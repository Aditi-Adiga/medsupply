import re
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import Medicine, Hospital
from app.db.operations import Batch, SupplyRequest, Alert, Audit
from app.services import auth, supply, alerts
from app.services.transactions import atomic

router = APIRouter()
bearer = HTTPBearer(auto_error=False)
DB = Annotated[Session, Depends(get_db)]


def token(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "Sign in first.")
    return credentials.credentials


def current_user(db: DB, value: Annotated[str, Depends(token)]):
    return auth.authenticate(db, value)[0]


User = Annotated[object, Depends(current_user)]
Token = Annotated[str, Depends(token)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class Code(Input):
    code: str = Field(min_length=1, max_length=80)
    recovery: bool = False


class Reset(Code):
    password: str = Field(max_length=200)


class Search(Input):
    medicine_id: str
    quantity: int = Field(gt=0, le=1000000)


class Request(Search):
    donor: str
    recipient: str | None = None
    urgency: str = Field(default="Routine", pattern="^(Routine|Urgent)$")
    reason: str = Field(min_length=1, max_length=500)


class Action(Input):
    status: str
    quantity: int | None = Field(default=None, gt=0)


class Question(Input):
    question: str = Field(min_length=1, max_length=500)


@router.post("/auth/login")
def login(body: Login, db: DB):
    return auth.login(db, body.username, body.password)


@router.post("/auth/setup")
def setup(db: DB, value: Token):
    import base64
    import io
    import qrcode
    uri = auth.setup(db, value)
    image = io.BytesIO()
    qrcode.make(uri).save(image, format="PNG")
    return {"uri": uri, "qr": "data:image/png;base64," + base64.b64encode(image.getvalue()).decode(),
            "message": "Scan the QR code. The second code is a time-based one-time password (TOTP)."}


@router.post("/auth/verify")
def verify(body: Code, db: DB, value: Token):
    return auth.verify(db, value, body.code, body.recovery)


@router.post("/auth/reset")
def reset(body: Reset, db: DB, value: Token):
    auth.reset(db, value, body.password, body.code, body.recovery)
    return {"message": "Two-factor access was reset. Sign in and set it up again."}


@router.post("/auth/logout")
def logout(db: DB, value: Token):
    auth.logout(db, value)
    return {"message": "Signed out."}


@router.get("/auth/me")
def me(db: DB, user: User, value: Token):
    from app.core.config import settings
    _, session = auth.authenticate(db, value)
    return {"id": user.id, "username": user.username, "hospital_id": user.hospital_id,
            "hospital_name": db.get(Hospital, user.hospital_id).name, "role": user.role,
            "two_factor_ready": user.totp_ready, "external_notifications_enabled": settings.ntfy_enabled,
            "session_expires_at": session.expires.isoformat() + "Z"}


def inventory_data(db, hospital):
    return [{"batch_id": b.batch_id, "medicine_id": b.medicine_id, "unit": b.unit,
             "quantity": b.quantity, "reserved": b.reserved, "expiry": b.expiry}
            for b in db.scalars(select(Batch).where(Batch.hospital_id == hospital))]


@router.get("/hospitals/{hospital}/inventory")
def inventory(hospital: str, db: DB, user: User):
    auth.allowed(user, hospital)
    return inventory_data(db, user.hospital_id)


@router.get("/inventory/export")
def export(db: DB, user: User):
    return inventory_data(db, user.hospital_id)


@router.get("/medicines")
def medicines(db: DB, user: User):
    return [{"id": m.id, "name": m.name} for m in db.scalars(select(Medicine))]


@router.get("/risk")
def risk(db: DB, user: User):
    return alerts.assess(db, user.hospital_id)


@router.get("/alerts")
def alert_list(db: DB, user: User):
    return alerts.list_alerts(db, user.hospital_id)


@router.post("/alerts/{alert_id:path}/acknowledge")
def acknowledge(alert_id: str, db: DB, user: User):
    with atomic(db):
        alert = db.get(Alert, alert_id)
        if not alert or alert.hospital_id != user.hospital_id:
            raise HTTPException(404, "Alert not found.")
        if alert.state == "Active":
            alert.state = "Acknowledged"
            db.add(Audit(user_id=user.id, action="Acknowledged", object_id=alert.id))
    return {"message": "Alert acknowledged. The supply problem can still be active."}


@router.post("/supply/search")
def search(body: Search, db: DB, user: User):
    return {"recommendations": supply.search(db, user, body.medicine_id, body.quantity),
            "message": "Select a source to request stock. Delivery times are estimates without live traffic."}


@router.post("/requests")
def create(body: Request, db: DB, user: User):
    return supply.create_request(db, user, body.donor, body.medicine_id, body.quantity, body.urgency, body.reason, body.recipient)


@router.get("/requests")
def requests_list(db: DB, user: User):
    return [supply.request_view(r) for r in db.scalars(select(SupplyRequest).where(
        or_(SupplyRequest.recipient == user.hospital_id, SupplyRequest.donor == user.hospital_id)))]


@router.get("/requests/{request_id}")
def request_detail(request_id: str, db: DB, user: User):
    r = db.get(SupplyRequest, request_id)
    supply.participant(user, r)
    value = supply.request_view(r)
    value["history"] = [{"action": a.action, "user_id": a.user_id, "at": a.at}
                        for a in db.scalars(select(Audit).where(Audit.object_id == r.id).order_by(Audit.at, Audit.id))]
    return value


@router.get("/medicines/{medicine_id}/detail")
def medicine_detail(medicine_id: str, db: DB, user: User):
    from app.services.medicine_detail import detail
    return detail(db, user.hospital_id, medicine_id)


@router.post("/requests/{request_id}/action")
def request_action(request_id: str, body: Action, db: DB, user: User):
    return supply.action(db, user, request_id, body.status, body.quantity)


@router.post("/assistant")
def assistant(body: Question, db: DB, user: User):
    question = body.question
    hospitals = re.findall(r"\bH\d+\b", question.upper())
    if any(h != user.hospital_id for h in hospitals):
        raise HTTPException(403, "The assistant cannot show another hospital's private data. Use supply search.")
    meds = list(db.scalars(select(Medicine)))
    medicine = next((m for m in meds if m.name.lower() in question.lower() or re.search(rf"\b{re.escape(m.id)}\b", question, re.I)), None)
    qty = re.search(r"\b(\d+)\s*(?:units?|tablets?)\b", question, re.I)
    if medicine and qty:
        number = int(qty.group(1))
        if number > 1000000:
            raise HTTPException(422, "Use a quantity of at most 1000000.")
        results = supply.search(db, user, medicine.id, number)
        return {"message": "Select a donor to submit a request. Delivery times are estimates without live traffic." if results else "No safe transfer is available.",
                "recommendations": results}
    return {"message": "Ask for a medicine and quantity. Example: We need 500 units of Paracetamol. Which hospital can supply them?"}


@router.get("/intelligence/summary")
def intelligence_summary(db: DB, user: User):
    from app.services.intelligence import summary
    return summary(db, user.hospital_id)
