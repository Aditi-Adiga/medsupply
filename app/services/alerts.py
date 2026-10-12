"""One calculation for dashboard alerts and the persistent delivery queue."""
import math
from datetime import date, timedelta
from sqlalchemy import select
from app.db.operations import Alert, Delivery, Batch, StockPolicy, SupplyRequest, now
from app.services.transactions import atomic
from app.services.forecasting import forecast_for, simulate_batches

RANK = {"LOW": 2, "MEDIUM": 3, "HIGH": 4, "CRITICAL": 5}


def record(db, event, hospital, kind, severity, message):
    alert = db.get(Alert, event)
    send = not alert
    if not alert:
        alert = Alert(id=event, hospital_id=hospital, kind=kind, severity=severity,
                      message=message, generation=1)
        db.add(alert)
    else:
        send = alert.state == "Resolved" or RANK[severity] > RANK[alert.severity]
        if send:
            alert.generation += 1
            alert.state = "Active"
        alert.severity = severity
        alert.message = message
        alert.updated = now()
    db.flush()
    if send:
        db.add(Delivery(event_id=f"{event}:{alert.generation}", alert_id=event,
                        hospital_id=hospital, severity=severity, message=message))
    return alert


def assess(db, hospital):
    today = date.today()
    results = []
    for policy in db.scalars(select(StockPolicy).where(StockPolicy.hospital_id == hospital)):
        batches = list(db.scalars(select(Batch).where(Batch.hospital_id == hospital,
                       Batch.medicine_id == policy.medicine_id, Batch.unit == policy.unit).order_by(Batch.expiry, Batch.id)))
        usable = [b for b in batches if b.expiry > today]
        stock = sum(b.quantity - b.reserved for b in usable)
        horizon = policy.lead_days + policy.safety_days
        insufficient = policy.forecast_days < horizon
        forecast = forecast_for(policy, today)
        daily = forecast['values']
        stockout = simulate_batches(usable, daily, today, horizon)['stockout']
        expiry_simulation = simulate_batches(usable, daily, today)
        severity = ("CRITICAL" if stock == 0 else "HIGH" if stockout and stockout <= policy.lead_days
                    else "MEDIUM" if stockout or insufficient else "LOW")
        message = (f"{policy.medicine_id}: {stock} usable units. Check covers supplier lead time "
                   f"({policy.lead_days} days) and safety period ({policy.safety_days} days).")
        if insufficient:
            message += " Forecast is too short. Risk after its end is unknown."
        results.append({"key": f"stock:{hospital}:{policy.medicine_id}", "kind": "Stock exhausted" if stock == 0 else "Predicted shortage",
                        "severity": severity, "message": message, "active": severity != "LOW",
                        "medicine_id": policy.medicine_id, "usable_quantity": stock,
                        "stockout_in_days": stockout, "forecast_limited": insufficient,
                        "unit": policy.unit, "lead_days": policy.lead_days,
                        "recommended_action": "Find a safe supply source." if severity != "LOW" else "Monitor stock."})
        for b in usable:
            days = (b.expiry - today).days
            qty = b.quantity - b.reserved
            covered = days - 1 <= len(daily)
            waste = max(0, math.ceil(expiry_simulation['waste'].get(b.id, 0) - 1e-8)) if covered else None
            demand = qty - waste if covered else None
            text = (f"{policy.medicine_id}, batch {b.batch_id}: {days} days until expiry. "
                    f"Usable quantity: {qty}. " + (f"Expected use before expiry: {demand}. Expected unused quantity: {waste}."
                    if covered else "Forecast does not cover the expiry date. Unused quantity is unknown."))
            for kind, active, level in [("Near-expiry batch", days <= 30 and qty > 0, "MEDIUM"),
                                        ("Expected expiry waste", days <= 30 and waste is not None and waste > 0, "HIGH")]:
                results.append({"key": f"{kind}:{hospital}:{b.batch_id}", "kind": kind,
                                "severity": level, "message": text, "active": active,
                                "medicine_id": policy.medicine_id, "batch_id": b.batch_id,
                                "days_until_expiry": days, "usable_quantity": qty,
                                "expected_demand": demand, "expected_unused": waste, "expiry_forecast_limited": not covered,
                                "unit": policy.unit, "recommended_action": "Review batch use before expiry."})
    return results


def refresh(db, hospital):
    with atomic(db):
        values = assess(db, hospital)
        active = set()
        for value in values:
            if value["active"]:
                active.add(value["key"])
                record(db, value["key"], hospital, value["kind"], value["severity"], value["message"])
        for alert in db.scalars(select(Alert).where(Alert.hospital_id == hospital)):
            if (alert.id.startswith("stock:") or alert.kind in ("Near-expiry batch", "Expected expiry waste")) and alert.id not in active:
                alert.state = "Resolved"


def list_alerts(db, hospital):
    calculated = {r["key"]: r for r in assess(db, hospital)}
    values = []
    for a in db.scalars(select(Alert).where(Alert.hospital_id == hospital).order_by(Alert.updated.desc())):
        context = calculated.get(a.id, {})
        request_id = a.id.split(":")[1] if a.id.startswith("request:") else None
        medicine = context.get("medicine_id")
        if request_id:
            request = db.get(SupplyRequest, request_id)
            if request and hospital in (request.donor, request.recipient):
                medicine = request.medicine_id
        elif not medicine:
            if a.id.startswith("stock:"):
                medicine = a.id.split(":", 2)[-1]
            else:
                batch = db.scalar(select(Batch).where(Batch.hospital_id == hospital, Batch.batch_id == a.id.split(":", 2)[-1]))
                if batch:
                    medicine = batch.medicine_id
        value = {"id": a.id, "kind": a.kind, "severity": a.severity, "message": a.message,
                 "state": a.state, "medicine_id": medicine,
                 "recommended_action": context.get("recommended_action", "Review the supply request."),
                 "request_id": request_id}
        values.append(value)
    return values
