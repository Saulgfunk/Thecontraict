import enum
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class OrganizationKind(enum.StrEnum):
    COMPANY = "company"
    HOLDING = "holding"
    LAW_FIRM = "law_firm"


class OrgRole(enum.StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class WorkspaceKind(enum.StrEnum):
    CLIENT = "client"
    ENTITY = "entity"
    DEPARTMENT = "department"


class WorkspaceRole(enum.StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    # Subject from the identity provider (Clerk). Null until the user first signs in,
    # e.g. when they were invited by email.
    auth_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[OrganizationKind] = mapped_column(_enum(OrganizationKind, "organization_kind"))
    default_timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    default_country: Mapped[str | None] = mapped_column(String(2))


class OrganizationMembership(TimestampMixin, Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[OrgRole] = mapped_column(_enum(OrgRole, "org_role"))

    user: Mapped[User] = relationship(lazy="joined")
    organization: Mapped[Organization] = relationship(lazy="joined")


class Workspace(TimestampMixin, Base):
    """A hard access boundary inside an organization: a client (law firm), a legal
    entity (holding company) or a department (company)."""

    __tablename__ = "workspaces"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    parent_workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[WorkspaceKind] = mapped_column(_enum(WorkspaceKind, "workspace_kind"))
    country: Mapped[str | None] = mapped_column(String(2))
    timezone: Mapped[str | None] = mapped_column(String(64))


class WorkspaceMembership(TimestampMixin, Base):
    __tablename__ = "workspace_memberships"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[WorkspaceRole] = mapped_column(_enum(WorkspaceRole, "workspace_role"))

    user: Mapped[User] = relationship(lazy="joined")


class AuditEvent(Base):
    """Append-only record of who did what."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# ---------------------------------------------------------------------------
# Contracts, documents and extraction results
# ---------------------------------------------------------------------------


class ContractStatus(enum.StrEnum):
    PROCESSING = "processing"  # document(s) still being analysed
    NEEDS_REVIEW = "needs_review"  # AI results waiting for a human
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"


class DocumentStatus(enum.StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ReviewStatus(enum.StrEnum):
    AI_SUGGESTED = "ai_suggested"
    CONFIRMED = "confirmed"
    EDITED = "edited"
    REJECTED = "rejected"


class PeriodUnit(enum.StrEnum):
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"
    YEARS = "years"


class DayBasis(enum.StrEnum):
    CALENDAR = "calendar"
    BUSINESS = "business"


class DateRuleType(enum.StrEnum):
    NON_RENEWAL_NOTICE = "non_renewal_notice"
    TERMINATION_NOTICE = "termination_notice"
    OPTION_EXERCISE = "option_exercise"
    PRICE_REVIEW = "price_review"
    WARRANTY_END = "warranty_end"
    INSURANCE_EXPIRY = "insurance_expiry"
    GUARANTEE_EXPIRY = "guarantee_expiry"
    LOCK_IN_END = "lock_in_end"
    OTHER = "other"


class DateAnchor(enum.StrEnum):
    FIXED_DATE = "fixed_date"
    EFFECTIVE_DATE = "effective_date"
    TERM_START = "term_start"
    TERM_END = "term_end"


class OffsetDirection(enum.StrEnum):
    BEFORE = "before"
    AFTER = "after"


class PaymentDirection(enum.StrEnum):
    RECEIVABLE = "receivable"
    PAYABLE = "payable"
    UNKNOWN = "unknown"


class PaymentFrequency(enum.StrEnum):
    ONE_OFF = "one_off"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMI_ANNUAL = "semi_annual"
    ANNUAL = "annual"
    OTHER = "other"


class DeadlineKind(enum.StrEnum):
    TERM_END = "term_end"
    NOTICE = "notice"
    OPTION = "option"
    PRICE_REVIEW = "price_review"
    PAYMENT = "payment"
    OTHER = "other"


class DeadlineStatus(enum.StrEnum):
    OPEN = "open"
    DONE = "done"
    DISMISSED = "dismissed"


class WorkspaceScopedMixin(TimestampMixin):
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )


class Contract(WorkspaceScopedMixin, Base):
    """The effective terms of an agreement. Values start as AI suggestions (with their
    sources in ``field_sources``) and become authoritative when a user reviews them."""

    __tablename__ = "contracts"

    title: Mapped[str] = mapped_column(String(500))
    status: Mapped[ContractStatus] = mapped_column(
        _enum(ContractStatus, "contract_status"), default=ContractStatus.PROCESSING
    )
    contract_type: Mapped[str | None] = mapped_column(String(100))
    counterparty_name: Mapped[str | None] = mapped_column(String(500))
    parties: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    summary: Mapped[str | None] = mapped_column(Text)

    effective_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    initial_term_amount: Mapped[int | None] = mapped_column(Integer)
    initial_term_unit: Mapped[PeriodUnit | None] = mapped_column(_enum(PeriodUnit, "period_unit"))
    auto_renews: Mapped[bool | None] = mapped_column(Boolean)
    renewal_term_amount: Mapped[int | None] = mapped_column(Integer)
    renewal_term_unit: Mapped[PeriodUnit | None] = mapped_column(_enum(PeriodUnit, "period_unit"))

    governing_law: Mapped[str | None] = mapped_column(String(200))
    holiday_country: Mapped[str | None] = mapped_column(String(2))
    holiday_subdivision: Mapped[str | None] = mapped_column(String(10))
    currency: Mapped[str | None] = mapped_column(String(3))
    contract_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    notice_details: Mapped[str | None] = mapped_column(Text)

    # {"effective_date": {"clause_refs": ["C3"], "quote": "...", "confidence": 0.9,
    #   "status": "ai_suggested"}, ...}
    field_sources: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    documents: Mapped[list["Document"]] = relationship(
        back_populates="contract",
        order_by="Document.created_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    date_rules: Mapped[list["DateRule"]] = relationship(
        back_populates="contract",
        order_by="DateRule.created_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    payment_terms: Mapped[list["PaymentTerm"]] = relationship(
        back_populates="contract",
        order_by="PaymentTerm.created_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    deadlines: Mapped[list["Deadline"]] = relationship(
        back_populates="contract",
        order_by="Deadline.due_date",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Document(WorkspaceScopedMixin, Base):
    __tablename__ = "documents"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(200))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(1000))
    status: Mapped[DocumentStatus] = mapped_column(
        _enum(DocumentStatus, "document_status"), default=DocumentStatus.UPLOADED
    )
    error: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    text_source: Mapped[str | None] = mapped_column(String(20))  # "text_layer" | "ocr" | "docx"
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    contract: Mapped[Contract] = relationship(back_populates="documents")


class Clause(WorkspaceScopedMixin, Base):
    """A numbered section of a document: the unit we cite."""

    __tablename__ = "clauses"
    __table_args__ = (UniqueConstraint("document_id", "ref"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    ref: Mapped[str] = mapped_column(String(20))  # stable id given to the model, e.g. "C12"
    ordinal: Mapped[int] = mapped_column(Integer)
    number: Mapped[str | None] = mapped_column(String(50))  # as printed, e.g. "12.3"
    heading: Mapped[str | None] = mapped_column(String(500))
    text: Mapped[str] = mapped_column(Text)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)


class ExtractionRun(TimestampMixin, Base):
    __tablename__ = "extraction_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))  # "succeeded" | "failed"
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)


class SourcedMixin:
    """Provenance and review state shared by AI-extracted items."""

    source_clause_refs: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list)
    quote: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[ReviewStatus] = mapped_column(
        _enum(ReviewStatus, "review_status"), default=ReviewStatus.AI_SUGGESTED
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class DateRule(WorkspaceScopedMixin, SourcedMixin, Base):
    """A machine-readable date rule, e.g. "90 days before the end of the term"."""

    __tablename__ = "date_rules"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    rule_type: Mapped[DateRuleType] = mapped_column(_enum(DateRuleType, "date_rule_type"))
    label: Mapped[str] = mapped_column(String(300))
    anchor: Mapped[DateAnchor] = mapped_column(_enum(DateAnchor, "date_anchor"))
    fixed_date: Mapped[date | None] = mapped_column(Date)
    offset_amount: Mapped[int | None] = mapped_column(Integer)
    offset_unit: Mapped[PeriodUnit | None] = mapped_column(_enum(PeriodUnit, "period_unit"))
    offset_basis: Mapped[DayBasis] = mapped_column(
        _enum(DayBasis, "day_basis"), default=DayBasis.CALENDAR
    )
    direction: Mapped[OffsetDirection] = mapped_column(
        _enum(OffsetDirection, "offset_direction"), default=OffsetDirection.BEFORE
    )
    delivery_amount: Mapped[int | None] = mapped_column(Integer)
    delivery_basis: Mapped[DayBasis] = mapped_column(
        _enum(DayBasis, "day_basis"), default=DayBasis.BUSINESS
    )
    compute_error: Mapped[str | None] = mapped_column(Text)

    contract: Mapped[Contract] = relationship(back_populates="date_rules")


class PaymentTerm(WorkspaceScopedMixin, SourcedMixin, Base):
    __tablename__ = "payment_terms"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(String(500))
    direction: Mapped[PaymentDirection] = mapped_column(
        _enum(PaymentDirection, "payment_direction"), default=PaymentDirection.UNKNOWN
    )
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    frequency: Mapped[PaymentFrequency] = mapped_column(
        _enum(PaymentFrequency, "payment_frequency")
    )
    first_due_date: Mapped[date | None] = mapped_column(Date)
    payment_days: Mapped[int | None] = mapped_column(Integer)  # e.g. 30 for "net 30"
    escalation: Mapped[str | None] = mapped_column(Text)

    contract: Mapped[Contract] = relationship(back_populates="payment_terms")


class Deadline(WorkspaceScopedMixin, Base):
    """A concrete date computed from the contract's terms, rules and payment terms.
    Recomputed whenever those change; ``status`` survives recomputation."""

    __tablename__ = "deadlines"

    contract_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    date_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("date_rules.id", ondelete="CASCADE")
    )
    payment_term_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment_terms.id", ondelete="CASCADE")
    )
    kind: Mapped[DeadlineKind] = mapped_column(_enum(DeadlineKind, "deadline_kind"))
    label: Mapped[str] = mapped_column(String(300))
    due_date: Mapped[date] = mapped_column(Date, index=True)
    derivation: Mapped[list[str]] = mapped_column(JSONB, default=list)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[DeadlineStatus] = mapped_column(
        _enum(DeadlineStatus, "deadline_status"), default=DeadlineStatus.OPEN
    )

    contract: Mapped[Contract] = relationship(back_populates="deadlines")
