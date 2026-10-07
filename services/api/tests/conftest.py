import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://contraict:contraict@localhost:5432/contraict_test"
)
os.environ["ENVIRONMENT"] = "test"
os.environ["AUTH_MODE"] = "dev"

from collections.abc import Callable, Iterator  # noqa: E402

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402

TABLES = (
    "audit_events, workspace_memberships, workspaces, organization_memberships, "
    "organizations, users"
)


@pytest.fixture(scope="session", autouse=True)
def _migrate() -> None:
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _clean_db() -> Iterator[None]:
    yield
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} CASCADE"))


Client = Callable[[str], TestClient]


@pytest.fixture
def client_as() -> Client:
    """Return a test client authenticated (dev mode) as the given email."""

    def make(email: str) -> TestClient:
        client = TestClient(app)
        client.headers["X-Dev-User-Email"] = email
        return client

    return make
