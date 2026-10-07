import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models import (
    ContractStatus,
    DateAnchor,
    DateRuleType,
    DayBasis,
    DeadlineKind,
    DeadlineStatus,
    DocumentStatus,
    OffsetDirection,
    PaymentDirection,
    PaymentFrequency,
    PeriodUnit,
    ReviewStatus,
)
from app.schemas import ORMModel, _check_country


class DocumentOut(ORMModel):
    id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    status: DocumentStatus
    error: str | None
    page_count: int | None
    text_source: str | None
    created_at: datetime
    processed_at: datetime | None


class ClauseOut(ORMModel):
    id: uuid.UUID
    ref: str
    number: str | None
    heading: str | None
    text: str
    page_start: int | None
    page_end: int | None


class DeadlineOut(ORMModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    workspace_id: uuid.UUID
    date_rule_id: uuid.UUID | None
    payment_term_id: uuid.UUID | None
    kind: DeadlineKind
    label: str
    due_date: date
    derivation: list[str]
    confirmed: bool
    status: DeadlineStatus


class DeadlineWithContract(DeadlineOut):
    contract_title: str
    counterparty_name: str | None
    workspace_name: str


class DeadlineUpdate(BaseModel):
    status: DeadlineStatus


class SourcedOut(ORMModel):
    source_clause_refs: list[str]
    quote: str | None
    confidence: float | None
    review_status: ReviewStatus
    reviewed_at: datetime | None


class DateRuleOut(SourcedOut):
    id: uuid.UUID
    rule_type: DateRuleType
    label: str
    anchor: DateAnchor
    fixed_date: date | None
    offset_amount: int | None
    offset_unit: PeriodUnit | None
    offset_basis: DayBasis
    direction: OffsetDirection
    delivery_amount: int | None
    compute_error: str | None


class DateRuleIn(BaseModel):
    rule_type: DateRuleType = DateRuleType.OTHER
    label: str = Field(min_length=1, max_length=300)
    anchor: DateAnchor
    fixed_date: date | None = None
    offset_amount: int | None = Field(default=None, ge=0, le=36500)
    offset_unit: PeriodUnit | None = None
    offset_basis: DayBasis = DayBasis.CALENDAR
    direction: OffsetDirection = OffsetDirection.BEFORE
    delivery_amount: int | None = Field(default=None, ge=0, le=365)


class DateRuleUpdate(BaseModel):
    """Either a review decision, edits, or both. Edits imply status 'edited'."""

    review_status: ReviewStatus | None = None
    rule_type: DateRuleType | None = None
    label: str | None = Field(default=None, min_length=1, max_length=300)
    anchor: DateAnchor | None = None
    fixed_date: date | None = None
    offset_amount: int | None = Field(default=None, ge=0, le=36500)
    offset_unit: PeriodUnit | None = None
    offset_basis: DayBasis | None = None
    direction: OffsetDirection | None = None
    delivery_amount: int | None = Field(default=None, ge=0, le=365)


class PaymentTermOut(SourcedOut):
    id: uuid.UUID
    description: str
    direction: PaymentDirection
    amount: Decimal | None
    currency: str | None
    frequency: PaymentFrequency
    first_due_date: date | None
    payment_days: int | None
    escalation: str | None


class PaymentTermIn(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    direction: PaymentDirection = PaymentDirection.UNKNOWN
    amount: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    frequency: PaymentFrequency
    first_due_date: date | None = None
    payment_days: int | None = Field(default=None, ge=0, le=365)
    escalation: str | None = None


class PaymentTermUpdate(BaseModel):
    review_status: ReviewStatus | None = None
    description: str | None = Field(default=None, min_length=1, max_length=500)
    direction: PaymentDirection | None = None
    amount: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    frequency: PaymentFrequency | None = None
    first_due_date: date | None = None
    payment_days: int | None = Field(default=None, ge=0, le=365)
    escalation: str | None = None


class ContractSummary(ORMModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    status: ContractStatus
    contract_type: str | None
    counterparty_name: str | None
    effective_date: date | None
    end_date: date | None
    auto_renews: bool | None
    owner_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    documents: list[DocumentOut]
    next_deadline: DeadlineOut | None = None
    pending_review: int = 0


class ContractDetail(ContractSummary):
    summary: str | None
    parties: list[dict[str, Any]]
    initial_term_amount: int | None
    initial_term_unit: PeriodUnit | None
    renewal_term_amount: int | None
    renewal_term_unit: PeriodUnit | None
    governing_law: str | None
    holiday_country: str | None
    holiday_subdivision: str | None
    currency: str | None
    contract_value: Decimal | None
    notice_details: str | None
    field_sources: dict[str, Any]
    reviewed_at: datetime | None
    date_rules: list[DateRuleOut]
    payment_terms: list[PaymentTermOut]
    deadlines: list[DeadlineOut]


# Fields a user can edit on the contract itself.
CONTRACT_EDITABLE = (
    "title",
    "status",
    "contract_type",
    "counterparty_name",
    "effective_date",
    "end_date",
    "initial_term_amount",
    "initial_term_unit",
    "auto_renews",
    "renewal_term_amount",
    "renewal_term_unit",
    "governing_law",
    "holiday_country",
    "holiday_subdivision",
    "currency",
    "contract_value",
    "notice_details",
)

# How edited columns map onto the reviewed "fields" tracked in field_sources.
FIELD_OF_COLUMN = {
    "initial_term_amount": "initial_term",
    "initial_term_unit": "initial_term",
    "renewal_term_amount": "renewal_term",
    "renewal_term_unit": "renewal_term",
}


class ContractUpdate(BaseModel):
    owner_id: uuid.UUID | None = Field(
        default=None, description="Who receives this contract's reminders."
    )
    title: str | None = Field(default=None, min_length=1, max_length=500)
    status: ContractStatus | None = None
    contract_type: str | None = Field(default=None, max_length=100)
    counterparty_name: str | None = Field(default=None, max_length=500)
    effective_date: date | None = None
    end_date: date | None = None
    initial_term_amount: int | None = Field(default=None, ge=1, le=1200)
    initial_term_unit: PeriodUnit | None = None
    auto_renews: bool | None = None
    renewal_term_amount: int | None = Field(default=None, ge=1, le=1200)
    renewal_term_unit: PeriodUnit | None = None
    governing_law: str | None = Field(default=None, max_length=200)
    holiday_country: str | None = None
    holiday_subdivision: str | None = Field(default=None, max_length=10)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    contract_value: Decimal | None = None
    notice_details: str | None = None

    _country = field_validator("holiday_country")(_check_country)

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        return v.upper() if v else v
