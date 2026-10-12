"""Run one local worker. Save failures without changing alerts or orders."""
from datetime import timedelta
from urllib.parse import quote
import requests
from types import SimpleNamespace
from sqlalchemy import select
from app.core.config import settings
from app.db.operations import Delivery, now
from app.services.alerts import RANK
from app.services.transactions import atomic


def ntfy_send(delivery):
    topic = settings.ntfy_topics.get(delivery.hospital_id)
    if not topic or not settings.ntfy_token or not settings.ntfy_url.startswith("https://"):
        raise ValueError("Set an HTTPS ntfy server, protected topic, and publishing token.")
    response = requests.post(f"{settings.ntfy_url.rstrip('/')}/{quote(topic, safe='')}",
                             data=delivery.message.encode(),
                             headers={"Authorization": f"Bearer {settings.ntfy_token}",
                                      "Priority": str(RANK[delivery.severity]),
                                      "Title": "Medical supply alert"}, timeout=10)
    response.raise_for_status()


def deliver_pending(db, sender=None):
    if sender is None and not settings.ntfy_enabled:
        return 0
    sender = sender or ntfy_send
    count = 0
    for _ in range(20):
        with atomic(db):
            item = db.scalar(select(Delivery).where(Delivery.state != "Sent", Delivery.next_attempt <= now()).limit(1))
            if not item:
                break
            item.attempts += 1
            item.state = "Sending"
            item.next_attempt = now() + timedelta(seconds=60)
            event = item.event_id
            payload = SimpleNamespace(hospital_id=item.hospital_id, message=item.message, severity=item.severity)
        error = None
        try:
            sender(payload)  # Network I/O must not hold a stock write lock.
        except Exception as exc:
            error = type(exc).__name__
        with atomic(db):
            item = db.get(Delivery, event)
            if error is None:
                item.state = "Sent"
                item.error = None
                count += 1
            else:
                item.state = "Retry"
                item.error = error  # Do not save credentials from HTTP errors.
                item.next_attempt = now() + timedelta(seconds=min(3600, 30 * 2 ** min(item.attempts, 7)))
    return count
