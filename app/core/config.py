from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    app_name: str = "Medical Supply Intelligence"
    app_version: str = "1.0.0"
    debug: bool = Field(default=False, validation_alias="MSI_DEBUG")

    database_url: str = "sqlite:///./medical_supply.db"
    auth_signing_key: str = ""
    totp_encryption_key: str = ""
    session_minutes: int = 30
    ntfy_enabled: bool = False
    ntfy_url: str = ""
    ntfy_token: str = ""
    ntfy_topics: dict[str, str] = {}
    frontend_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
