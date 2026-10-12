"""Dedicated browser-test server. Never opens the user's database or sends ntfy."""
import os
import sys
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
RUN = ROOT / '.verification'
RUN.mkdir(exist_ok=True)
ENV = RUN / 'react-e2e.env'

if len(sys.argv) > 1:
    from dotenv import load_dotenv
    load_dotenv(ENV, override=True)
    from app.db.database import SessionLocal
    from app.db.operations import Account, Batch
    from app.services.auth import keys
    from sqlalchemy import select
    import pyotp
    import json
    with SessionLocal() as db:
        if sys.argv[1] == 'code':
            user = db.get(Account, sys.argv[2])
            print(pyotp.TOTP(keys().decrypt(user.secret.encode()).decode()).now())
        elif sys.argv[1] == 'stock':
            b = db.scalar(select(Batch).where(Batch.hospital_id == 'H02', Batch.medicine_id == 'M01'))
            print(json.dumps({'quantity': b.quantity, 'reserved': b.reserved}))
    sys.exit(0)

import secrets
from cryptography.fernet import Fernet
values = {'DATABASE_URL': 'sqlite:///' + (RUN / f'react-e2e-{uuid.uuid4().hex}.db').as_posix(),
          'AUTH_SIGNING_KEY': secrets.token_urlsafe(48), 'TOTP_ENCRYPTION_KEY': Fernet.generate_key().decode(),
          'NTFY_ENABLED': 'false', 'FRONTEND_ORIGINS': '["http://127.0.0.1:5173"]'}
os.environ.update(values)
ENV.write_text('\n'.join(f'{k}={v}' for k, v in values.items()))
from app.db.database import Base, engine, SessionLocal
from app.db.models import Hospital, Medicine
from app.db.operations import Account, Batch, StockPolicy
from app.services.auth import hasher
from app.manage import seed
from app.services.alerts import refresh
from sqlalchemy import select
from datetime import date, timedelta
with SessionLocal() as db:
    Base.metadata.create_all(engine)
    seed(db, str(ROOT / 'data/medical_supply_20_medicines.csv'))
    for hid in ('H01', 'H02'):
        db.add(Account(id=hid, username='test-' + hid, password_hash=hasher.hash(os.environ['MSI_E2E_PASSWORD']), hospital_id=hid))
    for b in db.scalars(select(Batch).where(Batch.medicine_id == 'M01')):
        b.quantity = 1000 if b.hospital_id == 'H02' else 0
        b.expiry = date.today() + timedelta(days=90)
    for p in db.scalars(select(StockPolicy).where(StockPolicy.medicine_id == 'M01')):
        p.daily_demand = 10 if p.hospital_id == 'H02' else 100
        p.lead_days = 7
    db.commit()
    refresh(db, 'H01')
    refresh(db, 'H02')
import uvicorn
uvicorn.run('app.main:app', host='127.0.0.1', port=8001, access_log=False)
