import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit
from app.auth import get_current_user
from app.db import get_db, set_tenant
from app.deps import OrgContext, get_org_context
from app.models import (
    AuditEvent,
    Organization,
    OrganizationMembership,
    OrgRole,
    User,
    WorkspaceMembership,
)
from app.schemas import (
    AuditEventOut,
    MeOut,
    MyOrganization,
    OrganizationCreate,
    OrganizationOut,
    OrganizationUpdate,
    OrgMemberCreate,
    OrgMemberOut,
    OrgMemberUpdate,
    UserOut,
)
from app.users import get_or_invite_user

router = APIRouter(tags=["organizations"])


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MeOut:
    memberships = db.scalars(
        select(OrganizationMembership)
        .where(OrganizationMembership.user_id == user.id)
        .order_by(OrganizationMembership.created_at)
    ).all()
    return MeOut(
        user=UserOut.model_validate(user),
        organizations=[
            MyOrganization(organization=OrganizationOut.model_validate(m.organization), role=m.role)
            for m in memberships
        ],
    )


@router.post("/organizations", response_model=OrganizationOut, status_code=201)
def create_organization(
    body: OrganizationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Organization:
    org = Organization(**body.model_dump())
    db.add(org)
    db.flush()
    set_tenant(db, org.id)
    db.add(OrganizationMembership(organization_id=org.id, user_id=user.id, role=OrgRole.OWNER))
    audit.record(
        db,
        organization_id=org.id,
        actor_user_id=user.id,
        action="organization.created",
        entity_type="organization",
        entity_id=org.id,
        data=body.model_dump(),
    )
    db.commit()
    return org


@router.get("/organizations/{org_id}", response_model=OrganizationOut)
def get_organization(ctx: OrgContext = Depends(get_org_context)) -> Organization:
    return ctx.membership.organization


@router.patch("/organizations/{org_id}", response_model=OrganizationOut)
def update_organization(
    body: OrganizationUpdate, ctx: OrgContext = Depends(get_org_context)
) -> Organization:
    ctx.require_org_admin()
    org = ctx.membership.organization
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(org, key, value)
    audit.record(
        ctx.db,
        organization_id=org.id,
        actor_user_id=ctx.user.id,
        action="organization.updated",
        entity_type="organization",
        entity_id=org.id,
        data=changes,
    )
    ctx.db.commit()
    return org


@router.get("/organizations/{org_id}/members", response_model=list[OrgMemberOut])
def list_members(ctx: OrgContext = Depends(get_org_context)) -> list[OrganizationMembership]:
    return list(
        ctx.db.scalars(
            select(OrganizationMembership)
            .where(OrganizationMembership.organization_id == ctx.org_id)
            .order_by(OrganizationMembership.created_at)
        ).all()
    )


@router.post("/organizations/{org_id}/members", response_model=OrgMemberOut, status_code=201)
def add_member(
    body: OrgMemberCreate, ctx: OrgContext = Depends(get_org_context)
) -> OrganizationMembership:
    ctx.require_org_admin()
    if body.role == OrgRole.OWNER and ctx.membership.role != OrgRole.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners can add owners")
    user = get_or_invite_user(ctx.db, body.email)
    exists = ctx.db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == ctx.org_id,
            OrganizationMembership.user_id == user.id,
        )
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "User is already a member")
    membership = OrganizationMembership(organization_id=ctx.org_id, user_id=user.id, role=body.role)
    ctx.db.add(membership)
    ctx.db.flush()
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        actor_user_id=ctx.user.id,
        action="organization.member_added",
        entity_type="user",
        entity_id=user.id,
        data={"email": user.email, "role": body.role},
    )
    ctx.db.commit()
    ctx.db.refresh(membership)
    return membership


def _get_membership(ctx: OrgContext, member_id: uuid.UUID) -> OrganizationMembership:
    membership = ctx.db.get(OrganizationMembership, member_id)
    if membership is None or membership.organization_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return membership


def _ensure_other_owner(ctx: OrgContext, membership: OrganizationMembership) -> None:
    if membership.role != OrgRole.OWNER:
        return
    owners = ctx.db.scalar(
        select(func.count()).where(
            OrganizationMembership.organization_id == ctx.org_id,
            OrganizationMembership.role == OrgRole.OWNER,
        )
    )
    if owners is not None and owners <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "An organization needs at least one owner")


@router.patch("/organizations/{org_id}/members/{member_id}", response_model=OrgMemberOut)
def update_member(
    member_id: uuid.UUID, body: OrgMemberUpdate, ctx: OrgContext = Depends(get_org_context)
) -> OrganizationMembership:
    ctx.require_org_admin()
    membership = _get_membership(ctx, member_id)
    touches_owner = OrgRole.OWNER in (membership.role, body.role)
    if touches_owner and ctx.membership.role != OrgRole.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners can change owners")
    if body.role != OrgRole.OWNER:
        _ensure_other_owner(ctx, membership)
    previous = membership.role
    membership.role = body.role
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        actor_user_id=ctx.user.id,
        action="organization.member_role_changed",
        entity_type="user",
        entity_id=membership.user_id,
        data={"from": previous, "to": body.role},
    )
    ctx.db.commit()
    return membership


@router.delete("/organizations/{org_id}/members/{member_id}", status_code=204)
def remove_member(member_id: uuid.UUID, ctx: OrgContext = Depends(get_org_context)) -> None:
    membership = _get_membership(ctx, member_id)
    if membership.user_id != ctx.user.id:  # anyone may leave; removing others needs admin
        ctx.require_org_admin()
        if membership.role == OrgRole.OWNER and ctx.membership.role != OrgRole.OWNER:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners can remove owners")
    _ensure_other_owner(ctx, membership)
    # Removing someone from the organization also removes all their workspace access.
    for wm in ctx.db.scalars(
        select(WorkspaceMembership).where(
            WorkspaceMembership.organization_id == ctx.org_id,
            WorkspaceMembership.user_id == membership.user_id,
        )
    ):
        ctx.db.delete(wm)
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        actor_user_id=ctx.user.id,
        action="organization.member_removed",
        entity_type="user",
        entity_id=membership.user_id,
        data={"email": membership.user.email},
    )
    ctx.db.delete(membership)
    ctx.db.commit()


@router.get("/organizations/{org_id}/audit-events", response_model=list[AuditEventOut])
def list_audit_events(
    ctx: OrgContext = Depends(get_org_context),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuditEvent]:
    ctx.require_org_admin()
    return list(
        ctx.db.scalars(
            select(AuditEvent)
            .where(AuditEvent.organization_id == ctx.org_id)
            .order_by(AuditEvent.at.desc())
            .limit(limit)
        ).all()
    )
