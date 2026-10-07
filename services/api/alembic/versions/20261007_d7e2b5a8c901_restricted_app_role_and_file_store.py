"""restricted app role and database file store

- ``contraict_app``: a NOLOGIN role without BYPASSRLS that the API switches to on every
  connection (see ``app.db``), so Row-Level Security holds even when the login user could
  bypass it. Created only when the migrating user may create roles; otherwise the API
  keeps using the login user, and production refuses to start if that user bypasses RLS.
- ``stored_files``: document storage inside Postgres for small deployments.

Revision ID: d7e2b5a8c901
Revises: c4a1e9d2f6b3
Create Date: 2026-10-07 21:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d7e2b5a8c901"
down_revision: str | Sequence[str] | None = "c4a1e9d2f6b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "contraict_app"


def upgrade() -> None:
    op.create_table(
        "stored_files",
        sa.Column("key", sa.String(length=1000), primary_key=True),
        sa.Column("content_type", sa.String(length=200), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.execute(
        f"""
        DO $$
        DECLARE
            allowed boolean;
        BEGIN
            SELECT rolsuper OR rolcreaterole INTO allowed
              FROM pg_roles WHERE rolname = current_user;
            IF NOT allowed THEN
                RAISE NOTICE 'No CREATEROLE: the API will use the login user directly';
                RETURN;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} NOLOGIN NOBYPASSRLS;
            END IF;
            -- PostgreSQL 16+ gives a role's creator membership without the right to
            -- SET ROLE to it; ask for that explicitly.
            IF current_setting('server_version_num')::int >= 160000 THEN
                EXECUTE format('GRANT {APP_ROLE} TO %I WITH SET TRUE', current_user);
            ELSIF NOT pg_has_role(current_user, '{APP_ROLE}', 'MEMBER') THEN
                EXECUTE format('GRANT {APP_ROLE} TO %I', current_user);
            END IF;
            EXECUTE format('GRANT USAGE ON SCHEMA public TO {APP_ROLE}');
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE};
            GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE};
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
                'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}', current_user);
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
                'GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {APP_ROLE}', current_user);
        END $$;
        """
    )


def downgrade() -> None:
    # The role is cluster-wide (other databases may use it): only remove this database's
    # privileges, not the role.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}')
               AND pg_has_role(current_user, '{APP_ROLE}', 'MEMBER') THEN
                EXECUTE format(
                    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
                    'REVOKE ALL ON TABLES FROM {APP_ROLE}', current_user);
                EXECUTE format(
                    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
                    'REVOKE ALL ON SEQUENCES FROM {APP_ROLE}', current_user);
                REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE};
                REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE};
                REVOKE USAGE ON SCHEMA public FROM {APP_ROLE};
            END IF;
        END $$;
        """
    )
    op.drop_table("stored_files")
