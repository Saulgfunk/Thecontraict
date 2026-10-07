"""Deadline reminders (in-app + email) and weekly digests.

``send_due_reminders`` is idempotent and safe to run often (hourly): for each open
deadline it finds the most recent reminder point already reached (e.g. "30 days
before") and sends it once per recipient. A missed run therefore catches up with a
single reminder instead of a burst, and a new deadline that is already close gets one
reminder straight away.
"""

import html
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import email
from app.config import get_settings
from app.db import SessionLocal, set_tenant
from app.models import (
    DEFAULT_REMINDER_DAYS,
    Contract,
    ContractStatus,
    Deadline,
    DeadlineStatus,
    Notification,
    Organization,
    OrganizationMembership,
    OrgRole,
    ReminderLog,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
    deadline_key,
)

log = logging.getLogger(__name__)

DIGEST_DAYS_AHEAD = 30


def reminder_days(org: Organization) -> dict[str, list[int]]:
    merged = {k: list(v) for k, v in DEFAULT_REMINDER_DAYS.items()}
    for kind, days in (org.reminder_days or {}).items():
        if kind in merged:
            merged[kind] = sorted({int(d) for d in days if 0 <= int(d) <= 3650}, reverse=True)
    return merged


def accessible_workspace_ids(
    db: Session, membership: OrganizationMembership
) -> set[uuid.UUID] | None:
    """None means every workspace (org owners and admins)."""
    if membership.role in (OrgRole.OWNER, OrgRole.ADMIN):
        return None
    return set(
        db.scalars(
            select(WorkspaceMembership.workspace_id).where(
                WorkspaceMembership.organization_id == membership.organization_id,
                WorkspaceMembership.user_id == membership.user_id,
            )
        )
    )


def _recipients(
    db: Session, contract: Contract, memberships: dict[uuid.UUID, OrganizationMembership]
) -> list[OrganizationMembership]:
    """The contract owner (or uploader) if they can still see it; otherwise the workspace's
    admins, so that no deadline goes unwatched."""
    for user_id in (contract.owner_id, contract.created_by_id):
        m = memberships.get(user_id) if user_id else None
        if m is None:
            continue
        allowed = accessible_workspace_ids(db, m)
        if allowed is None or contract.workspace_id in allowed:
            return [m]
    admin_ids = set(
        db.scalars(
            select(WorkspaceMembership.user_id).where(
                WorkspaceMembership.workspace_id == contract.workspace_id,
                WorkspaceMembership.role == WorkspaceRole.ADMIN,
            )
        )
    )
    found = [m for uid, m in memberships.items() if uid in admin_ids]
    if found:
        return found
    return [m for m in memberships.values() if m.role == OrgRole.OWNER]


@dataclass
class PendingReminder:
    deadline: Deadline
    contract: Contract
    days_left: int


def _when(days_left: int) -> str:
    if days_left == 0:
        return "today"
    if days_left == 1:
        return "tomorrow"
    return f"in {days_left} days"


def _contract_link(org_id: uuid.UUID, contract_id: uuid.UUID) -> str:
    return f"/app/{org_id}/contracts/{contract_id}"


def send_due_reminders(today: date | None = None) -> int:
    """Send reminders for every organization. Returns the number of reminders created."""
    today = today or date.today()
    with SessionLocal() as db:
        org_ids = list(db.scalars(select(Organization.id)))
    total = 0
    for org_id in org_ids:
        try:
            total += _send_for_org(org_id, today)
        except Exception:
            log.exception("Reminders failed for organization %s", org_id)
    return total


def _send_for_org(org_id: uuid.UUID, today: date) -> int:
    with SessionLocal() as db:
        set_tenant(db, org_id)
        org = db.get(Organization, org_id)
        assert org is not None
        days_by_kind = reminder_days(org)
        horizon = today + timedelta(days=max(max(d, default=0) for d in days_by_kind.values()))
        memberships = {
            m.user_id: m
            for m in db.scalars(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == org_id
                )
            )
        }
        rows = db.execute(
            select(Deadline, Contract)
            .join(Contract, Contract.id == Deadline.contract_id)
            .where(
                Deadline.status == DeadlineStatus.OPEN,
                Deadline.due_date >= today,
                Deadline.due_date <= horizon,
                Contract.status.not_in([ContractStatus.EXPIRED, ContractStatus.TERMINATED]),
            )
        ).all()

        per_user: dict[uuid.UUID, list[PendingReminder]] = defaultdict(list)
        created = 0
        for deadline, contract in rows:
            days_left = (deadline.due_date - today).days
            reached = [d for d in days_by_kind.get(deadline.kind, []) if d >= days_left]
            if not reached:
                continue
            point = min(reached)
            for m in _recipients(db, contract, memberships):
                inserted = db.execute(
                    insert(ReminderLog)
                    .values(
                        id=uuid.uuid4(),
                        organization_id=org_id,
                        contract_id=contract.id,
                        deadline_key=deadline_key(deadline),
                        due_date=deadline.due_date,
                        user_id=m.user_id,
                        days_before=point,
                        emailed=m.email_reminders,
                    )
                    .on_conflict_do_nothing()
                    .returning(ReminderLog.id)
                ).scalar()
                if inserted is None:
                    continue
                created += 1
                db.add(
                    Notification(
                        organization_id=org_id,
                        user_id=m.user_id,
                        kind="deadline_reminder",
                        title=f"{deadline.label} {_when(days_left)}",
                        body=f"{contract.title} · due {deadline.due_date:%d %b %Y}",
                        link=_contract_link(org_id, contract.id),
                        contract_id=contract.id,
                    )
                )
                if m.email_reminders:
                    per_user[m.user_id].append(PendingReminder(deadline, contract, days_left))
        db.commit()

        for user_id, items in per_user.items():
            user = memberships[user_id].user
            try:
                email.send(_reminder_email(org, user, items))
            except Exception:
                log.exception("Sending reminder email to %s failed", user.email)
        return created


# ---------------------------------------------------------------------------
# Emails
# ---------------------------------------------------------------------------


def _row_html(text: str, sub: str, link: str, badge: str) -> str:
    return (
        '<tr><td style="padding:10px 0;border-bottom:1px solid #e2e8f0">'
        f'<a href="{html.escape(link)}" style="color:#0f172a;font-weight:600;'
        f'text-decoration:none">{html.escape(text)}</a><br>'
        f'<span style="color:#64748b;font-size:13px">{html.escape(sub)}</span></td>'
        '<td style="padding:10px 0;border-bottom:1px solid #e2e8f0;text-align:right;'
        f'white-space:nowrap;color:#b45309;font-weight:600">{html.escape(badge)}</td></tr>'
    )


def _wrap_html(title: str, intro: str, rows: str, footer: str) -> str:
    return (
        '<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:600px;'
        'margin:0 auto;color:#0f172a">'
        f'<h2 style="margin:0 0 4px">{html.escape(title)}</h2>'
        f'<p style="color:#64748b;margin:0 0 16px">{html.escape(intro)}</p>'
        f'<table style="width:100%;border-collapse:collapse">{rows}</table>'
        f'<p style="color:#94a3b8;font-size:12px;margin-top:24px">{html.escape(footer)}</p>'
        "</div>"
    )


FOOTER = (
    "Dates are calculated from the contract terms; check the contract before acting. "
    "Change your notification settings in TheContrAIct."
)


def _reminder_email(org: Organization, user: User, items: list[PendingReminder]) -> email.Email:
    base = get_settings().app_url.rstrip("/")
    items.sort(key=lambda i: i.deadline.due_date)
    first = items[0]
    subject = (
        f"{first.deadline.label}: {first.contract.title} ({_when(first.days_left)})"
        if len(items) == 1
        else f"{len(items)} contract deadlines coming up ({org.name})"
    )
    lines, rows = [], []
    for i in items:
        sub = f"{i.contract.title} · {i.deadline.due_date:%a %d %b %Y}"
        if not i.deadline.confirmed:
            sub += " · not yet confirmed"
        link = base + _contract_link(org.id, i.contract.id)
        lines.append(f"- {i.deadline.label} {_when(i.days_left)}: {sub}\n  {link}")
        rows.append(_row_html(i.deadline.label, sub, link, _when(i.days_left)))
    intro = f"Upcoming deadlines in {org.name}."
    return email.Email(
        to=user.email,
        subject=subject,
        text=f"{intro}\n\n" + "\n".join(lines) + f"\n\n{FOOTER}\n",
        html=_wrap_html("Deadline reminder", intro, "".join(rows), FOOTER),
    )


def send_weekly_digests(today: date | None = None) -> int:
    """One email per user and organization summarising the next 30 days."""
    today = today or date.today()
    with SessionLocal() as db:
        org_ids = list(db.scalars(select(Organization.id)))
    sent = 0
    for org_id in org_ids:
        try:
            sent += _digests_for_org(org_id, today)
        except Exception:
            log.exception("Digests failed for organization %s", org_id)
    return sent


def _digests_for_org(org_id: uuid.UUID, today: date) -> int:
    base = get_settings().app_url.rstrip("/")
    sent = 0
    with SessionLocal() as db:
        set_tenant(db, org_id)
        org = db.get(Organization, org_id)
        assert org is not None
        rows = db.execute(
            select(Deadline, Contract, Workspace)
            .join(Contract, Contract.id == Deadline.contract_id)
            .join(Workspace, Workspace.id == Deadline.workspace_id)
            .where(
                Deadline.status == DeadlineStatus.OPEN,
                Deadline.due_date >= today - timedelta(days=30),
                Deadline.due_date <= today + timedelta(days=DIGEST_DAYS_AHEAD),
            )
            .order_by(Deadline.due_date)
        ).all()
        review = db.execute(
            select(Contract.workspace_id, Contract.id).where(
                Contract.status == ContractStatus.NEEDS_REVIEW
            )
        ).all()
        memberships = db.scalars(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == org_id,
                OrganizationMembership.weekly_digest.is_(True),
            )
        ).all()
        for m in memberships:
            allowed = accessible_workspace_ids(db, m)
            mine = [r for r in rows if allowed is None or r[2].id in allowed]
            to_review = [r for r in review if allowed is None or r[0] in allowed]
            if not mine and not to_review:
                continue
            overdue = [r for r in mine if r[0].due_date < today]
            upcoming = [r for r in mine if r[0].due_date >= today]
            lines, rows_html = [], []
            for d, c, w in overdue + upcoming:
                days = (d.due_date - today).days
                when = f"{-days} days overdue" if days < 0 else _when(days)
                sub = f"{c.title} · {w.name} · {d.due_date:%a %d %b %Y}"
                link = base + _contract_link(org_id, c.id)
                lines.append(f"- {d.label} ({when}): {sub}\n  {link}")
                rows_html.append(_row_html(d.label, sub, link, when))
            intro = (
                f"{len(upcoming)} deadline(s) in the next {DIGEST_DAYS_AHEAD} days"
                + (f", {len(overdue)} overdue" if overdue else "")
                + (f", {len(to_review)} contract(s) waiting for review" if to_review else "")
                + "."
            )
            try:
                email.send(
                    email.Email(
                        to=m.user.email,
                        subject=f"Weekly contract digest: {org.name}",
                        text=f"{intro}\n\n" + "\n".join(lines) + f"\n\n{FOOTER}\n",
                        html=_wrap_html(
                            f"Your week in {org.name}", intro, "".join(rows_html), FOOTER
                        ),
                    )
                )
                sent += 1
            except Exception:
                log.exception("Sending digest to %s failed", m.user.email)
    return sent
