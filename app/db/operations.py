"""Persistent prototype records. Inventory snapshots remain historical data."""
from datetime import datetime, date, timezone
from sqlalchemy import String, Integer, Float, Date, DateTime, Boolean, ForeignKey, JSON, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"))
    role: Mapped[str] = mapped_column(String, default="hospital_admin")
    status: Mapped[str] = mapped_column(String, default="active")
    totp_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    secret: Mapped[str | None] = mapped_column(String)
    last_step: Mapped[int] = mapped_column(Integer, default=-1)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    version: Mapped[int] = mapped_column(Integer, default=0)


class RecoveryCode(Base):
    __tablename__ = "recovery_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    code_hash: Mapped[str] = mapped_column(String)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    stage: Mapped[str] = mapped_column(String)
    expires: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer)


class StockPolicy(Base):
    __tablename__ = "stock_policies"
    __table_args__ = (UniqueConstraint("hospital_id", "medicine_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"))
    medicine_id: Mapped[str] = mapped_column(ForeignKey("medicines.id"))
    unit: Mapped[str] = mapped_column(String, default="unit")
    daily_demand: Mapped[float] = mapped_column(Float)
    lead_days: Mapped[int] = mapped_column(Integer)
    safety_days: Mapped[int] = mapped_column(Integer, default=3)
    forecast_days: Mapped[int] = mapped_column(Integer, default=30)


class Batch(Base):
    __tablename__ = "stock_batches"
    __table_args__ = (CheckConstraint("quantity >= 0 AND reserved >= 0 AND reserved <= quantity"), UniqueConstraint("hospital_id", "batch_id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[str] = mapped_column(String)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"))
    medicine_id: Mapped[str] = mapped_column(ForeignKey("medicines.id"))
    unit: Mapped[str] = mapped_column(String, default="unit")
    expiry: Mapped[date] = mapped_column(Date)
    quantity: Mapped[int] = mapped_column(Integer)
    reserved: Mapped[int] = mapped_column(Integer, default=0)


class SupplyRequest(Base):
    __tablename__ = "supply_requests"
    __table_args__ = (CheckConstraint("requested > 0 AND approved >= 0 AND approved <= requested"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    recipient: Mapped[str] = mapped_column(ForeignKey("hospitals.id"))
    donor: Mapped[str] = mapped_column(ForeignKey("hospitals.id"))
    medicine_id: Mapped[str] = mapped_column(ForeignKey("medicines.id"))
    requested: Mapped[int] = mapped_column(Integer)
    approved: Mapped[int] = mapped_column(Integer, default=0)
    allocations: Mapped[list] = mapped_column(JSON, default=list)
    urgency: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="Requested")
    in_transit: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated: Mapped[datetime] = mapped_column(DateTime, default=now)
    created_by: Mapped[str] = mapped_column(ForeignKey("accounts.id"))


class Audit(Base):
    __tablename__ = "audit_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    object_id: Mapped[str] = mapped_column(String)
    at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Alert(Base):
    __tablename__ = "hospital_alerts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"))
    kind: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String, default="Active")
    generation: Mapped[int] = mapped_column(Integer, default=1)
    updated: Mapped[datetime] = mapped_column(DateTime, default=now)


class Delivery(Base):
    __tablename__ = "notification_deliveries"
    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey("hospital_alerts.id"))
    hospital_id: Mapped[str] = mapped_column(ForeignKey("hospitals.id"))
    message: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String, default="Pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt: Mapped[datetime] = mapped_column(DateTime, default=now)
    error: Mapped[str | None] = mapped_column(String)
