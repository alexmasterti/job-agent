from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration. Fails fast at startup if any required var is missing."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    secret_key: str = Field(min_length=32)

    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    anthropic_api_key: str
    llm_daily_budget_usd: float = 5.0

    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str = "http://localhost:8080/auth/callback"
    allowed_google_emails: str  # comma-separated

    sentry_dsn: str = ""
    port: int = 8080

    @property
    def allowed_emails(self) -> list[str]:
        return [e.strip().lower() for e in self.allowed_google_emails.split(",") if e.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"
