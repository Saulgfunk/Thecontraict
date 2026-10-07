"""Authorization dependencies: organization and workspace access."""

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db, set_tenant
from app.models import (
    OrganizationMembership,
    OrgRole,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
)

_WORKSPACE_ROLE_RANK = {WorkspaceRole.VIEWER: 1, WorkspaceRole.EDITOR: 2, WorkspaceRole.ADMIN: 3}


@dataclass
class OrgContext:
    db: Session
    user: User
    membership: OrganizationMembership

    @property
    def org_id(self) -> uuid.UUID:
        return self.membership.organization_id

    @property
    def is_org_admin(self) -> bool:
        return self.membership.role in (OrgRole.OWNER, OrgRole.ADMIN)

    def require_org_admin(self) -> None:
        if not self.is_org_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization admin role required")

    def workspace_role(self, workspace_id: uuid.UUID) -> WorkspaceRole | None:
        """Effective role in a workspace. Org owners/admins are admins everywhere."""
        if self.is_org_admin:
            return WorkspaceRole.ADMIN
        return self.db.scalar(
            select(WorkspaceMembership.role).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == self.user.id,
            )
        )

    def get_workspace(
        self, workspace_id: uuid.UUID, min_role: WorkspaceRole = WorkspaceRole.VIEWER
    ) -> Workspace:
        workspace = self.db.get(Workspace, workspace_id)
        role = self.workspace_role(workspace_id) if workspace else None
        # Same 404 whether it doesn't exist or the user has no access: don't leak existence.
        if workspace is None or workspace.organization_id != self.org_id or role is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
        if _WORKSPACE_ROLE_RANK[role] < _WORKSPACE_ROLE_RANK[min_role]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Workspace {min_role} role required")
        return workspace


def get_org_context(
    org_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgContext:
    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.user_id == user.id,
        )
    )
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    set_tenant(db, org_id)
    return OrgContext(db=db, user=user, membership=membership)
