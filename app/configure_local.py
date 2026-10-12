"""Configure the local demo without printing keys or replacing valid keys."""
import secrets
from pathlib import Path
from cryptography.fernet import Fernet
from dotenv import dotenv_values, set_key


def configure(path=Path(".env")):
    values = dotenv_values(path) if path.exists() else {}
    updates = {"NTFY_ENABLED": "false", "MSI_DEBUG": "false"}
    if not values.get("DATABASE_URL"):
        updates["DATABASE_URL"] = "sqlite:///./medical_supply.db"
    signing = values.get("AUTH_SIGNING_KEY", "") or ""
    if not signing or signing.startswith("replace-"):
        updates["AUTH_SIGNING_KEY"] = secrets.token_urlsafe(48)
    elif len(signing) < 32:
        raise ValueError("Existing AUTH_SIGNING_KEY is too short. Set at least 32 random characters.")
    encryption = values.get("TOTP_ENCRYPTION_KEY", "") or ""
    if not encryption or encryption.startswith("replace-"):
        updates["TOTP_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    else:
        Fernet(encryption.encode())  # Reject invalid keys. Never silently rotate a real key.
    if not values.get("SESSION_MINUTES"):
        updates["SESSION_MINUTES"] = "30"
    path.touch(exist_ok=True)
    for key, value in updates.items():
        set_key(str(path), key, value)
    print("Local settings saved. Existing valid keys and database settings were preserved.")
    print("Real ntfy delivery is disabled. Restart running services to load these settings.")


if __name__ == "__main__":
    configure()
