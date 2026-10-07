import os
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"

    database_url: str = "postgresql+psycopg://contraict:contraict@localhost:5432/contraict"
    # The app switches to this role (if the database user may) so Row-Level Security
    # always applies, even when the login user could bypass it (common on hosted Postgres).
    db_app_role: str = "contraict_app"
    redis_url: str = "redis://localhost:6379/0"

    # "dev": trust the X-Dev-User-Email header (local development only).
    # "clerk": verify Clerk-issued JWTs.
    auth_mode: Literal["dev", "clerk"] = "dev"
    clerk_issuer: str = ""
    clerk_jwks_url: str = ""
    clerk_authorized_parties: list[str] = []

    cors_origins: list[str] = ["http://localhost:3000"]

    # "local" stores files on disk (development/tests); "s3" uses S3 or MinIO;
    # "database" keeps them in Postgres (small deployments without object storage).
    storage_backend: Literal["local", "s3", "database"] = "local"
    local_storage_dir: str = ".storage"
    max_upload_mb: int = 50
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_bucket: str = "contraict-documents"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    extraction_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"

    chat_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"

    # Run Celery tasks inline (tests, or development without a worker).
    tasks_eager: bool = False

    # Public URLs, used in emails and calendar feeds.
    app_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"

    # "console" logs emails (development); "smtp" or "postmark" send them.
    email_backend: Literal["console", "smtp", "postmark"] = "console"
    email_from: str = "TheContrAIct <reminders@localhost>"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    postmark_server_token: str = ""

    # Shared secret for the scheduler (e.g. GitHub Actions) calling /internal/jobs/*.
    # Empty disables those endpoints.
    cron_secret: str = ""

    @field_validator("database_url")
    @classmethod
    def _psycopg_driver(cls, v: str) -> str:
        """Accept the plain URLs hosting providers hand out (postgres://, postgresql://)."""
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix) :]
        return v

    @model_validator(mode="after")
    def _derive_urls(self) -> "Settings":
        """Fill in what follows from the public URLs, so a deployment sets fewer values."""
        if self.api_url == "http://localhost:8000" and os.environ.get("RENDER_EXTERNAL_URL"):
            self.api_url = os.environ["RENDER_EXTERNAL_URL"]
        if self.clerk_issuer and not self.clerk_jwks_url:
            self.clerk_jwks_url = self.clerk_issuer.rstrip("/") + "/.well-known/jwks.json"
        app_origin = self.app_url.rstrip("/")
        if app_origin not in self.cors_origins:
            self.cors_origins = [*self.cors_origins, app_origin]
        if self.auth_mode == "clerk" and app_origin not in self.clerk_authorized_parties:
            self.clerk_authorized_parties = [*self.clerk_authorized_parties, app_origin]
        return self

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.environment == "production" and settings.auth_mode == "dev":
        raise RuntimeError("AUTH_MODE=dev is not allowed in production")
    return settings
