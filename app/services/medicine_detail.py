"""Hospital-only detail using the same policy as stock risk and transfer safety."""
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
from fastapi import HTTPException
from sqlalchemy import select
from app.db.models import Medicine
from app.db.operations import Batch
from app.services.supply import policy_for
from app.services.alerts import assess
from app.services.forecasting import forecast_for


def detail(db, hospital, medicine):
    policy = policy_for(db, hospital, medicine)
    item = db.get(Medicine, medicine)
    if not policy or not item:
        raise HTTPException(404, "Medicine is not in your hospital inventory.")
    forecast = forecast_for(policy)
    history = forecast['history']
    risk = next(r for r in assess(db, hospital) if r.get("medicine_id") == medicine)
    return {"medicine_id": medicine, "name": item.name, "unit": policy.unit,
            "hospital_id": hospital, "lead_days": policy.lead_days, "safety_days": policy.safety_days,
            "forecast_days": policy.forecast_days, "risk": risk, "history": history,
            "forecast": forecast['points'],
            "forecast_method": forecast['method'] + '. Shared by chart, stock risk, expiry checks and supply search.',
            "uncertainty": forecast['uncertainty'] + ' ' + forecast['date_note'],
            "validation": forecast['validation'], "fallback_reason": forecast['fallback_reason'],
            "demo_date_shift_days": forecast['demo_date_shift_days'],
            "batches": [{"batch_id": b.batch_id, "quantity": b.quantity, "reserved": b.reserved,
                         "expiry": b.expiry, "unit": b.unit} for b in db.scalars(select(Batch).where(
                             Batch.hospital_id == hospital, Batch.medicine_id == medicine))]}
