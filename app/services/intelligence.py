"""Hospital-scoped facts and explicit demand-surge rules. No model-generated facts."""
from datetime import date, timedelta
from pathlib import Path
import math
import pandas as pd
from sqlalchemy import select, or_
from app.db.models import Medicine
from app.db.operations import StockPolicy, SupplyRequest, now
from app.services.alerts import assess
from app.services.forecasting import history_frame

HISTORY_FILE = Path(__file__).resolve().parents[2] / 'data' / 'medical_supply_20_medicines.csv'
SURGE_RATIO = 1.30
MIN_INCREASE = 5


def calculate_trend(rows, today):
    """Require 17 unique consecutive days. Keep original dates and reject invalid demand."""
    clean = []
    for row in rows:
        try:
            day = date.fromisoformat(str(row['date'])[:10])
            quantity = float(row['daily_demand'])
        except (ValueError, TypeError, KeyError):
            return {'status': 'insufficient', 'reason': 'Demand records contain invalid dates or values.', 'points': []}
        if not math.isfinite(quantity) or quantity < 0 or day > today:
            return {'status': 'insufficient', 'reason': 'Demand records contain invalid values or future dates.', 'points': []}
        clean.append((day, quantity))
    clean.sort()
    points = [{'date': d.isoformat(), 'quantity': q} for d, q in clean[-14:]]
    if len(clean) < 17:
        return {'status': 'insufficient', 'reason': 'At least 17 daily records are required.', 'points': points}
    window = clean[-17:]
    days = [d for d, _ in window]
    if len(set(days)) != 17 or days != [days[0] + timedelta(days=i) for i in range(17)]:
        return {'status': 'insufficient', 'reason': 'The latest 17 records must cover consecutive days without duplicates.', 'points': points}
    baseline = sum(q for _, q in window[:14]) / 14
    recent = sum(q for _, q in window[14:]) / 3
    delta = recent - baseline
    surge = recent > baseline and recent >= baseline * SURGE_RATIO and delta >= MIN_INCREASE
    stale = (today - days[-1]).days > 3
    return {'status': 'historical' if stale else 'current', 'reason': 'Historical synthetic demand.' if stale else 'Recent synthetic demo demand.',
            'points': points, 'baseline_average': round(baseline, 2), 'recent_average': round(recent, 2),
            'increase_units_per_day': round(delta, 2), 'increase_percent': round(delta / baseline * 100, 1) if baseline > 0 else None,
            'surge': surge, 'current_surge': surge and not stale,
            'period_start': days[0].isoformat(), 'period_end': days[-1].isoformat(),
            'recent_start': days[-3].isoformat(), 'baseline_end': days[-4].isoformat()}


def summary(db, hospital):
    today = date.today()
    policies = list(db.scalars(select(StockPolicy).where(StockPolicy.hospital_id == hospital)))
    names = {m.id: m.name for m in db.scalars(select(Medicine))}
    risks = assess(db, hospital)
    stock = [r for r in risks if r['key'].startswith('stock:')]
    requests = list(db.scalars(select(SupplyRequest).where(or_(SupplyRequest.donor == hospital, SupplyRequest.recipient == hospital))))
    incoming = [r for r in requests if r.donor == hospital and r.status == 'Requested']
    actions = [r for r in requests if (r.donor == hospital and r.status == 'Approved') or (r.recipient == hospital and r.status == 'Dispatched')]
    grouped = {}
    if HISTORY_FILE.exists():
        history, demo_shift = history_frame(HISTORY_FILE, today)
        if {'hospital_id','medicine_id','date','daily_demand'}.issubset(history.columns):
            own = history[history.hospital_id == hospital]
            grouped = {mid: group.to_dict('records') for mid, group in own.groupby('medicine_id')}
    trends = []
    for policy in policies:
        trend = calculate_trend(grouped.get(policy.medicine_id, []), today)
        trends.append({'medicine_id': policy.medicine_id, 'medicine_name': names.get(policy.medicine_id, policy.medicine_id), 'unit': policy.unit, **trend})
    priorities = []
    for risk in risks:
        if not risk['active'] or risk['kind'] == 'Near-expiry batch':
            continue
        mid = risk['medicine_id']
        if risk['key'].startswith('stock:'):
            score = 100 if risk['usable_quantity'] == 0 else 85 if risk['severity'] == 'HIGH' else 50
            text = f"{risk['usable_quantity']} {risk['unit']} usable. "
            text += f"Expected stock-out: day {risk['stockout_in_days']}." if risk['stockout_in_days'] is not None else 'Forecast does not cover a confirmed stock-out date.'
            label, target = 'Find supply', 'supply'
        else:
            score = 70
            text = f"{risk['expected_unused']} {risk['unit']} expected unused before expiry in {risk['days_until_expiry']} days. Review the batch."
            label, target = 'Review batch', 'medicine'
        priorities.append({'id': risk['key'], 'medicine_id': mid, 'title': names.get(mid, mid), 'message': text,
                           'severity': risk['severity'], 'target': target, 'button': label, '_score': score,
                           '_stockout': risk.get('stockout_in_days') if risk.get('stockout_in_days') is not None else 100000})
    for request in incoming + actions:
        priorities.append({'id': request.id, 'request_id': request.id, 'title': names.get(request.medicine_id, request.medicine_id),
                           'message': f"{request.donor} → {request.recipient}: {request.requested} units. {request.status}. {request.urgency}.",
                           'severity': 'HIGH' if request.urgency == 'Urgent' else 'MEDIUM', 'target': 'request', 'button': 'Review request',
                           '_score': 90 if request.urgency == 'Urgent' else 60, '_stockout': 100000})
    for trend in trends:
        if trend.get('current_surge'):
            priorities.append({'id': 'surge:' + trend['medicine_id'], 'medicine_id': trend['medicine_id'], 'title': trend['medicine_name'],
                               'message': f"Latest 3-day average: {trend['recent_average']} {trend['unit']}/day. Previous 14-day average: {trend['baseline_average']}.",
                               'severity': 'HIGH', 'target': 'medicine', 'button': 'Review demand', '_score': 75, '_stockout': 100000})
    priorities.sort(key=lambda item: (-item['_score'], item['_stockout'], item['id']))
    for item in priorities:
        item.pop('_score'); item.pop('_stockout')
    totals = {'out_of_stock': sum(r['usable_quantity'] == 0 for r in stock),
              'urgent_shortages': sum(r['severity'] in ('HIGH','CRITICAL') for r in stock),
              'expiry_waste_batches': sum(r['active'] and r['kind'] == 'Expected expiry waste' for r in risks),
              'incoming_requests': len(incoming), 'transfers_need_action': len(actions),
              'current_surges': sum(bool(t.get('current_surge')) for t in trends),
              'insufficient_trends': sum(t['status'] == 'insufficient' for t in trends)}
    lines = [f"{totals['out_of_stock']} medicines are out of stock. {totals['urgent_shortages']} medicines have high or critical shortage risk.",
             f"{len(incoming)} incoming requests need review. {len(actions)} transfers need dispatch or receipt.",
             f"{totals['expiry_waste_batches']} batches may have unused stock near expiry."]
    if any(t['status'] == 'historical' for t in trends):
        lines.append('Historical demand is shown with its original dates. It cannot confirm a current surge.')
    lines.append(f"{totals['current_surges']} current demand surges detected in records with enough recent data.")
    return {'hospital_id': hospital, 'generated_at': now().isoformat() + 'Z', 'method': 'Local rules using hospital data. Synthetic demand dates are shifted to the demo date. No language model is connected.',
            'summary_lines': lines, 'counts': totals, 'priorities': priorities[:3], 'priority_count': len(priorities),
            'trends': sorted(trends, key=lambda t: (not t.get('current_surge',False), not t.get('surge',False), t['medicine_id'])),
            'surge_rule': 'Latest 3-day average is at least 30% and 5 units/day above the previous 14-day average. Requires 17 consecutive daily records. Current records end within 3 days.'}
