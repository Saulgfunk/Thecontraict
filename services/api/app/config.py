from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"

    database_url: str = "postgresql+psycopg://contraict:contraict@localhost:5432/contraict"
    redis_url: str = "redis://localhost:6379/0"

    # "dev": trust the X-Dev-User-Email header (local development only).
    # "clerk": verify Clerk-issued JWTs.
    auth_mode: Literal["dev", "clerk"] = "dev"
    clerk_issuer: str = ""
    clerk_jwks_url: str = ""
    clerk_authorized_parties: list[str] = []

    cors_origins: list[str] = ["http://localhost:3000"]

    # "local" stores files on disk (development/tests); "s3" uses S3 or MinIO.
    storage_backend: Literal["local", "s3"] = "local"
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

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.environment == "production" and settings.auth_mode == "dev":
        raise RuntimeError("AUTH_MODE=dev is not allowed in production")
    return settings
