from datetime import date, timedelta
import pytest
from app.services import intelligence
from tests.test_operations import system, block_external_notifications, headers


def records(end, baseline=10, recent=15):
    return [{'date': (end-timedelta(days=16-i)).isoformat(), 'daily_demand': baseline if i < 14 else recent} for i in range(17)]


def test_recent_surge_and_exact_windows():
    today=date.today()
    result=intelligence.calculate_trend(records(today),today)
    assert result['current_surge'] and result['surge']
    assert result['baseline_average']==10 and result['recent_average']==15
    assert result['increase_percent']==50 and len(result['points'])==14


def test_historical_surge_is_not_current():
    result=intelligence.calculate_trend(records(date(2025,12,31)),date(2026,10,9))
    assert result['status']=='historical' and result['surge'] and not result['current_surge']
    assert result['points'][-1]['date']=='2025-12-31'


@pytest.mark.parametrize('baseline,recent',[(10,14),(100,125),(100,100)])
def test_minimum_absolute_and_percentage_increase(baseline,recent):
    result=intelligence.calculate_trend(records(date.today(),baseline,recent),date.today())
    assert not result['current_surge']


def test_zero_baseline_has_no_invented_percentage():
    result=intelligence.calculate_trend(records(date.today(),0,5),date.today())
    assert result['increase_percent'] is None and result['current_surge']


def test_missing_duplicate_invalid_and_future_data():
    today=date.today()
    assert intelligence.calculate_trend([],today)['status']=='insufficient'
    rows=records(today);rows[3]['date']=rows[2]['date']
    assert intelligence.calculate_trend(rows,today)['status']=='insufficient'
    rows=records(today);rows[3]['daily_demand']=float('nan')
    assert intelligence.calculate_trend(rows,today)['status']=='insufficient'
    assert intelligence.calculate_trend(records(today+timedelta(days=1)),today)['status']=='insufficient'


def test_summary_requires_sign_in_and_scopes_hospital(system):
    assert system.client.get('/api/v1/intelligence/summary').status_code==401
    result=system.client.get('/api/v1/intelligence/summary',headers=headers(system)).json()
    assert result['hospital_id']=='H01' and result['counts']['out_of_stock']==1
    assert len(result['priorities'])<=3
    assert result['priorities'][0]['medicine_id']=='M01' and result['priorities'][0]['target']=='supply'
    result2=system.client.get('/api/v1/intelligence/summary?hospital=H01',headers=headers(system,'H02')).json()
    assert result2['hospital_id']=='H02' and result2['counts']['out_of_stock']==0


def test_current_surge_does_not_use_other_hospital_history(system,monkeypatch,tmp_path):
    path=tmp_path/'demand.csv'
    import csv
    with path.open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=['hospital_id','medicine_id','date','daily_demand']);writer.writeheader()
        for row in records(date.today(),10,50): writer.writerow({'hospital_id':'H02','medicine_id':'M01',**row})
        for row in records(date.today(),10,10): writer.writerow({'hospital_id':'H01','medicine_id':'M01',**row})
    monkeypatch.setattr(intelligence,'HISTORY_FILE',path)
    one=system.client.get('/api/v1/intelligence/summary',headers=headers(system)).json()
    two=system.client.get('/api/v1/intelligence/summary',headers=headers(system,'H02')).json()
    assert one['counts']['current_surges']==0 and two['counts']['current_surges']==1
