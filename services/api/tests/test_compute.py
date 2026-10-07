import uuid
from datetime import date

from app.deadlines.engine import Calendar
from app.models import (
    Contract,
    DateAnchor,
    DateRule,
    DateRuleType,
    DayBasis,
    DeadlineKind,
    OffsetDirection,
    PaymentFrequency,
    PaymentTerm,
    PeriodUnit,
    ReviewStatus,
)
from app.pipeline.compute import compute

UK = Calendar(country="GB", subdivision="ENG")


def make_contract(**kwargs: object) -> Contract:
    fields: dict[str, object] = {
        "title": "Test",
        "effective_date": date(2025, 1, 1),
        "initial_term_amount": 24,
        "initial_term_unit": PeriodUnit.MONTHS,
        "auto_renews": True,
        "renewal_term_amount": 12,
        "renewal_term_unit": PeriodUnit.MONTHS,
    }
    fields.update(kwargs)
    contract = Contract(**fields)
    contract.date_rules = []
    contract.payment_terms = []
    return contract


def notice_rule(**kwargs: object) -> DateRule:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "rule_type": DateRuleType.NON_RENEWAL_NOTICE,
        "label": "Notice of non-renewal",
        "anchor": DateAnchor.TERM_END,
        "offset_amount": 90,
        "offset_unit": PeriodUnit.DAYS,
        "offset_basis": DayBasis.CALENDAR,
        "direction": OffsetDirection.BEFORE,
        "delivery_basis": DayBasis.BUSINESS,
        "review_status": ReviewStatus.AI_SUGGESTED,
    }
    defaults.update(kwargs)
    return DateRule(**defaults)


def by_kind(result, kind):  # type: ignore[no-untyped-def]
    return [d for d in result.deadlines if d.kind == kind]


def test_term_end_and_notice_for_current_term() -> None:
    contract = make_contract()
    contract.date_rules = [notice_rule()]
    result = compute(contract, date(2026, 9, 1), UK)
    (term_end,) = by_kind(result, DeadlineKind.TERM_END)
    assert term_end.due_date == date(2026, 12, 31)
    assert term_end.label == "Term renews automatically"
    assert term_end.confirmed is False
    (notice,) = by_kind(result, DeadlineKind.NOTICE)
    assert notice.due_date == date(2026, 10, 2)
    assert notice.confirmed is False


def test_notice_rolls_to_next_term_and_applies_deemed_receipt() -> None:
    contract = make_contract()
    contract.date_rules = [notice_rule(delivery_amount=2, review_status=ReviewStatus.CONFIRMED)]
    result = compute(contract, date(2026, 10, 7), UK)
    (term_end,) = by_kind(result, DeadlineKind.TERM_END)
    assert term_end.due_date == date(2026, 12, 31)  # still in the initial term
    (notice,) = by_kind(result, DeadlineKind.NOTICE)
    # Next opportunity: term ending 31 Dec 2027 → Sat 2 Oct → Fri 1 Oct → −2 business days.
    assert notice.due_date == date(2027, 9, 29)
    assert notice.confirmed is True
    assert any("deemed receipt" in step for step in notice.derivation)


def test_fixed_term_contract_without_renewal() -> None:
    contract = make_contract(auto_renews=False)
    contract.date_rules = [notice_rule(rule_type=DateRuleType.TERMINATION_NOTICE)]
    result = compute(contract, date(2027, 6, 1), UK)
    (term_end,) = by_kind(result, DeadlineKind.TERM_END)
    assert term_end.label == "Contract expires"
    assert term_end.due_date == date(2026, 12, 31)
    (notice,) = by_kind(result, DeadlineKind.NOTICE)
    assert notice.due_date == date(2026, 10, 2)  # in the past; still shown as missed


def test_rules_that_cannot_be_computed_report_why() -> None:
    contract = make_contract(effective_date=None)
    fixed = notice_rule(anchor=DateAnchor.FIXED_DATE, rule_type=DateRuleType.PRICE_REVIEW)
    term = notice_rule()
    rejected = notice_rule(review_status=ReviewStatus.REJECTED)
    contract.date_rules = [fixed, term, rejected]
    result = compute(contract, date(2026, 1, 1), UK)
    assert result.rule_errors == {
        fixed.id: "The rule needs a fixed date",
        term.id: "The contract term is unknown",
    }
    assert result.deadlines == []


def test_end_date_only_contract() -> None:
    contract = make_contract(
        effective_date=None, initial_term_amount=None, initial_term_unit=None, auto_renews=None
    )
    contract.end_date = date(2027, 3, 31)
    contract.date_rules = [notice_rule(offset_amount=3, offset_unit=PeriodUnit.MONTHS)]
    result = compute(contract, date(2026, 10, 1), UK)
    assert [d.due_date for d in result.deadlines] == [date(2027, 3, 31), date(2026, 12, 31)]


def test_monthly_payments_within_horizon() -> None:
    contract = make_contract()
    contract.payment_terms = [
        PaymentTerm(
            id=uuid.uuid4(),
            description="Monthly fee",
            frequency=PaymentFrequency.MONTHLY,
            first_due_date=date(2025, 1, 1),
            review_status=ReviewStatus.CONFIRMED,
        )
    ]
    result = compute(contract, date(2026, 10, 7), UK)
    payments = by_kind(result, DeadlineKind.PAYMENT)
    dates = [p.due_date for p in payments]
    # The most recent past payment (1 Oct) stays visible, then 12 months ahead.
    assert dates[0] == date(2026, 10, 1)
    assert dates[-1] == date(2027, 10, 1)
    assert len(dates) == 13
    assert all(p.confirmed for p in payments)


def test_one_off_payment() -> None:
    contract = make_contract()
    contract.payment_terms = [
        PaymentTerm(
            id=uuid.uuid4(),
            description="Setup fee",
            frequency=PaymentFrequency.ONE_OFF,
            first_due_date=date(2025, 2, 1),
            review_status=ReviewStatus.AI_SUGGESTED,
        )
    ]
    result = compute(contract, date(2026, 10, 7), UK)
    assert [p.due_date for p in by_kind(result, DeadlineKind.PAYMENT)] == [date(2025, 2, 1)]
