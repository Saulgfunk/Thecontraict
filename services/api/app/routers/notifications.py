"""In-app notifications, reminder settings and personal calendar feeds."""

import hashlib
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from icalendar import Calendar, Event
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from app import audit
from app.config import get_settings
from app.db import SessionLocal, set_tenant
from app.deps import OrgContext, get_org_context
from app.models import (
    DEFAULT_REMINDER_DAYS,
    CalendarFeed,
    Contract,
    Deadline,
    DeadlineStatus,
    Notification,
    OrganizationMembership,
    Workspace,
    deadline_key,
)
from app.reminders import accessible_workspace_ids, reminder_days

router = APIRouter(tags=["notifications"])


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str | None
    link: str | None
    read_at: datetime | None
    created_at: datetime


class NotificationList(BaseModel):
    items: list[NotificationOut]
    unread_count: int


class MarkRead(BaseModel):
    ids: list[uuid.UUID] | None = Field(default=None, description="Omit to mark all as read.")


@router.get("/organizations/{org_id}/notifications", response_model=NotificationList)
def list_notifications(
    ctx: OrgContext = Depends(get_org_context),
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
) -> NotificationList:
    mine = Notification.user_id == ctx.user.id
    query = select(Notification).where(mine).order_by(Notification.created_at.desc()).limit(limit)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    unread = ctx.db.scalar(
        select(func.count()).select_from(Notification).where(mine, Notification.read_at.is_(None))
    )
    return NotificationList(
        items=[
            NotificationOut.model_validate(n, from_attributes=True) for n in ctx.db.scalars(query)
        ],
        unread_count=unread or 0,
    )


@router.post("/organizations/{org_id}/notifications/read", status_code=204)
def mark_read(body: MarkRead, ctx: OrgContext = Depends(get_org_context)) -> None:
    stmt = update(Notification).where(
        Notification.user_id == ctx.user.id, Notification.read_at.is_(None)
    )
    if body.ids is not None:
        stmt = stmt.where(Notification.id.in_(body.ids))
    ctx.db.execute(stmt.values(read_at=datetime.now(UTC)))
    ctx.db.commit()


# ---------------------------------------------------------------------------
# Preferences and reminder settings
# ---------------------------------------------------------------------------


class Preferences(BaseModel):
    email_reminders: bool
    weekly_digest: bool


class PreferencesUpdate(BaseModel):
    email_reminders: bool | None = None
    weekly_digest: bool | None = None


@router.get("/organizations/{org_id}/me/preferences", response_model=Preferences)
def get_preferences(ctx: OrgContext = Depends(get_org_context)) -> Preferences:
    return Preferences.model_validate(ctx.membership, from_attributes=True)


@router.patch("/organizations/{org_id}/me/preferences", response_model=Preferences)
def update_preferences(
    body: PreferencesUpdate, ctx: OrgContext = Depends(get_org_context)
) -> Preferences:
    membership: OrganizationMembership = ctx.membership
    for key, value in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(membership, key, value)
    ctx.db.commit()
    return Preferences.model_validate(membership, from_attributes=True)


class ReminderSettings(BaseModel):
    reminder_days: dict[str, list[int]] = Field(
        description="Days before each kind of deadline to send reminders (0 = on the day)."
    )


@router.get("/organizations/{org_id}/reminder-settings", response_model=ReminderSettings)
def get_reminder_settings(ctx: OrgContext = Depends(get_org_context)) -> ReminderSettings:
    return ReminderSettings(reminder_days=reminder_days(ctx.membership.organization))


@router.put("/organizations/{org_id}/reminder-settings", response_model=ReminderSettings)
def update_reminder_settings(
    body: ReminderSettings, ctx: OrgContext = Depends(get_org_context)
) -> ReminderSettings:
    ctx.require_org_admin()
    cleaned: dict[str, list[int]] = {}
    for kind, days in body.reminder_days.items():
        if kind not in DEFAULT_REMINDER_DAYS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown kind: {kind}")
        if any(d < 0 or d > 3650 for d in days) or len(days) > 20:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Use up to 20 values between 0 and 3650"
            )
        cleaned[kind] = sorted(set(days), reverse=True)
    org = ctx.membership.organization
    org.reminder_days = cleaned
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        actor_user_id=ctx.user.id,
        action="organization.reminder_settings_updated",
        entity_type="organization",
        entity_id=ctx.org_id,
        data=cleaned,
    )
    ctx.db.commit()
    return ReminderSettings(reminder_days=reminder_days(org))


# ---------------------------------------------------------------------------
# Calendar feed
# ---------------------------------------------------------------------------


class CalendarFeedOut(BaseModel):
    active: bool
    created_at: datetime | None = None
    last_accessed_at: datetime | None = None
    url: str | None = Field(default=None, description="Only returned when the feed is created.")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _feed(ctx: OrgContext) -> CalendarFeed | None:
    return ctx.db.scalar(
        select(CalendarFeed).where(
            CalendarFeed.organization_id == ctx.org_id, CalendarFeed.user_id == ctx.user.id
        )
    )


@router.get("/organizations/{org_id}/calendar-feed", response_model=CalendarFeedOut)
def get_calendar_feed(ctx: OrgContext = Depends(get_org_context)) -> CalendarFeedOut:
    feed = _feed(ctx)
    if feed is None:
        return CalendarFeedOut(active=False)
    return CalendarFeedOut(
        active=True, created_at=feed.created_at, last_accessed_at=feed.last_accessed_at
    )


@router.post("/organizations/{org_id}/calendar-feed", response_model=CalendarFeedOut)
def create_calendar_feed(ctx: OrgContext = Depends(get_org_context)) -> CalendarFeedOut:
    """Create (or replace) the user's private feed. The URL is shown only once; creating a
    new one invalidates the old URL."""
    token = secrets.token_urlsafe(32)
    feed = _feed(ctx)
    if feed is None:
        feed = CalendarFeed(organization_id=ctx.org_id, user_id=ctx.user.id, token_hash="")
        ctx.db.add(feed)
    feed.token_hash = _hash(token)
    feed.created_at = datetime.now(UTC)
    feed.last_accessed_at = None
    audit.record(
        ctx.db,
        organization_id=ctx.org_id,
        actor_user_id=ctx.user.id,
        action="calendar_feed.created",
        entity_type="user",
        entity_id=ctx.user.id,
    )
    ctx.db.commit()
    url = f"{get_settings().api_url.rstrip('/')}/calendar/{token}.ics"
    return CalendarFeedOut(active=True, created_at=feed.created_at, url=url)


@router.delete("/organizations/{org_id}/calendar-feed", status_code=204)
def delete_calendar_feed(ctx: OrgContext = Depends(get_org_context)) -> None:
    feed = _feed(ctx)
    if feed:
        ctx.db.delete(feed)
        ctx.db.commit()


@router.get("/calendar/{token}.ics", include_in_schema=False)
def calendar_ics(token: str) -> Response:
    with SessionLocal() as db:
        feed = db.scalar(select(CalendarFeed).where(CalendarFeed.token_hash == _hash(token)))
        if feed is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown calendar")
        set_tenant(db, feed.organization_id)
        membership = db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == feed.organization_id,
                OrganizationMembership.user_id == feed.user_id,
            )
        )
        if membership is None:  # the user has left the organization
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown calendar")
        allowed = accessible_workspace_ids(db, membership)
        query = (
            select(Deadline, Contract, Workspace)
            .join(Contract, Contract.id == Deadline.contract_id)
            .join(Workspace, Workspace.id == Deadline.workspace_id)
            .where(
                Deadline.status == DeadlineStatus.OPEN,
                Deadline.due_date >= date.today() - timedelta(days=60),
            )
            .order_by(Deadline.due_date)
        )
        if allowed is not None:
            query = query.where(Deadline.workspace_id.in_(allowed))
        rows = db.execute(query).all()
        org_name = membership.organization.name
        feed.last_accessed_at = datetime.now(UTC)
        db.commit()

    app_url = get_settings().app_url.rstrip("/")
    cal = Calendar()
    cal.add("prodid", "-//TheContrAIct//Deadlines//EN")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", f"Contract deadlines – {org_name}")
    cal.add("refresh-interval;value=duration", "PT6H")
    now = datetime.now(UTC)
    for d, c, w in rows:
        link = f"{app_url}/app/{d.organization_id}/contracts/{c.id}"
        event = Event()
        event.add("uid", f"{deadline_key(d)}:{d.due_date.isoformat()}@thecontraict")
        event.add("dtstamp", now)
        event.add("dtstart", d.due_date)
        event.add("dtend", d.due_date + timedelta(days=1))
        prefix = "" if d.confirmed else "[unconfirmed] "
        event.add("summary", f"{prefix}{d.label} – {c.title}")
        event.add(
            "description",
            "\n".join([f"{c.title} ({w.name})", *d.derivation, "", link]),
        )
        event.add("url", link)
        event.add("transp", "TRANSPARENT")
        cal.add_component(event)
    return Response(
        content=cal.to_ical(),
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "private, max-age=900"},
    )
