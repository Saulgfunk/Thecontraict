import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://contraict:contraict@localhost:5432/contraict_test"
)
os.environ["ENVIRONMENT"] = "test"
os.environ["AUTH_MODE"] = "dev"
os.environ["TASKS_EAGER"] = "true"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["LOCAL_STORAGE_DIR"] = os.path.join(os.path.dirname(__file__), "..", ".storage-test")
os.environ["ANTHROPIC_API_KEY"] = ""

from collections.abc import Callable, Iterator  # noqa: E402

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from alembic import command  # noqa: E402
from app.main import app  # noqa: E402

TABLES = (
    "chat_messages, chat_threads, notifications, reminder_logs, calendar_feeds, "
    "deadlines, payment_terms, date_rules, extraction_runs, clauses, documents, contracts, "
    "audit_events, workspace_memberships, workspaces, organization_memberships, "
    "organizations, users, stored_files"
)

# The app's engine switches to the restricted role, which may not TRUNCATE: clean up as
# the login user (the table owner).
owner_engine = create_engine(os.environ["DATABASE_URL"], poolclass=NullPool)


@pytest.fixture(scope="session", autouse=True)
def _migrate() -> None:
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _clean_db() -> Iterator[None]:
    yield
    with owner_engine.begin() as conn:
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
