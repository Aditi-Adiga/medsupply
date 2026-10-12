"""Argon2 passwords, encrypted PyOTP secrets, and revocable PyJWT sessions."""
import secrets
import time
import uuid
from datetime import timedelta
import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select, delete
from app.core.config import settings
from app.db.operations import Account, RecoveryCode, LoginSession, Audit, now
from app.services.transactions import atomic

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


def keys():
    if len(settings.auth_signing_key) < 32 or not settings.totp_encryption_key:
        raise HTTPException(503, "Set the sign-in and encryption keys in the environment.")
    return Fernet(settings.totp_encryption_key.encode())


def password_ok(encoded, password):
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def issue(db, user, stage):
    duration = 5 if stage == "challenge" else settings.session_minutes
    record = LoginSession(id=str(uuid.uuid4()), user_id=user.id, stage=stage,
                          expires=now() + timedelta(minutes=duration), version=user.version)
    db.add(record)
    return jwt.encode({"sub": user.id, "jti": record.id, "exp": record.expires,
                       "stage": stage, "iss": "medical-supply"}, settings.auth_signing_key, algorithm="HS256")


def authenticate(db, token, stage="full"):
    keys()
    try:
        payload = jwt.decode(token, settings.auth_signing_key, algorithms=["HS256"],
                             issuer="medical-supply", options={"require": ["exp", "sub", "jti", "stage"]})
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Sign in again. Your session is invalid or expired.")
    record = db.get(LoginSession, payload["jti"])
    user = db.get(Account, payload["sub"])
    if (not record or not user or record.user_id != user.id or record.revoked or record.expires <= now()
            or record.version != user.version or user.status != "active" or user.role != "hospital_admin"
            or record.stage != stage or payload["stage"] != stage
            or (stage == "full" and not user.totp_ready)):
        raise HTTPException(401, "Complete two-factor sign-in.")
    return user, record


def allowed(user, hospital):
    if str(hospital) != user.hospital_id:
        raise HTTPException(403, "You can access only your assigned hospital.")


def check_lock(user):
    if user.locked_until and user.locked_until > now():
        raise HTTPException(429, "Too many attempts. Wait 15 minutes.")


def failure(user):
    user.failures += 1
    if user.failures >= 5:
        user.locked_until = now() + timedelta(minutes=15)
        user.failures = 0


def login(db, username, password):
    keys()
    result = None
    with atomic(db):
        user = db.scalar(select(Account).where(Account.username == username))
        if user:
            check_lock(user)
        valid = password_ok(user.password_hash if user else DUMMY_HASH, password)
        if user and valid and user.status == "active" and user.role == "hospital_admin":
            result = {"challenge": issue(db, user, "challenge"), "setup_required": not user.totp_ready}
        elif user:
            failure(user)
    if result is None:
        raise HTTPException(401, "Username or password is incorrect.")
    return result


def setup(db, token):
    with atomic(db):
        user, _ = authenticate(db, token, "challenge")
        check_lock(user)
        if user.totp_ready:
            raise HTTPException(409, "Two-factor access is already set up.")
        if not user.secret:
            user.secret = keys().encrypt(pyotp.random_base32().encode()).decode()
        secret = keys().decrypt(user.secret.encode()).decode()
        return pyotp.TOTP(secret).provisioning_uri(user.username, issuer_name="Medical Supply Intelligence")


def consume_code(db, user, code, recovery=False):
    if recovery and user.totp_ready:
        for item in db.scalars(select(RecoveryCode).where(RecoveryCode.user_id == user.id, RecoveryCode.used == False)):
            if password_ok(item.code_hash, code):
                item.used = True
                return True
        return False
    if not user.secret or not code.isdigit() or len(code) != 6:
        return False
    totp = pyotp.TOTP(keys().decrypt(user.secret.encode()).decode())
    current = int(time.time()) // 30
    for step in (current - 1, current, current + 1):
        if step > user.last_step and secrets.compare_digest(totp.at(step * 30), code):
            user.last_step = step
            return True
    return False


def verify(db, token, code, recovery=False):
    result = None
    with atomic(db):
        user, record = authenticate(db, token, "challenge")
        check_lock(user)
        if consume_code(db, user, code, recovery):
            codes = []
            if not user.totp_ready:
                codes = [secrets.token_hex(10) for _ in range(8)]
                db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
                for value in codes:
                    db.add(RecoveryCode(user_id=user.id, code_hash=hasher.hash(value)))
            user.totp_ready = True
            user.failures = 0
            user.locked_until = None
            record.revoked = True
            db.add(Audit(user_id=user.id, action="two_factor_sign_in", object_id=user.id))
            result = {"token": issue(db, user, "full"), "recovery_codes": codes}
        else:
            failure(user)
    if result is None:
        raise HTTPException(401, "Code is incorrect or already used. Use a new code.")
    return result


def reset(db, token, password, code, recovery=False):
    success = False
    with atomic(db):
        user, _ = authenticate(db, token, "full")
        check_lock(user)
        if password_ok(user.password_hash, password) and consume_code(db, user, code, recovery):
            user.secret = None
            user.totp_ready = False
            user.last_step = -1
            user.version += 1
            db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
            db.add(Audit(user_id=user.id, action="two_factor_reset", object_id=user.id))
            success = True
        else:
            failure(user)
    if not success:
        raise HTTPException(401, "Password or second code is incorrect.")


def logout(db, token):
    with atomic(db):
        _, record = authenticate(db, token)
        record.revoked = True
