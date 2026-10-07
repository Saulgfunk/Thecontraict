"""Database engine and session handling.

Tenant isolation is enforced twice:
1. API authorization (see ``app.deps``) checks memberships for every request.
2. PostgreSQL Row-Level Security (see the initial migration) filters tenant-scoped
   tables on the ``app.org_id`` setting, which we apply at the start of every
   transaction from ``session.info["org_id"]``.
"""

from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(Session, "after_begin")
def _apply_tenant_context(session: Session, transaction: Any, connection: Any) -> None:
    org_id = session.info.get("org_id")
    connection.execute(
        text("SELECT set_config('app.org_id', :org_id, true)"),
        {"org_id": str(org_id) if org_id else ""},
    )


def set_tenant(session: Session, org_id: object | None) -> None:
    """Scope the session to an organization for RLS (applies to the current and future
    transactions of this session)."""
    session.info["org_id"] = org_id
    if session.in_transaction():
        session.execute(
            text("SELECT set_config('app.org_id', :org_id, true)"),
            {"org_id": str(org_id) if org_id else ""},
        )


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
