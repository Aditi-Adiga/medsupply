"""Controlled network search. No assistant receives raw donor inventory."""
import math
import uuid
from datetime import date, timedelta
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import object_session
from app.db.models import Hospital, Medicine
from app.db.operations import Batch, StockPolicy, SupplyRequest, Audit, now
from app.services.alerts import record
from app.services.transactions import atomic
from app.services.routes import route_for
from app.services.forecasting import forecast_for, demand_between, simulate_batches


def policy_for(db, hospital, medicine):
    return db.scalar(select(StockPolicy).where(StockPolicy.hospital_id == hospital, StockPolicy.medicine_id == medicine))


def travel_days(db, donor, recipient):
    route = route_for(donor, recipient)
    if route is None:
        raise HTTPException(409, "Road route is unavailable for this hospital pair.")
    # Daily expiry calculations use a conservative whole-day delivery horizon.
    return math.ceil(route["estimated_delivery_minutes"] / 1440)


def safe_allocation(db, donor, recipient, medicine, quantity):
    today = date.today()
    dp, rp = policy_for(db, donor, medicine), policy_for(db, recipient, medicine)
    if not dp or not rp or dp.unit != rp.unit or dp.forecast_days < dp.lead_days + dp.safety_days:
        return []
    if route_for(donor, recipient) is None:
        return []
    travel = travel_days(db, donor, recipient)
    donor_daily = forecast_for(dp, today)['values']
    recipient_daily = forecast_for(rp, today)['values']
    if rp.forecast_days <= travel or sum(recipient_daily[travel:]) <= 0:
        return []
    batches = list(db.scalars(select(Batch).where(Batch.hospital_id == donor, Batch.medicine_id == medicine,
                    Batch.unit == dp.unit, Batch.expiry > today).order_by(Batch.expiry, Batch.id)))
    retained = {b.id: b.quantity - b.reserved for b in batches}
    horizon = dp.lead_days + dp.safety_days
    if simulate_batches(batches, donor_daily, today, horizon, retained)['unmet_demand']:
        return []
    recipient_stock = sum(b.quantity - b.reserved for b in db.scalars(select(Batch).where(
        Batch.hospital_id == recipient, Batch.medicine_id == medicine, Batch.unit == rp.unit, Batch.expiry > today)))
    # Include already approved and in-transit incoming units in recipient use capacity.
    recipient_stock += sum(r.approved for r in db.scalars(select(SupplyRequest).where(
        SupplyRequest.recipient == recipient, SupplyRequest.medicine_id == medicine,
        SupplyRequest.status.in_(["Approved", "Dispatched"]))))
    allocations = []
    for batch in batches:
        days = (batch.expiry - today).days
        if days <= travel + 1:
            continue
        recipient_capacity = max(0, math.floor(demand_between(recipient_daily, travel + 1, min(days, rp.forecast_days + 1))) - recipient_stock)
        amount = min(quantity - sum(a["quantity"] for a in allocations), retained[batch.id], recipient_capacity)
        # Find the largest integer transfer that leaves every donor day covered.
        low, high = 0, int(amount)
        while low < high:
            trial = (low + high + 1) // 2
            candidate = dict(retained)
            candidate[batch.id] -= trial
            if simulate_batches(batches, donor_daily, today, horizon, candidate)['unmet_demand']:
                high = trial - 1
            else:
                low = trial
        amount = low
        if amount > 0:
            allocations.append({"stock_id": batch.id, "batch_id": batch.batch_id,
                                "quantity": amount, "expiry": batch.expiry.isoformat(), "unit": batch.unit})
            retained[batch.id] -= amount
            recipient_stock += amount
    return allocations


def search(db, user, medicine, quantity):
    if quantity <= 0 or not db.get(Medicine, medicine):
        raise HTTPException(422, "Use a valid medicine and a positive quantity.")
    result = []
    for hospital in db.scalars(select(Hospital).where(Hospital.id != user.hospital_id)):
        allocation = safe_allocation(db, hospital.id, user.hospital_id, medicine, quantity)
        if allocation:
            travel = travel_days(db, hospital.id, user.hospital_id)
            result.append({"donor_hospital": hospital.id, "medicine": medicine,
                           "available_quantity": sum(a["quantity"] for a in allocation), "unit": allocation[0]["unit"],
                           "estimated_arrival_days": travel, "travel_time_simulated": False,
                           **route_for(hospital.id, user.hospital_id),
                           "earliest_expiry": min(a["expiry"] for a in allocation),
                           "reason": "Stock covers donor demand and safety stock. Recipient can use it before expiry."})
    return sorted(result, key=lambda x: (x["estimated_delivery_minutes"], -x["available_quantity"]))


def request_view(r):
    value = {key: getattr(r, key) for key in ("id", "recipient", "donor", "medicine_id", "requested", "approved",
            "allocations", "urgency", "reason", "status", "in_transit", "created", "updated", "created_by")}
    policy = policy_for(object_session(r), r.recipient, r.medicine_id)
    value["unit"] = r.allocations[0]["unit"] if r.allocations else policy.unit if policy else "unknown"
    return value


def participant(user, r):
    if not r or user.hospital_id not in (r.recipient, r.donor):
        raise HTTPException(404, "Request not found.")


def notify_request(db, r, state):
    hospitals = [r.donor] if state == "Requested" else [r.recipient] if state in ("Approved", "Rejected") else [r.donor, r.recipient]
    for hospital in hospitals:
        record(db, f"request:{r.id}:{state}:{hospital}", hospital,
               "Incoming supply request" if state == "Requested" else f"Request {state.lower()}",
               "HIGH" if r.urgency == "Urgent" else "MEDIUM",
               f"Request {r.id}: {state}. {r.medicine_id}, {r.requested if state == 'Requested' else r.approved} units.")


def create_request(db, user, donor, medicine, quantity, urgency, reason, recipient=None):
    if recipient is not None and recipient != user.hospital_id:
        raise HTTPException(403, "You cannot request stock for another hospital.")
    with atomic(db):
        if quantity <= 0 or donor == user.hospital_id or not db.get(Hospital, donor) or not db.get(Medicine, medicine):
            raise HTTPException(422, "Check hospital, medicine, and quantity.")
        if not policy_for(db, user.hospital_id, medicine):
            raise HTTPException(422, "This medicine has no hospital demand policy.")
        r = SupplyRequest(id=str(uuid.uuid4()), recipient=user.hospital_id, donor=donor, medicine_id=medicine,
                          requested=quantity, approved=0, urgency=urgency, reason=reason, created_by=user.id,
                          status="Requested", allocations=[])
        db.add(r)
        db.flush()
        db.add(Audit(user_id=user.id, action="Requested", object_id=r.id))
        notify_request(db, r, "Requested")
        return request_view(r)


def action(db, user, request_id, target, quantity=None):
    with atomic(db):
        r = db.get(SupplyRequest, request_id)
        participant(user, r)
        donor_actions = {"Approved", "Rejected", "Dispatched"}
        if target in donor_actions and user.hospital_id != r.donor:
            raise HTTPException(403, "Only the donor administrator can perform this action.")
        if target == "Received" and user.hospital_id != r.recipient:
            raise HTTPException(403, "Only the recipient can record receipt.")
        transitions = {"Approved": {"Requested"}, "Rejected": {"Requested"}, "Dispatched": {"Approved"},
                       "Received": {"Dispatched"}, "Cancelled": {"Requested", "Approved"}}
        if target not in transitions or r.status not in transitions[target]:
            raise HTTPException(409, "This status change is not allowed.")
        if target == "Approved":
            qty = r.requested if quantity is None else quantity
            if qty <= 0 or qty > r.requested:
                raise HTTPException(422, "Approved quantity must be positive and within the request.")
            allocations = safe_allocation(db, r.donor, r.recipient, r.medicine_id, qty)
            if sum(a["quantity"] for a in allocations) != qty:
                raise HTTPException(409, "Safe stock is insufficient. Search again or approve fewer units.")
            r.allocations = allocations
            r.approved = qty
            for a in allocations:
                db.get(Batch, a["stock_id"]).reserved += a["quantity"]
        elif target in ("Dispatched", "Cancelled"):
            for a in r.allocations:
                b = db.get(Batch, a["stock_id"])
                if target == "Dispatched":
                    if b.expiry <= date.today() + timedelta(days=travel_days(db, r.donor, r.recipient) + 1):
                        raise HTTPException(409, "Allocated stock will expire too soon. Cancel the request.")
                    b.quantity -= a["quantity"]
                b.reserved -= a["quantity"]
            if target == "Dispatched":
                r.in_transit = r.approved
        elif target == "Received":
            for a in r.allocations:
                b = db.scalar(select(Batch).where(Batch.hospital_id == r.recipient, Batch.batch_id == a["batch_id"]))
                if not b:
                    b = Batch(batch_id=a["batch_id"], hospital_id=r.recipient, medicine_id=r.medicine_id,
                              expiry=date.fromisoformat(a["expiry"]), unit=a["unit"], quantity=0, reserved=0)
                    db.add(b)
                elif b.medicine_id != r.medicine_id or b.expiry.isoformat() != a["expiry"] or b.unit != a["unit"]:
                    raise HTTPException(409, "Batch identity does not match existing stock.")
                b.quantity += a["quantity"]
            r.in_transit = 0
        r.status = target
        r.updated = now()
        db.add(Audit(user_id=user.id, action=target, object_id=r.id))
        notify_request(db, r, target)
        db.flush()
        return request_view(r)
