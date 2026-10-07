"""Turn a contract's terms, date rules and payment terms into concrete deadlines."""

import uuid
from dataclasses import dataclass, field
from datetime import date

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from app.deadlines import engine
from app.models import (
    Contract,
    DateAnchor,
    DateRule,
    DateRuleType,
    Deadline,
    DeadlineKind,
    DeadlineStatus,
    PaymentFrequency,
    PaymentTerm,
    ReviewStatus,
    Workspace,
)

PAYMENT_HORIZON_MONTHS = 12

_RULE_KIND = {
    DateRuleType.NON_RENEWAL_NOTICE: DeadlineKind.NOTICE,
    DateRuleType.TERMINATION_NOTICE: DeadlineKind.NOTICE,
    DateRuleType.OPTION_EXERCISE: DeadlineKind.OPTION,
    DateRuleType.PRICE_REVIEW: DeadlineKind.PRICE_REVIEW,
}

_FREQUENCY_MONTHS = {
    PaymentFrequency.MONTHLY: 1,
    PaymentFrequency.QUARTERLY: 3,
    PaymentFrequency.SEMI_ANNUAL: 6,
    PaymentFrequency.ANNUAL: 12,
}

_REVIEWED = (ReviewStatus.CONFIRMED, ReviewStatus.EDITED)


@dataclass
class ComputedDeadline:
    kind: DeadlineKind
    label: str
    due_date: date
    derivation: list[str]
    confirmed: bool
    date_rule_id: uuid.UUID | None = None
    payment_term_id: uuid.UUID | None = None


@dataclass
class ComputeResult:
    deadlines: list[ComputedDeadline] = field(default_factory=list)
    rule_errors: dict[uuid.UUID, str] = field(default_factory=dict)


def _period(amount: int | None, unit: object | None) -> engine.Period | None:
    if amount is None or unit is None:
        return None
    return engine.Period(amount, engine.Unit(str(unit)))


def calendar_for(contract: Contract, workspace: Workspace | None, default_country: str | None):
    country = contract.holiday_country or (workspace.country if workspace else None)
    country = country or default_country
    subdivision = contract.holiday_subdivision if contract.holiday_country else None
    return engine.Calendar(country=country, subdivision=subdivision)


def current_term(contract: Contract, as_of: date) -> engine.Term | None:
    initial = _period(contract.initial_term_amount, contract.initial_term_unit)
    if contract.effective_date and initial and initial.amount > 0:
        renewal = (
            _period(contract.renewal_term_amount, contract.renewal_term_unit)
            if contract.auto_renews
            else None
        )
        if contract.auto_renews and renewal is None:
            renewal = initial  # "renews for the same period" is the usual default
        return engine.term_containing(contract.effective_date, initial, renewal, as_of)
    if contract.end_date:
        start = contract.effective_date or contract.end_date
        return engine.Term(start, contract.end_date, 1)
    return None


def _terms_reviewed(contract: Contract) -> bool:
    return contract.reviewed_at is not None


def compute(
    contract: Contract,
    as_of: date,
    calendar: engine.Calendar,
) -> ComputeResult:
    result = ComputeResult()
    term = current_term(contract, as_of)
    renewal = (
        _period(contract.renewal_term_amount, contract.renewal_term_unit)
        if contract.auto_renews
        else None
    )
    if contract.auto_renews and renewal is None:
        renewal = _period(contract.initial_term_amount, contract.initial_term_unit)

    if term:
        renews = bool(contract.auto_renews)
        label = "Term renews automatically" if renews else "Contract expires"
        if term.is_renewal:
            label += f" (renewal term {term.number - 1})"
        result.deadlines.append(
            ComputedDeadline(
                kind=DeadlineKind.TERM_END,
                label=label,
                due_date=term.end,
                derivation=[
                    f"Current term: {engine.fmt(term.start)} – {engine.fmt(term.end)}",
                ],
                confirmed=_terms_reviewed(contract),
            )
        )

    for rule in contract.date_rules:
        if rule.review_status == ReviewStatus.REJECTED:
            continue
        try:
            computed = _compute_rule(contract, rule, term, renewal, as_of, calendar)
        except engine.DeadlineError as exc:
            result.rule_errors[rule.id] = str(exc)
            continue
        if isinstance(computed, str):
            result.rule_errors[rule.id] = computed
            continue
        result.deadlines.append(computed)

    for term_ in contract.payment_terms:
        if term_.review_status == ReviewStatus.REJECTED:
            continue
        result.deadlines.extend(_payment_deadlines(term_, as_of))
    return result


def _compute_rule(
    contract: Contract,
    rule: DateRule,
    term: engine.Term | None,
    renewal: engine.Period | None,
    as_of: date,
    calendar: engine.Calendar,
) -> ComputedDeadline | str:
    offset = _period(rule.offset_amount, rule.offset_unit) or engine.Period(0, engine.Unit.DAYS)
    if rule.offset_basis == "business":
        offset = engine.Period(offset.amount, offset.unit, engine.DayBasis.BUSINESS)
    delivery = (
        engine.Period(rule.delivery_amount, engine.Unit.DAYS, engine.DayBasis(rule.delivery_basis))
        if rule.delivery_amount
        else None
    )
    direction = engine.Direction(str(rule.direction))
    kind = _RULE_KIND.get(rule.rule_type, DeadlineKind.OTHER)
    roll = (
        engine.Roll.PRECEDING
        if kind in (DeadlineKind.NOTICE, DeadlineKind.OPTION)
        else (engine.Roll.NONE)
    )

    if rule.anchor == DateAnchor.FIXED_DATE:
        if not rule.fixed_date:
            return "The rule needs a fixed date"
        res = engine.compute_deadline(
            rule.fixed_date, "Date in contract", offset, direction, calendar, roll, delivery
        )
    elif rule.anchor == DateAnchor.EFFECTIVE_DATE:
        if not contract.effective_date:
            return "The contract's effective date is unknown"
        res = engine.compute_deadline(
            contract.effective_date, "Effective date", offset, direction, calendar, roll, delivery
        )
    else:
        if term is None:
            return "The contract term is unknown"
        if rule.anchor == DateAnchor.TERM_START:
            res = engine.compute_deadline(
                term.start, "Start of current term", offset, direction, calendar, roll, delivery
            )
        else:
            initial = _period(contract.initial_term_amount, contract.initial_term_unit)
            if (
                direction is engine.Direction.BEFORE
                and contract.effective_date
                and initial
                and renewal
            ):
                # Auto-renewing: if this term's deadline has passed, roll to the next term.
                term, res = engine.notice_deadline(
                    contract.effective_date,
                    initial,
                    renewal,
                    offset,
                    as_of,
                    calendar,
                    roll,
                    delivery,
                )
            else:
                label = (
                    f"End of renewal term {term.number - 1}" if term.is_renewal else "End of term"
                )
                res = engine.compute_deadline(
                    term.end, label, offset, direction, calendar, roll, delivery
                )

    return ComputedDeadline(
        kind=kind,
        label=rule.label,
        due_date=res.date,
        derivation=res.steps,
        confirmed=rule.review_status in _REVIEWED,
        date_rule_id=rule.id,
    )


def _payment_deadlines(term: PaymentTerm, as_of: date) -> list[ComputedDeadline]:
    if term.first_due_date is None:
        return []
    confirmed = term.review_status in _REVIEWED
    label = f"Payment: {term.description}"
    if term.frequency == PaymentFrequency.ONE_OFF or term.frequency not in _FREQUENCY_MONTHS:
        dates = [term.first_due_date]
    else:
        step = _FREQUENCY_MONTHS[term.frequency]
        horizon = as_of + relativedelta(months=PAYMENT_HORIZON_MONTHS)
        dates = []
        i = 0
        while True:
            d = term.first_due_date + relativedelta(months=step * i)
            if d > horizon or i > 1000:
                break
            # Keep the most recent past occurrence too, so overdue payments stay visible.
            next_d = term.first_due_date + relativedelta(months=step * (i + 1))
            if d >= as_of or next_d > as_of:
                dates.append(d)
            i += 1
    return [
        ComputedDeadline(
            kind=DeadlineKind.PAYMENT,
            label=label,
            due_date=d,
            derivation=[
                f"First payment: {engine.fmt(term.first_due_date)}",
                f"Frequency: {term.frequency.replace('_', '-')}",
            ],
            confirmed=confirmed,
            payment_term_id=term.id,
        )
        for d in dates
    ]


def refresh_deadlines(
    db: Session, contract: Contract, default_country: str | None, as_of: date | None = None
) -> None:
    """Recompute the contract's deadlines, keeping the status users set on existing ones."""
    as_of = as_of or date.today()
    workspace = db.get(Workspace, contract.workspace_id)
    calendar = calendar_for(contract, workspace, default_country)
    try:
        result = compute(contract, as_of, calendar)
    except engine.DeadlineError as exc:
        # e.g. an unknown holiday country: fall back to weekends only.
        result = compute(contract, as_of, engine.Calendar())
        result.rule_errors = {r.id: str(exc) for r in contract.date_rules}

    # User state (done/dismissed, decisions) is kept for deadlines that still exist.
    user_fields = ("status", "decision", "decision_note", "decided_at", "decided_by_id")
    previous = {
        (d.date_rule_id, d.payment_term_id, d.kind, d.due_date): {
            f: getattr(d, f) for f in user_fields
        }
        for d in contract.deadlines
    }
    contract.deadlines.clear()
    db.flush()
    for c in result.deadlines:
        key = (c.date_rule_id, c.payment_term_id, c.kind, c.due_date)
        contract.deadlines.append(
            Deadline(
                organization_id=contract.organization_id,
                workspace_id=contract.workspace_id,
                date_rule_id=c.date_rule_id,
                payment_term_id=c.payment_term_id,
                kind=c.kind,
                label=c.label,
                due_date=c.due_date,
                derivation=c.derivation,
                confirmed=c.confirmed,
                **previous.get(key, {"status": DeadlineStatus.OPEN}),
            )
        )
    for rule in contract.date_rules:
        rule.compute_error = result.rule_errors.get(rule.id)
