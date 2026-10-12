from datetime import date,timedelta
from types import SimpleNamespace
import csv
import pytest
from sqlalchemy import select
from app.services import forecasting,alerts,supply
from app.db.operations import Batch,StockPolicy
from tests.test_operations import system,block_external_notifications,headers


def history(count=200):
    start=date(2025,1,1)
    return [{'date':(start+timedelta(days=i)).isoformat(),'quantity':10+((start+timedelta(days=i)).weekday()==0)*30+i*.05} for i in range(count)]


def test_weekly_model_beats_baseline_on_unseen_dates():
    records=history()
    values,method,metrics=forecasting._fit(tuple((r['date'],r['quantity']) for r in records),30)
    assert 'Validated weekly' in method
    assert metrics['model_mae'] < metrics['baseline_mae']
    assert len(set(values))>1 and all(v>=0 for v in values)
    assert metrics['test_days']==90
    assert all(f['train_end']<f['test_start']<=f['test_end'] for f in metrics['folds'])


def test_constant_history_uses_average_instead_of_artificial_variation():
    values,method,metrics=forecasting._fit(tuple((r['date'],10.) for r in history()),30)
    assert method=='14-day average fallback' and set(values)=={10.}
    assert metrics['baseline_mae']==0


def make_csv(path,rows):
    with path.open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=['hospital_id','medicine_id','date','daily_demand']);writer.writeheader();writer.writerows(rows)


def test_demo_date_mapping_preserves_source_and_forecast_alignment(tmp_path,monkeypatch):
    path=tmp_path/'source.csv'
    make_csv(path,[{'hospital_id':'H01','medicine_id':'M01','date':r['date'],'daily_demand':r['quantity']} for r in history()])
    original=path.read_bytes();monkeypatch.setattr(forecasting,'HISTORY_FILE',path)
    anchor=date(2026,10,9)
    policy=SimpleNamespace(hospital_id='H01',medicine_id='M01',unit='unit',forecast_days=30,daily_demand=99)
    result=forecasting.forecast_for(policy,anchor)
    assert result['history'][-1]['date']=='2026-10-09'
    assert result['history'][-1]['original_date']==history()[-1]['date']
    assert result['points'][0]['date']=='2026-10-10'
    assert [p['quantity'] for p in result['points']]==result['values']
    assert path.read_bytes()==original and result['demo_date_shift_days']>0


def test_missing_history_falls_back_to_policy_without_random_values(tmp_path,monkeypatch):
    monkeypatch.setattr(forecasting,'HISTORY_FILE',tmp_path/'missing.csv')
    policy=SimpleNamespace(hospital_id='H01',medicine_id='M01',unit='unit',forecast_days=3,daily_demand=25)
    assert forecasting.forecast_for(policy)['values']==[25,25,25]


def test_invalid_or_gapped_history_is_not_used(tmp_path,monkeypatch):
    path=tmp_path/'source.csv';rows=history(20)
    rows[3]['date']=rows[2]['date']
    make_csv(path,[{'hospital_id':'H01','medicine_id':'M01','date':r['date'],'daily_demand':r['quantity']} for r in rows])
    monkeypatch.setattr(forecasting,'HISTORY_FILE',path)
    policy=SimpleNamespace(hospital_id='H01',medicine_id='M01',unit='unit',forecast_days=3,daily_demand=25)
    assert forecasting.forecast_for(policy)['values']==[25,25,25]


def test_fefo_expiry_does_not_use_wasted_earlier_batch_as_consumption():
    today=date.today()
    batches=[SimpleNamespace(id=1,expiry=today+timedelta(days=3),quantity=500,reserved=0),SimpleNamespace(id=2,expiry=today+timedelta(days=5),quantity=100,reserved=0)]
    result=forecasting.simulate_batches(batches,[10]*5,today)
    assert result['waste'][1]==480 and result['waste'][2]==80
    assert result['unmet_demand'] and result['stockout']==5


def test_unknown_future_demand_is_not_extrapolated():
    assert forecasting.demand_between([10,20,30],2,4)==50
    with pytest.raises(ValueError):forecasting.demand_between([10],1,3)


def test_risk_and_transfer_use_daily_forecast_not_policy_average(system,monkeypatch):
    def model(policy,today=None):return {'values':[150,50] if policy.hospital_id=='H02' else [20,200]}
    monkeypatch.setattr(alerts,'forecast_for',model);monkeypatch.setattr(supply,'forecast_for',model)
    with system.sessions() as db:
        for p in db.scalars(select(StockPolicy)):
            p.lead_days=2;p.safety_days=0;p.forecast_days=2
        b=db.scalar(select(Batch).where(Batch.hospital_id=='H02'));b.quantity=260;db.commit()
        assert alerts.assess(db,'H02')[0]['stockout_in_days'] is None
        allocation=supply.safe_allocation(db,'H02','H01','M01',200)
        assert sum(a['quantity'] for a in allocation)==60
        b.quantity=100;db.commit()
        assert alerts.assess(db,'H02')[0]['stockout_in_days']==1


def test_detail_chart_and_risk_share_same_service(system,monkeypatch):
    from app.services import medicine_detail
    original=forecasting.forecast_for
    def vector(policy,today=None):
        result=original(policy,today)
        result['values']=[150]*policy.forecast_days
        result['points']=[{**p,'quantity':150} for p in result['points']]
        return result
    monkeypatch.setattr(alerts,'forecast_for',vector);monkeypatch.setattr(medicine_detail,'forecast_for',vector)
    response=system.client.get('/api/v1/medicines/M01/detail',headers=headers(system,'H02'))
    assert response.status_code==200
    body=response.json()
    assert body['forecast'][0]['quantity']==150 and body['risk']['stockout_in_days']==7


def test_expiry_past_horizon_is_unknown(system):
    with system.sessions() as db:
        values=alerts.assess(db,'H02')
        waste=next(r for r in values if r['kind']=='Expected expiry waste')
        assert waste['expected_unused'] is None and waste['expiry_forecast_limited'] and not waste['active']
