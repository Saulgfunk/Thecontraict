"""What a hosted deployment relies on: the restricted database role, the Postgres file
store, the scheduler endpoint and settings derived from the public URLs."""

from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app import email
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.storage import DatabaseStorage
from tests.conftest import Client
from tests.test_api import ALICE, create_org, create_workspace
from tests.test_manual_entry import MANUAL


def test_connections_use_the_restricted_role() -> None:
    with SessionLocal() as db:
        assert db.scalar(text("SELECT current_user")) == "contraict_app"
        assert not db.scalar(
            text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        )


def test_database_file_store() -> None:
    store = DatabaseStorage()
    store.put("org/ws/c/d/file.pdf", b"%PDF-1", "application/pdf")
    assert store.get("org/ws/c/d/file.pdf") == b"%PDF-1"
    store.put("org/ws/c/d/file.pdf", b"%PDF-2", "application/pdf")  # overwrite
    assert store.get("org/ws/c/d/file.pdf") == b"%PDF-2"
    store.delete("org/ws/c/d/file.pdf")
    with pytest.raises(FileNotFoundError):
        store.get("org/ws/c/d/file.pdf")


@pytest.fixture
def cron_secret() -> str:
    settings = get_settings()
    settings.cron_secret = "s3cret-value"
    yield settings.cron_secret
    settings.cron_secret = ""


def test_scheduler_endpoint(client_as: Client, cron_secret: str) -> None:
    org_id = create_org(client_as)
    ws_id = create_workspace(client_as, org_id, "Client A Ltd")
    # Started ~10 months ago with a 12-month term: its notice deadline is weeks away.
    started = (date.today() - timedelta(days=300)).isoformat()
    client_as(ALICE).post(
        f"/organizations/{org_id}/workspaces/{ws_id}/contracts/manual",
        json={**MANUAL, "effective_date": started, "initial_term_amount": 12},
    )
    anon = client_as("nobody@example.com")
    assert anon.post("/internal/jobs/reminders").status_code == 404
    assert (
        anon.post("/internal/jobs/reminders", headers={"X-Cron-Secret": "wrong"}).status_code == 404
    )
    email.outbox.clear()
    res = anon.post("/internal/jobs/reminders", headers={"X-Cron-Secret": cron_secret})
    assert res.status_code == 200 and res.json()["sent"] >= 1
    assert (
        anon.post("/internal/jobs/digests", headers={"X-Cron-Secret": cron_secret}).status_code
        == 200
    )
    assert (
        anon.post("/internal/jobs/other", headers={"X-Cron-Secret": cron_secret}).status_code == 422
    )


def test_disabled_without_a_secret(client_as: Client) -> None:
    assert get_settings().cron_secret == ""
    res = client_as(ALICE).post("/internal/jobs/reminders", headers={"X-Cron-Secret": ""})
    assert res.status_code == 404


def test_settings_from_hosting_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://api.example.onrender.com")
    s = Settings(
        _env_file=None,
        database_url="postgresql://u:p@db.example.com/app?sslmode=require",
        app_url="https://app.example.com/",
        auth_mode="clerk",
        clerk_issuer="https://clerk.example.com",
    )
    assert s.database_url == "postgresql+psycopg://u:p@db.example.com/app?sslmode=require"
    assert s.api_url == "https://api.example.onrender.com"
    assert s.clerk_jwks_url == "https://clerk.example.com/.well-known/jwks.json"
    assert "https://app.example.com" in s.cors_origins
    assert s.clerk_authorized_parties == ["https://app.example.com"]
