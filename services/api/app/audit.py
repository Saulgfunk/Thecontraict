import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent


def record(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Add an audit event to the session; it is committed with the change it describes."""
    db.add(
        AuditEvent(
            organization_id=organization_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            data=data or {},
        )
    )
