import os
from dataclasses import dataclass


def _db_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url

@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    database_url: str = _db_url(os.getenv("DATABASE_URL", "sqlite:///./dev.db"))
    session_secret: str = os.getenv("SESSION_SECRET", "dev-session-secret-change-me")
    pin_pepper: str = os.getenv("PIN_PEPPER", "dev-pin-pepper-change-me")
    public_origin: str = os.getenv("PUBLIC_ORIGIN", "http://localhost:8000").rstrip("/")
    bootstrap_admin_login: str = os.getenv("BOOTSTRAP_ADMIN_LOGIN", "admin")
    bootstrap_admin_password: str = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "ChangeMe123!")
    bootstrap_admin_totp_secret: str = os.getenv("BOOTSTRAP_ADMIN_TOTP_SECRET", "JBSWY3DPEHPK3PXP")
    dev_admin_totp_bypass: bool = os.getenv("DEV_ADMIN_TOTP_BYPASS", "true").lower() == "true"

settings = Settings()
if settings.app_env == "production" and not settings.database_url.startswith("postgresql+psycopg://"):
    raise RuntimeError("APP_ENV=production requires PostgreSQL DATABASE_URL")
