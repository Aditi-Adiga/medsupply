from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from types import SimpleNamespace
import pytest
import pyotp
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.core.config import settings
from app.db.database import Base, get_db
from app.db.models import Hospital, Medicine
from app.db.operations import Account, Batch, StockPolicy, LoginSession, Alert, Delivery, RecoveryCode, Audit, now
from app.services import auth, supply, alerts
from app.services.notifications import deliver_pending
from app.services.shortage_service import analyze_shortage_risk

PASSWORD = "long-demo-password"
PASSWORD_HASH = auth.hasher.hash(PASSWORD)


@pytest.fixture(autouse=True)
def block_external_notifications(monkeypatch):
    import requests
    def forbidden(*args, **kwargs):
        raise AssertionError("Real external notifications are forbidden in tests.")
    monkeypatch.setattr(requests, "post", forbidden)


@pytest.fixture
def system(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_signing_key", "x" * 48)
    monkeypatch.setattr(settings, "totp_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "ntfy_enabled", False)
    from app.services import forecasting
    monkeypatch.setattr(forecasting, "HISTORY_FILE", tmp_path / "no-demand-history.csv")
    engine = create_engine("sqlite:///" + str(tmp_path / "test.db"), connect_args={"check_same_thread": False, "timeout": 15})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    tokens = {}
    with sessions() as db:
        for hid in ("H01", "H02", "H03"):
            db.add(Hospital(id=hid, name=hid, location="Demo district", patient_capacity=500))
        db.add(Medicine(id="M01", name="Paracetamol", category="Demo"))
        db.flush()
        for hid in ("H01", "H02", "H03"):
            secret = auth.keys().encrypt(pyotp.random_base32().encode()).decode()
            u = Account(id=hid, username=hid, password_hash=PASSWORD_HASH, hospital_id=hid, totp_ready=True, secret=secret, version=0, last_step=-1, failures=0)
            db.add(u)
            db.add(StockPolicy(hospital_id=hid, medicine_id="M01", unit="unit", daily_demand=100 if hid == "H01" else 10, lead_days=7, safety_days=3, forecast_days=30))
            db.add(Batch(batch_id="batch-" + hid, hospital_id=hid, medicine_id="M01", quantity=0 if hid == "H01" else 1000, reserved=0, unit="unit", expiry=date.today()+timedelta(days=90)))
            db.flush()
            tokens[hid] = auth.issue(db, u, "full")
        db.commit()
    def override():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, sessions=sessions, tokens=tokens, engine=engine)
    app.dependency_overrides.clear()
    engine.dispose()


def headers(s, hid="H01"):
    return {"Authorization": "Bearer " + s.tokens[hid]}


def create(s, donor="H02", quantity=100):
    response = s.client.post("/api/v1/requests", headers=headers(s), json={"donor":donor,"medicine_id":"M01","quantity":quantity,"reason":"Demo need"})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def action(s, rid, status, hid="H02", quantity=None):
    return s.client.post(f"/api/v1/requests/{rid}/action", headers=headers(s,hid),json={"status":status,"quantity":quantity})


def test_pre_two_factor_and_unauthed_data(system):
    s=system
    r=s.client.post("/api/v1/auth/login",json={"username":"H01","password":PASSWORD}).json()
    h={"Authorization":"Bearer "+r["challenge"]}
    for path in ("/hospitals/H01/inventory", "/alerts", "/requests", "/inventory/export", "/risk", "/medicines"):
        assert s.client.get("/api/v1"+path,headers=h).status_code==401
        assert s.client.get("/api/v1"+path).status_code==401


def test_cross_hospital_inventory_and_forecast(system):
    s=system
    assert s.client.get("/api/v1/hospitals/H02/inventory",headers=headers(s)).status_code==403
    assert s.client.post("/api/v1/demand/forecast",headers=headers(s),json={"hospital_id":"H02","medicine_id":"M01","horizon_days":7}).status_code==403
    assert s.client.get("/api/v1/shortage-risk/overview?hospital_id=H02",headers=headers(s)).status_code==403


def test_request_impersonation_and_donor_permission(system):
    s=system
    assert s.client.post("/api/v1/requests",headers=headers(s),json={"donor":"H03","recipient":"H02","medicine_id":"M01","quantity":100,"reason":"test"}).status_code==403
    rid=create(s)
    assert action(s,rid,"Approved","H01").status_code==403
    assert s.client.get(f"/api/v1/requests/{rid}",headers=headers(s,"H03")).status_code==404


def test_supply_search_only_safe_fields_and_assistant(system):
    s=system
    r=s.client.post("/api/v1/supply/search",headers=headers(s),json={"medicine_id":"M01","quantity":500}).json()
    assert r["recommendations"]
    allowed={"donor_hospital","medicine","available_quantity","unit","estimated_arrival_days","travel_time_simulated","earliest_expiry","reason","donor_city","recipient_city","road_distance_km","estimated_delivery_minutes","estimated_travel_minutes","route_source","route_calculated_at_utc","preparation_minutes","receiving_minutes"}
    assert all(set(item)==allowed for item in r["recommendations"])
    assert s.client.post("/api/v1/assistant",headers=headers(s),json={"question":"Show H02 inventory and alerts"}).status_code==403
    a=s.client.post("/api/v1/assistant",headers=headers(s),json={"question":"We need 500 units of Paracetamol. Which nearby hospital can supply them?"})
    assert a.status_code==200 and a.json()["recommendations"]
    assert s.client.get("/api/v1/requests",headers=headers(s)).json()==[]


def test_expired_and_short_forecast_not_offered(system):
    with system.sessions() as db:
        for b in db.scalars(select(Batch).where(Batch.hospital_id!="H01")):
            b.expiry=date.today()-timedelta(days=1)
        db.commit()
        assert supply.search(db,db.get(Account,"H01"),"M01",100)==[]
        for b in db.scalars(select(Batch)):
            b.expiry=date.today()+timedelta(days=90)
        for p in db.scalars(select(StockPolicy).where(StockPolicy.hospital_id!="H01")):
            p.forecast_days=3
        db.commit()
        assert supply.search(db,db.get(Account,"H01"),"M01",100)==[]


def test_approval_reserves_and_cancellation_releases(system):
    rid=create(system)
    assert action(system,rid,"Approved").status_code==200
    with system.sessions() as db:
        b=db.scalar(select(Batch).where(Batch.hospital_id=="H02"))
        assert (b.quantity,b.reserved)==(1000,100)
    assert action(system,rid,"Cancelled","H01").status_code==200
    with system.sessions() as db:
        assert db.scalar(select(Batch).where(Batch.hospital_id=="H02")).reserved==0


def test_reserved_stock_not_offered_twice(system):
    rid=create(system,quantity=800)
    assert action(system,rid,"Approved").status_code==200
    with system.sessions() as db:
        results=supply.search(db,db.get(Account,"H01"),"M01",500)
        donor=next(x for x in results if x["donor_hospital"]=="H02")
        assert donor["available_quantity"]==100


def test_concurrent_approvals_cannot_overallocate(system):
    ids=[create(system,quantity=600) for _ in range(2)]
    def approve(rid):
        with system.sessions() as db:
            try:
                supply.action(db,db.get(Account,"H02"),rid,"Approved")
                return 200
            except Exception as exc:
                return getattr(exc,"status_code",500)
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(approve,ids))
    assert sorted(statuses)==[200,409]
    with system.sessions() as db:
        assert db.scalar(select(Batch).where(Batch.hospital_id=="H02")).reserved==600


def test_dispatch_receipt_preserve_batch_and_are_not_repeated(system):
    rid=create(system)
    assert action(system,rid,"Approved").status_code==200
    assert action(system,rid,"Dispatched").status_code==200
    assert action(system,rid,"Dispatched").status_code==409
    assert action(system,rid,"Cancelled","H01").status_code==409
    assert action(system,rid,"Received","H02").status_code==403
    assert action(system,rid,"Received","H01").status_code==200
    assert action(system,rid,"Received","H01").status_code==409
    with system.sessions() as db:
        donor=db.scalar(select(Batch).where(Batch.hospital_id=="H02"))
        received=db.scalar(select(Batch).where(Batch.hospital_id=="H01",Batch.batch_id=="batch-H02"))
        assert (donor.quantity,donor.reserved)==(900,0)
        assert received.quantity==100 and received.expiry==donor.expiry
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.object_id==rid))==4


def test_notification_routing_and_refresh_deduplication(system):
    s=system
    with s.sessions() as db:
        alerts.refresh(db,"H01")
        first=db.scalar(select(func.count()).select_from(Delivery))
        assert first>0
        assert all(d.hospital_id=="H01" for d in db.scalars(select(Delivery)))
        alerts.refresh(db,"H01")
        assert db.scalar(select(func.count()).select_from(Delivery))==first
    rid=create(s,donor="H03")
    with s.sessions() as db:
        incoming=list(db.scalars(select(Delivery).where(Delivery.event_id.like(f"request:{rid}:Requested:%"))))
        assert [d.hospital_id for d in incoming]==["H03"]
    assert action(s,rid,"Approved","H03").status_code==200
    with s.sessions() as db:
        approved=list(db.scalars(select(Delivery).where(Delivery.event_id.like(f"request:{rid}:Approved:%"))))
        assert [d.hospital_id for d in approved]==["H01"]


def test_failed_delivery_is_saved_and_retried(system):
    sent=[]
    with system.sessions() as db:
        alerts.refresh(db,"H01")
        def broken(item):
            raise OSError("mock unavailable")
        assert deliver_pending(db,broken)==0
        rows=list(db.scalars(select(Delivery)))
        assert rows and all(d.state=="Retry" and d.attempts==1 for d in rows)
        for d in rows:
            d.next_attempt=now()-timedelta(seconds=1)
        db.commit()
        assert deliver_pending(db,lambda item:sent.append(item.hospital_id))==len(rows)
        assert sent and set(sent)=={"H01"}
        assert deliver_pending(db,lambda item:sent.append(item.hospital_id))==0


def test_lead_time_risk_and_forecast_limitation(system):
    result=analyze_shortage_risk(1000,14,[100]*7)
    assert result["shortage_risk"]!="LOW" and result["forecast_limited"]
    with system.sessions() as db:
        p=db.scalar(select(StockPolicy).where(StockPolicy.hospital_id=="H02"))
        p.lead_days=14
        p.daily_demand=100
        db.commit()
        values=alerts.assess(db,"H02")
        assert values[0]["severity"]=="HIGH" and values[0]["stockout_in_days"]==10


def test_setup_recovery_totp_replay_reset_and_expiry(system):
    s=system
    with s.sessions() as db:
        user=db.get(Account,"H01")
        user.totp_ready=False
        user.secret=None
        db.commit()
    login=s.client.post("/api/v1/auth/login",json={"username":"H01","password":PASSWORD}).json()
    challenge={"Authorization":"Bearer "+login["challenge"]}
    uri=s.client.post("/api/v1/auth/setup",headers=challenge).json()["uri"]
    otp=pyotp.parse_uri(uri)
    verified=s.client.post("/api/v1/auth/verify",headers=challenge,json={"code":otp.now()}).json()
    assert len(verified["recovery_codes"])==8
    full={"Authorization":"Bearer "+verified["token"]}
    assert s.client.get("/api/v1/auth/me",headers=full).status_code==200
    login2=s.client.post("/api/v1/auth/login",json={"username":"H01","password":PASSWORD}).json()
    ch2={"Authorization":"Bearer "+login2["challenge"]}
    assert s.client.post("/api/v1/auth/verify",headers=ch2,json={"code":otp.now()}).status_code==401
    recovery=verified["recovery_codes"][0]
    recovered=s.client.post("/api/v1/auth/verify",headers=ch2,json={"code":recovery,"recovery":True}).json()
    assert recovered["recovery_codes"]==[]
    with s.sessions() as db:
        codes=list(db.scalars(select(RecoveryCode)))
        assert all(c.code_hash not in verified["recovery_codes"] for c in codes)
        assert sum(c.used for c in codes)==1
        assert db.get(Account,"H01").secret!=otp.secret
    h={"Authorization":"Bearer "+recovered["token"]}
    assert s.client.post("/api/v1/auth/reset",headers=h,json={"password":PASSWORD,"code":verified["recovery_codes"][1],"recovery":True}).status_code==200
    assert s.client.get("/api/v1/auth/me",headers=full).status_code==401
    with s.sessions() as db:
        expired=auth.issue(db,db.get(Account,"H02"),"full")
        db.flush()
        for record in db.scalars(select(LoginSession).where(LoginSession.user_id=="H02")):
            record.expires=now()-timedelta(seconds=1)
        db.commit()
    assert s.client.get("/api/v1/auth/me",headers={"Authorization":"Bearer "+expired}).status_code==401


def test_failed_login_limit_and_logout(system):
    s=system
    for _ in range(5):
        assert s.client.post("/api/v1/auth/login",json={"username":"H01","password":"wrong"}).status_code==401
    assert s.client.post("/api/v1/auth/login",json={"username":"H01","password":PASSWORD}).status_code==429
    assert s.client.post("/api/v1/auth/logout",headers=headers(s,"H02")).status_code==200
    assert s.client.get("/api/v1/auth/me",headers=headers(s,"H02")).status_code==401


def test_acknowledgement_does_not_resolve(system):
    with system.sessions() as db:
        alerts.refresh(db,"H01")
        assert db.get(Alert,"stock:H01:M01").severity=="CRITICAL"
    response=system.client.post("/api/v1/alerts/stock:H01:M01/acknowledge",headers=headers(system))
    assert response.status_code==200
    with system.sessions() as db:
        alerts.refresh(db,"H01")
        assert db.get(Alert,"stock:H01:M01").state=="Acknowledged"
        assert db.scalar(select(func.count()).select_from(Delivery))==1


def test_near_expiry_and_waste_are_distinct(system):
    with system.sessions() as db:
        b=db.scalar(select(Batch).where(Batch.hospital_id=="H02"))
        b.expiry=date.today()+timedelta(days=20)
        b.quantity=50
        db.commit()
        values=alerts.assess(db,"H02")
        assert next(v for v in values if v["kind"]=="Near-expiry batch")["active"]
        assert not next(v for v in values if v["kind"]=="Expected expiry waste")["active"]


def test_dashboard_sign_in_and_assigned_hospital(system, monkeypatch):
    from streamlit.testing.v1 import AppTest
    import requests
    from urllib.parse import urlsplit
    def local_request(method, url, json=None, headers=None, timeout=None):
        return system.client.request(method, urlsplit(url).path, json=json, headers=headers)
    monkeypatch.setattr(requests, "request", local_request)
    view = AppTest.from_file(str(PROJECT_ROOT / "dashboard/dashboard_app.py"), default_timeout=60).run()
    assert not view.exception
    assert not view.dataframe
    view.text_input[0].set_value("H01")
    view.text_input[1].set_value(PASSWORD)
    view.button[0].click().run()
    assert not view.exception
    assert not view.dataframe
    with system.sessions() as db:
        secret = auth.keys().decrypt(db.get(Account,"H01").secret.encode()).decode()
    view.text_input[0].set_value(pyotp.TOTP(secret).now())
    next(b for b in view.button if b.label == "Verify and sign in").click().run()
    assert not view.exception
    assert view.sidebar.subheader[0].value == "H01"
    assert len(view.dataframe) >= 2
    assert not any("Hospital" == w.label for w in view.selectbox)
    next(b for b in view.button if b.label == "Logout").click().run()
    assert not view.exception and not view.dataframe


def test_dashboard_request_controls_follow_permissions(system, monkeypatch):
    from streamlit.testing.v1 import AppTest
    import requests
    from urllib.parse import urlsplit
    monkeypatch.setattr(requests, "request", lambda method,url,json=None,headers=None,timeout=None:
        system.client.request(method,urlsplit(url).path,json=json,headers=headers))
    rid=create(system)
    recipient=AppTest.from_file(str(PROJECT_ROOT / "dashboard/dashboard_app.py"),default_timeout=60)
    recipient.session_state["token"]=system.tokens["H01"]
    recipient.run()
    assert not recipient.exception
    assert "Approved" not in [b.label for b in recipient.button]
    donor=AppTest.from_file(str(PROJECT_ROOT / "dashboard/dashboard_app.py"),default_timeout=60)
    donor.session_state["token"]=system.tokens["H02"]
    donor.run()
    assert not donor.exception
    assert "Approved" in [b.label for b in donor.button]
    assert "Rejected" in [b.label for b in donor.button]
    next(b for b in donor.button if b.label == "Approved").click().run()
    assert not donor.exception
    next(b for b in donor.button if b.label == "Dispatched").click().run()
    assert not donor.exception
    recipient.run()
    next(b for b in recipient.button if b.label == "Received").click().run()
    assert not recipient.exception
    with system.sessions() as db:
        from app.db.operations import SupplyRequest
        assert db.get(SupplyRequest,rid).status == "Received"


def test_migration_preserves_legacy_data_and_is_repeatable(tmp_path):
    import os
    import subprocess
    import sys
    import sqlite3
    path=tmp_path / "legacy.db"
    engine=create_engine("sqlite:///"+str(path))
    Hospital.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(Hospital.__table__.insert().values(id="H01",name="Existing hospital",location="Existing district",patient_capacity=123))
    engine.dispose()
    env=dict(os.environ, DATABASE_URL="sqlite:///"+str(path))
    for _ in range(2):
        result=subprocess.run([sys.executable,"-m","alembic","upgrade","head"],env=env,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT name,patient_capacity FROM hospitals WHERE id='H01'").fetchone()==("Existing hospital",123)
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()==("0001_operations",)
        assert db.execute("SELECT count(*) FROM accounts").fetchone()==(0,)


def test_invalid_quantities_units_and_recipient_expiry_capacity(system):
    s=system
    assert s.client.post("/api/v1/supply/search",headers=headers(s),json={"medicine_id":"M01","quantity":0}).status_code==422
    assert s.client.post("/api/v1/requests",headers=headers(s),json={"donor":"INVALID","medicine_id":"M01","quantity":1,"reason":"Demo"}).status_code==422
    with s.sessions() as db:
        donor=db.scalar(select(StockPolicy).where(StockPolicy.hospital_id=="H02"))
        donor.unit="box"
        other=db.scalar(select(Batch).where(Batch.hospital_id=="H03"))
        other.expiry=date.today()+timedelta(days=2)
        db.commit()
        assert supply.search(db,db.get(Account,"H01"),"M01",500)==[]


def test_alert_severity_increase_and_reactivation(system):
    with system.sessions() as db:
        from app.services.transactions import atomic
        with atomic(db):
            alerts.record(db,"test:H01","H01","Demo","MEDIUM","Demo")
        with atomic(db):
            alerts.record(db,"test:H01","H01","Demo","HIGH","Worse")
        with atomic(db):
            alerts.record(db,"test:H01","H01","Demo","HIGH","Unchanged")
        assert db.scalar(select(func.count()).select_from(Delivery))==2
        with atomic(db):
            db.get(Alert,"test:H01").state="Resolved"
        with atomic(db):
            alerts.record(db,"test:H01","H01","Demo","MEDIUM","Active again")
        assert db.scalar(select(func.count()).select_from(Delivery))==3


def test_legacy_dashboard_entry_uses_secured_view(system, monkeypatch):
    from streamlit.testing.v1 import AppTest
    import requests
    from urllib.parse import urlsplit
    monkeypatch.setattr(requests,"request",lambda method,url,json=None,headers=None,timeout=None:
        system.client.request(method,urlsplit(url).path,json=json,headers=headers))
    view=AppTest.from_file(str(PROJECT_ROOT / "dashboard/app.py"),default_timeout=60).run()
    assert not view.exception and not view.dataframe
    assert view.subheader[0].value=="Administrator sign-in"
    view.session_state["token"]=system.tokens["H01"]
    view.run()
    assert not view.exception
    assert view.sidebar.subheader[0].value=="H01"


def test_disabled_ntfy_and_mock_topic_routing(system, monkeypatch):
    import requests
    from app.services.notifications import ntfy_send
    with system.sessions() as db:
        alerts.refresh(db,"H01")
        assert deliver_pending(db)==0
        assert all(d.state=="Pending" for d in db.scalars(select(Delivery)))
    monkeypatch.setattr(settings,"ntfy_url","https://ntfy.example.test")
    monkeypatch.setattr(settings,"ntfy_token","mock-publisher-token")
    monkeypatch.setattr(settings,"ntfy_topics",{"H01":"mock-h01","H02":"mock-h02"})
    calls=[]
    def mock_post(url, **kwargs):
        calls.append((url,kwargs))
        return SimpleNamespace(raise_for_status=lambda:None)
    monkeypatch.setattr(requests,"post",mock_post)
    with system.sessions() as db:
        deliver_pending(db,ntfy_send)
    assert calls and all(url=="https://ntfy.example.test/mock-h01" for url,_ in calls)
    assert all(call["headers"]["Priority"]=="5" for _,call in calls)


def test_local_configuration_preserves_keys_and_disables_ntfy(tmp_path):
    from app.configure_local import configure
    from dotenv import dotenv_values
    path=tmp_path/".env"
    path.write_text("DATABASE_URL=sqlite:///custom.db\nUNRELATED_SETTING=keep-me\nNTFY_ENABLED=true\n")
    configure(path)
    first=dotenv_values(path)
    configure(path)
    second=dotenv_values(path)
    assert first==second
    assert second["NTFY_ENABLED"]=="false"
    assert second["DATABASE_URL"]=="sqlite:///custom.db"
    assert second["UNRELATED_SETTING"]=="keep-me"
    Fernet(second["TOTP_ENCRYPTION_KEY"].encode())
    assert len(second["AUTH_SIGNING_KEY"])>=32


def test_react_detail_and_audit_are_hospital_scoped(system):
    s=system
    r=s.client.get('/api/v1/medicines/M01/detail?hospital_id=H02',headers=headers(s))
    assert r.status_code==200
    assert r.json()['hospital_id']=='H01'
    assert all(b['batch_id']=='batch-H01' for b in r.json()['batches'])
    assert r.json()['forecast'][0]['quantity']==100
    assert s.client.get('/api/v1/medicines/M01/detail').status_code==401
    rid=create(s)
    assert action(s,rid,'Approved').status_code==200
    r=s.client.get(f'/api/v1/requests/{rid}',headers=headers(s))
    assert [a['action'] for a in r.json()['history']]==['Requested','Approved']
    assert s.client.get(f'/api/v1/requests/{rid}',headers=headers(s,'H03')).status_code==404


def test_browser_refresh_never_creates_notifications(system):
    s=system
    with s.sessions() as db:
        before=db.scalar(select(func.count()).select_from(Delivery))
    for _ in range(3):
        assert s.client.get('/api/v1/alerts',headers=headers(s)).status_code==200
        assert s.client.get('/api/v1/risk',headers=headers(s)).status_code==200
    with s.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Delivery))==before
        alerts.refresh(db,'H01')
        assert db.scalar(select(func.count()).select_from(Delivery))>before
    rows=s.client.get('/api/v1/alerts',headers=headers(s,'H02')).json()
    assert not any(a['id'].startswith('stock:H01:') for a in rows)


def test_explicit_frontend_origins(system):
    for origin,permitted in [('http://localhost:5173',True),('https://untrusted.example',False)]:
        r=system.client.options('/api/v1/requests',headers={'Origin':origin,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'authorization,content-type'})
        assert ('access-control-allow-origin' in r.headers)==permitted
        assert 'access-control-allow-credentials' not in r.headers


def test_stockout_day_matches_depletion_and_zero_stock(system):
    with system.sessions() as db:
        assert next(r for r in alerts.assess(db,'H01') if r['key']=='stock:H01:M01')['stockout_in_days']==0
        p=db.scalar(select(StockPolicy).where(StockPolicy.hospital_id=='H02'))
        p.daily_demand=100
        db.commit()
        assert next(r for r in alerts.assess(db,'H02') if r['key']=='stock:H02:M01')['stockout_in_days']==10


def test_risk_and_supply_never_combine_incompatible_units(system):
    with system.sessions() as db:
        db.add(Batch(batch_id='incompatible-H01',hospital_id='H01',medicine_id='M01',unit='box',
                     quantity=10000,reserved=0,expiry=date.today()+timedelta(days=90)))
        db.commit()
        assert next(r for r in alerts.assess(db,'H01') if r['key']=='stock:H01:M01')['usable_quantity']==0
        options=supply.search(db,db.get(Account,'H01'),'M01',100)
        assert any(r['donor_hospital']=='H02' and r['available_quantity']==100 and r['unit']=='unit' for r in options)
