"""Explicit local setup and worker commands. Never run external delivery in tests."""
import argparse
import getpass
import time
import uuid
from datetime import date, timedelta
import pandas as pd
from sqlalchemy import select
from app.db.database import SessionLocal
from app.db.models import Hospital, Medicine
from app.db.operations import Account, Batch, StockPolicy, Audit
from app.services.auth import hasher
from app.services.transactions import atomic
from app.services.notifications import deliver_pending, ntfy_send
from app.core.config import settings


def seed(db, csv):
    df = pd.read_csv(csv)
    df["date"] = pd.to_datetime(df["date"])
    anchor = df["date"].max().date()
    shift = date.today() - anchor
    with atomic(db):
        for hid in df.hospital_id.unique():
            if not db.get(Hospital, hid):
                db.add(Hospital(id=hid, name=f"Demo hospital {hid}", location="Metropolitan Health District", patient_capacity=500))
        for mid, group in df.groupby("medicine_id"):
            if not db.get(Medicine, mid):
                db.add(Medicine(id=mid, name=str(group.iloc[-1].medicine_name), category="Demo medicine"))
        db.flush()
        for (hid, mid), group in df.groupby(["hospital_id", "medicine_id"]):
            if db.scalar(select(StockPolicy).where(StockPolicy.hospital_id == hid, StockPolicy.medicine_id == mid)):
                continue
            group = group.sort_values("date")
            latest = group.iloc[-1]
            db.add(StockPolicy(hospital_id=hid, medicine_id=mid, daily_demand=float(group.daily_demand.tail(14).mean()),
                               lead_days=int(latest.supplier_lead_time_days), safety_days=3, forecast_days=30, unit="unit"))
            db.add(Batch(batch_id=f"DEMO-{hid}-{mid}", hospital_id=hid, medicine_id=mid,
                         expiry=pd.to_datetime(latest.expiry_date).date() + shift,
                         quantity=max(0, int(latest.current_stock)), reserved=0, unit="unit"))
        db.add(Audit(user_id="local-operator", action="synthetic_csv_conversion", object_id=f"anchor:{anchor};shift:{shift.days}"))
    print("Imported missing demo policies and stock. Existing stock was preserved.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seed-demo", "create-account", "worker", "manual-notify"])
    parser.add_argument("--hospital")
    parser.add_argument("--username")
    parser.add_argument("--csv", default="data/medical_supply_20_medicines.csv")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.command == "seed-demo":
            seed(db, args.csv)
        elif args.command == "create-account":
            if not args.hospital or not args.username or not db.get(Hospital, args.hospital):
                parser.error("Set a valid --hospital and --username.")
            password = getpass.getpass("New password (at least 12 characters): ")
            if len(password) < 12:
                parser.error("Use at least 12 characters.")
            if db.scalar(select(Account).where(Account.username == args.username)):
                parser.error("Username already exists.")
            with atomic(db):
                db.add(Account(id=str(uuid.uuid4()), username=args.username, password_hash=hasher.hash(password), hospital_id=args.hospital))
                db.add(Audit(user_id="local-operator", action="account_created", object_id=args.username))
            print("Account created. Complete authenticator setup at sign-in.")
        elif args.command == "manual-notify":
            if not settings.ntfy_enabled or args.hospital not in settings.ntfy_topics:
                parser.error("Enable ntfy and set a protected topic for --hospital.")
            from types import SimpleNamespace
            ntfy_send(SimpleNamespace(hospital_id=args.hospital, message="Explicit manual demo notification.", severity="LOW"))
            print("Manual notification sent.")
        else:
            while True:
                from app.services.alerts import refresh
                for hospital in list(db.scalars(select(Hospital))):
                    refresh(db, hospital.id)
                deliver_pending(db)
                if args.once:
                    break
                time.sleep(5)


if __name__ == "__main__":
    main()
