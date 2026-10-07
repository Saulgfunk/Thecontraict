import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app import audit
from app.deps import OrgContext, get_org_context
from app.models import (
    OrganizationMembership,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
)
from app.schemas import (
    WorkspaceCreate,
    WorkspaceMemberCreate,
    WorkspaceMemberOut,
    WorkspaceOut,
    WorkspaceUpdate,
    WorkspaceWithRole,
)
from app.users import get_or_invite_user

router = APIRouter(prefix="/organizations/{org_id}/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceWithRole])
def list_workspaces(ctx: OrgContext = Depends(get_org_context)) -> list[WorkspaceWithRole]:
    if ctx.is_org_admin:
        rows = [
            (ws, WorkspaceRole.ADMIN)
            for ws in ctx.db.scalars(
                select(Workspace)
                .where(Workspace.organization_id == ctx.org_id)
                .order_by(Workspace.name)
            )
        ]
    else:
        rows = [
            (ws, role)
            for ws, role in ctx.db.execute(
                select(Workspace, WorkspaceMembership.role)
                .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
                .where(
                    Workspace.organization_id == ctx.org_id,
                    WorkspaceMembership.user_id == ctx.user.id,
                )
                .order_by(Workspace.name)
            )
        ]
    return [
        WorkspaceWithRole(**WorkspaceOut.model_validate(ws).model_dump(), my_role=role)
        for ws, role in rows
    ]


@router.post("", response_model=WorkspaceOut, status_code=201)
def create_workspace(
    body: WorkspaceCreate, ctx: OrgContext = Depends(get_org_context)
) -> Workspace:
    ctx.require_org_admin()
    if body.parent_workspace_id is not None:
        ctx.get_workspace(body.parent_workspace_id, WorkspaceRole.ADMIN)
    workspace = Workspace(organization_id=ctx.org_id, **body.model_dump())
    ctx.db.add(workspace)
    ctx.db.flush()
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=workspace.id,
        actor_user_id=ctx.user.id,
        action="workspace.created",
        entity_type="workspace",
        entity_id=workspace.id,
        data=body.model_dump(mode="json"),
    )
    ctx.db.commit()
    return workspace


@router.get("/{workspace_id}", response_model=WorkspaceWithRole)
def get_workspace(
    workspace_id: uuid.UUID, ctx: OrgContext = Depends(get_org_context)
) -> WorkspaceWithRole:
    workspace = ctx.get_workspace(workspace_id)
    role = ctx.workspace_role(workspace_id)
    assert role is not None
    return WorkspaceWithRole(**WorkspaceOut.model_validate(workspace).model_dump(), my_role=role)


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(
    workspace_id: uuid.UUID, body: WorkspaceUpdate, ctx: OrgContext = Depends(get_org_context)
) -> Workspace:
    workspace = ctx.get_workspace(workspace_id, WorkspaceRole.ADMIN)
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(workspace, key, value)
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=workspace.id,
        actor_user_id=ctx.user.id,
        action="workspace.updated",
        entity_type="workspace",
        entity_id=workspace.id,
        data=changes,
    )
    ctx.db.commit()
    return workspace


@router.get("/{workspace_id}/members", response_model=list[WorkspaceMemberOut])
def list_workspace_members(
    workspace_id: uuid.UUID, ctx: OrgContext = Depends(get_org_context)
) -> list[WorkspaceMembership]:
    ctx.get_workspace(workspace_id)
    return list(
        ctx.db.scalars(
            select(WorkspaceMembership)
            .where(WorkspaceMembership.workspace_id == workspace_id)
            .order_by(WorkspaceMembership.created_at)
        ).all()
    )


@router.post("/{workspace_id}/members", response_model=WorkspaceMemberOut, status_code=201)
def add_workspace_member(
    workspace_id: uuid.UUID,
    body: WorkspaceMemberCreate,
    ctx: OrgContext = Depends(get_org_context),
) -> WorkspaceMembership:
    workspace = ctx.get_workspace(workspace_id, WorkspaceRole.ADMIN)
    user = get_or_invite_user(ctx.db, body.email)
    org_member = ctx.db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == ctx.org_id,
            OrganizationMembership.user_id == user.id,
        )
    )
    if org_member is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Add the user to the organization before the workspace"
        )
    membership = ctx.db.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace.id,
            WorkspaceMembership.user_id == user.id,
        )
    )
    if membership is None:
        membership = WorkspaceMembership(
            organization_id=ctx.org_id, workspace_id=workspace.id, user_id=user.id, role=body.role
        )
        ctx.db.add(membership)
    else:
        membership.role = body.role
    ctx.db.flush()
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=workspace.id,
        actor_user_id=ctx.user.id,
        action="workspace.member_set",
        entity_type="user",
        entity_id=user.id,
        data={"email": user.email, "role": body.role},
    )
    ctx.db.commit()
    ctx.db.refresh(membership)
    return membership


@router.delete("/{workspace_id}/members/{member_id}", status_code=204)
def remove_workspace_member(
    workspace_id: uuid.UUID, member_id: uuid.UUID, ctx: OrgContext = Depends(get_org_context)
) -> None:
    workspace = ctx.get_workspace(workspace_id, WorkspaceRole.ADMIN)
    membership = ctx.db.get(WorkspaceMembership, member_id)
    if membership is None or membership.workspace_id != workspace.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        workspace_id=workspace.id,
        actor_user_id=ctx.user.id,
        action="workspace.member_removed",
        entity_type="user",
        entity_id=membership.user_id,
        data={"email": membership.user.email},
    )
    ctx.db.delete(membership)
    ctx.db.commit()
