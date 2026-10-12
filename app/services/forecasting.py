"""Shared, date-ordered daily forecast with validated fallback and explicit demo dates."""
from datetime import date, timedelta
from pathlib import Path
from functools import lru_cache
import math
import numpy as np
import pandas as pd

HISTORY_FILE = Path(__file__).resolve().parents[2] / 'data' / 'medical_supply_20_medicines.csv'


@lru_cache(maxsize=2)
def _source(path, modified, size):
    frame = pd.read_csv(path, dtype={'hospital_id':str, 'medicine_id':str})
    required = {'hospital_id','medicine_id','date','daily_demand'}
    if not required.issubset(frame.columns):
        return pd.DataFrame(columns=list(required) + ['original_date'])
    frame['original_date'] = frame['date'].astype(str)
    frame['date'] = pd.to_datetime(frame['date'], errors='coerce').dt.date
    frame['daily_demand'] = pd.to_numeric(frame['daily_demand'], errors='coerce')
    return frame


@lru_cache(maxsize=2)
def _aligned_source(path, modified, size, anchor):
    frame = _source(path, modified, size).copy()
    valid_dates = frame['date'].dropna()
    shift = (anchor - valid_dates.max()).days if len(valid_dates) else 0
    frame['date'] = frame['date'].map(lambda d: d + timedelta(days=shift) if pd.notna(d) else None)
    return frame, shift


def history_frame(path=None, anchor=None):
    path = Path(path or HISTORY_FILE)
    anchor = anchor or date.today()
    if not path.exists():
        return pd.DataFrame(columns=['hospital_id','medicine_id','date','daily_demand','original_date']), 0
    stat = path.stat()
    # Callers filter this shared frame; they must not mutate it.
    return _aligned_source(str(path), stat.st_mtime_ns, stat.st_size, anchor)


def history_for(hospital, medicine, anchor=None):
    frame, shift = history_frame(anchor=anchor)
    rows = frame[(frame.hospital_id == hospital) & (frame.medicine_id == medicine)].sort_values('date')
    if rows.empty:
        return [], shift
    if (rows.date.isna().any() or rows.date.duplicated().any() or rows.daily_demand.isna().any()
            or not np.isfinite(rows.daily_demand.to_numpy()).all() or (rows.daily_demand < 0).any()):
        return [], shift
    records = [{'date':r.date.isoformat(), 'original_date':r.original_date, 'quantity':float(r.daily_demand)} for r in rows.itertuples()]
    return records, shift


def average_predict(records, days):
    value = sum(r['quantity'] for r in records[-14:]) / min(14, len(records))
    return [value] * days


def weekly_predict(records, days):
    recent = records[-84:]
    values = np.array([r['quantity'] for r in recent], dtype=float)
    x = np.arange(len(values), dtype=float) - (len(values) - 1)
    design = np.column_stack([np.ones(len(values)), x])
    intercept, slope = np.linalg.lstsq(design, values, rcond=None)[0]
    level = max(0, float(intercept))
    slope = float(np.clip(slope, -max(1,level)*0.01, max(1,level)*0.01))
    residual = values - (intercept + slope*x)
    weekdays = [date.fromisoformat(r['date']).weekday() for r in recent]
    effects = {}
    for day in range(7):
        members = [float(v) for v,w in zip(residual,weekdays) if w==day]
        effects[day] = sum(members)/(len(members)+2) if members else 0
    last = date.fromisoformat(records[-1]['date'])
    return [max(0, level + slope*(i/(1+i/28)) + effects[(last+timedelta(days=i)).weekday()]) for i in range(1,days+1)]


@lru_cache(maxsize=512)
def _fit(records_tuple, days):
    records = [{'date':d,'quantity':q} for d,q in records_tuple]
    metrics = None
    method = '14-day average fallback'
    use_weekly = False
    if len(records) >= 146:
        model_errors, baseline_errors, fold_results = [], [], []
        for offset in (90,60,30):
            cutoff = len(records)-offset
            train, test = records[:cutoff], records[cutoff:cutoff+30]
            predicted = weekly_predict(train,30)
            baseline = average_predict(train,30)
            actual = [r['quantity'] for r in test]
            errors = [abs(a-p) for a,p in zip(actual,predicted)]
            base_errors = [abs(a-p) for a,p in zip(actual,baseline)]
            model_errors.extend(errors);baseline_errors.extend(base_errors)
            fold_results.append({'train_end':train[-1]['date'],'test_start':test[0]['date'],'test_end':test[-1]['date'],
                                 'model_mae':round(sum(errors)/30,3),'baseline_mae':round(sum(base_errors)/30,3)})
        mae = sum(model_errors)/len(model_errors)
        baseline_mae = sum(baseline_errors)/len(baseline_errors)
        use_weekly = mae < baseline_mae*0.98
        metrics = {'model_mae':round(mae,3), 'baseline_mae':round(baseline_mae,3), 'test_days':90,
                   'folds':fold_results,'selection_rule':'Weekly model must reduce mean absolute error by more than 2%.'}
    if use_weekly:
        method = 'Validated weekly pattern with damped trend'
        values = weekly_predict(records,days)
    else:
        values = average_predict(records,days)
    return tuple(round(v,4) for v in values), method, metrics


def forecast_for(policy, today=None):
    today = today or date.today()
    days = max(0, int(policy.forecast_days))
    history, shift = history_for(policy.hospital_id, policy.medicine_id, today)
    reason = ''
    if policy.unit != 'unit':
        history = []; reason = 'Historical demand has no matching unit metadata.'
    if history:
        dates = [date.fromisoformat(r['date']) for r in history]
        if dates[-1] != today or any(b-a != timedelta(days=1) for a,b in zip(dates,dates[1:])):
            history = []; reason = 'History does not end at the demo anchor or has missing days.'
    if len(history) >= 14:
        values, method, metrics = _fit(tuple((r['date'],r['quantity']) for r in history),days)
    else:
        baseline = float(policy.daily_demand)
        if not math.isfinite(baseline) or baseline < 0:
            raise ValueError('Demand policy must be finite and non-negative.')
        values = tuple([baseline]*days)
        method, metrics = 'Configured daily demand fallback', None
        reason = reason or 'Not enough valid daily history. At least 14 days are required.'
    points = [{'date':(today+timedelta(days=i+1)).isoformat(),'quantity':q} for i,q in enumerate(values)]
    return {'history':history[-30:], 'points':points,'values':list(values),'method':method,'validation':metrics,
            'fallback_reason':reason, 'demo_anchor':today.isoformat(),'demo_date_shift_days':shift,
            'date_note':f'Synthetic demo dates shifted by {shift} days to end at {today.isoformat()}. Original source dates are preserved in the CSV.',
            'uncertainty':'Point estimates only. No validated prediction interval is available.'}


def demand_between(values, start, end):
    """One-based start is inclusive, end exclusive. Refuse unknown future demand."""
    if start < 1 or end < start or end-1 > len(values):
        raise ValueError('Demand period is outside the forecast horizon.')
    return sum(values[start-1:end-1])


def simulate_batches(batches, values, today, days=None, quantities=None):
    """Use earliest-expiring stock first; no consumption on or after expiry."""
    batches = sorted(batches,key=lambda b:(b.expiry,b.id))
    remaining = {b.id:float(quantities[b.id] if quantities is not None else b.quantity-b.reserved) for b in batches}
    waste = {}
    stockout = 0 if sum(remaining.values()) <= 0 else None
    horizon = len(values) if days is None else min(days,len(values))
    unmet = False
    for day in range(1,horizon+1):
        demand = values[day-1]
        for batch in batches:
            if batch.expiry <= today+timedelta(days=day):
                waste.setdefault(batch.id,remaining[batch.id]);remaining[batch.id]=0
                continue
            used = min(demand,remaining[batch.id]);remaining[batch.id]-=used;demand-=used
        unmet = unmet or demand > 1e-8
        if stockout is None and (demand > 1e-8 or (values[day-1]>0 and sum(remaining.values())<=1e-8)):
            stockout=day
    for batch in batches:
        if batch.expiry <= today+timedelta(days=horizon+1):
            waste.setdefault(batch.id,remaining[batch.id])
    return {'remaining':remaining,'waste':waste,'stockout':stockout,'unmet_demand':unmet}
