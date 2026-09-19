"""Small, explicit deployment configuration. All distances are metres."""

from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql://qr:qr_local_demo@postgres:5432/qr_chuvsu"
    public_base_url: str = "http://localhost"
    app_secret: str = ""
    secret_file: Path = Path("/data/app-secret")
    cookie_secure: bool = False
    timezone: str = "Europe/Moscow"
    ip_rate_limit: int = Field(default=120, ge=1)
    rate_window_seconds: int = Field(default=60, ge=1)
    schedule_file: Path = Path(__file__).parent / "schedule.json"

    @field_validator("public_base_url")
    @classmethod
    def valid_origin(cls, value: str) -> str:
        from urllib.parse import urlsplit

        url = urlsplit(value)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username:
            raise ValueError("PUBLIC_BASE_URL must be an HTTP(S) origin")
        if url.path not in {"", "/"} or url.query or url.fragment:
            raise ValueError("PUBLIC_BASE_URL must not contain a path, query or fragment")
        return value.rstrip("/")

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @field_validator("app_secret")
    @classmethod
    def strong_secret(cls, value: str) -> str:
        if value and len(value) < 32:
            raise ValueError("APP_SECRET must contain at least 32 characters")
        return value
