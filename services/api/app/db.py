"""Database engine and session handling.

Tenant isolation is enforced twice:
1. API authorization (see ``app.deps``) checks memberships for every request.
2. PostgreSQL Row-Level Security (see the initial migration) filters tenant-scoped
   tables on the ``app.org_id`` setting, which we apply at the start of every
   transaction from ``session.info["org_id"]``.

RLS only binds roles that can't bypass it. Hosted Postgres often hands out a login user
with BYPASSRLS, so every connection switches to the restricted ``db_app_role`` (created
by a migration) when the login user may, and production refuses to run on a role that
would ignore RLS.
"""

import logging
from collections.abc import Iterator
from typing import Any

from psycopg import sql
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

log = logging.getLogger(__name__)

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class UnsafeDatabaseRole(RuntimeError):
    pass


@event.listens_for(engine, "connect")
def _use_restricted_role(dbapi_connection: Any, connection_record: Any) -> None:
    settings = get_settings()
    with dbapi_connection.cursor() as cur:
        if settings.db_app_role:
            cur.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s AND pg_has_role(current_user, oid, "
                "CASE WHEN current_setting('server_version_num')::int >= 160000 "
                "THEN 'SET' ELSE 'MEMBER' END)",
                (settings.db_app_role,),
            )
            if cur.fetchone():
                cur.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(settings.db_app_role)))
        cur.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        row = cur.fetchone()
    dbapi_connection.commit()  # keep SET ROLE (it would be undone by a rollback)
    if row and row[0]:
        message = (
            "The database role bypasses Row-Level Security, so organizations' data would not "
            "be isolated. Give the login user CREATEROLE (so migrations can create "
            f"'{settings.db_app_role}') or connect as a role without BYPASSRLS."
        )
        if settings.environment == "production":
            raise UnsafeDatabaseRole(message)
        log.warning(message)


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
