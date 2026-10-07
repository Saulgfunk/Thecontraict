"""external reminder recipients

Contracts can name extra people to email about deadlines (no account needed), so a
reminder log row is now for either a user or an email address.

Revision ID: c4a1e9d2f6b3
Revises: 6bdd68c84ea5
Create Date: 2026-10-07 20:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c4a1e9d2f6b3"
down_revision: str | Sequence[str] | None = "6bdd68c84ea5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contracts",
        sa.Column(
            "reminder_emails",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("reminder_logs", sa.Column("email", sa.String(length=320), nullable=True))
    op.alter_column("reminder_logs", "user_id", existing_type=sa.Uuid(), nullable=True)
    op.drop_constraint(
        "reminder_logs_deadline_key_due_date_user_id_days_before_key",
        "reminder_logs",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_reminder_logs_recipient_point",
        "reminder_logs",
        ["deadline_key", "due_date", "user_id", "email", "days_before"],
        postgresql_nulls_not_distinct=True,
    )
    op.create_check_constraint(
        "ck_reminder_logs_one_recipient",
        "reminder_logs",
        "(user_id IS NULL) <> (email IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_reminder_logs_one_recipient", "reminder_logs", type_="check")
    op.drop_constraint("uq_reminder_logs_recipient_point", "reminder_logs", type_="unique")
    op.execute("DELETE FROM reminder_logs WHERE user_id IS NULL")
    op.create_unique_constraint(
        "reminder_logs_deadline_key_due_date_user_id_days_before_key",
        "reminder_logs",
        ["deadline_key", "due_date", "user_id", "days_before"],
    )
    op.alter_column("reminder_logs", "user_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("reminder_logs", "email")
    op.drop_column("contracts", "reminder_emails")
