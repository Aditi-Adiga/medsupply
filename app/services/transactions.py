from contextlib import contextmanager
from sqlalchemy import text


@contextmanager
def atomic(db):
    """Serialize prototype SQLite writers before reading stock or OTP counters."""
    if db.bind.dialect.name != "sqlite":
        raise RuntimeError("This prototype requires SQLite. Port locking before changing databases.")
    db.commit()  # End the read-only authentication transaction.
    db.execute(text("BEGIN IMMEDIATE"))
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise
