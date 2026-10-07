from datetime import date

import pytest

from app.deadlines.engine import (
    Calendar,
    DayBasis,
    DeadlineError,
    Direction,
    Period,
    Roll,
    Unit,
    compute_deadline,
    notice_deadline,
    shift,
    term_containing,
    term_end,
    terms,
)

UK = Calendar(country="GB", subdivision="ENG")
MONTHS_12 = Period(12, Unit.MONTHS)
DAYS_90 = Period(90, Unit.DAYS)


def test_term_end_is_inclusive() -> None:
    assert term_end(date(2025, 1, 1), MONTHS_12) == date(2025, 12, 31)
    assert term_end(date(2025, 3, 15), Period(2, Unit.YEARS)) == date(2027, 3, 14)


def test_month_arithmetic_clamps_to_month_end() -> None:
    assert shift(date(2025, 1, 31), Period(1, Unit.MONTHS), Direction.AFTER) == date(2025, 2, 28)
    assert shift(date(2024, 5, 31), Period(3, Unit.MONTHS), Direction.BEFORE) == date(2024, 2, 29)


def test_business_days_skip_weekends_and_holidays() -> None:
    # Thu 24 Dec 2026 + 2 business days in England: Fri 25 Dec (Christmas) and Mon 28 Dec
    # (Boxing Day substitute) are holidays, so the days counted are Tue 29 and Wed 30 Dec.
    result = shift(date(2026, 12, 24), Period(2, Unit.DAYS, DayBasis.BUSINESS), Direction.AFTER, UK)
    assert result == date(2026, 12, 30)


def test_custom_weekend() -> None:
    fri_sat = Calendar(weekend=frozenset({4, 5}))
    # Thu 1 Oct 2026 + 1 business day with a Fri/Sat weekend → Sun 4 Oct.
    assert shift(
        date(2026, 10, 1), Period(1, Unit.DAYS, DayBasis.BUSINESS), Direction.AFTER, fri_sat
    ) == date(2026, 10, 4)


def test_business_basis_requires_days() -> None:
    with pytest.raises(DeadlineError):
        Period(1, Unit.MONTHS, DayBasis.BUSINESS)


def test_unknown_country_is_reported() -> None:
    with pytest.raises(DeadlineError):
        Calendar(country="XX").is_business_day(date(2026, 1, 1))


def test_compute_deadline_with_roll_and_derivation() -> None:
    # 2026-12-31 − 90 days = Fri 2 Oct 2026 (a business day, no roll).
    result = compute_deadline(
        date(2026, 12, 31), "End of term", DAYS_90, Direction.BEFORE, UK, Roll.PRECEDING
    )
    assert result.date == date(2026, 10, 2)
    assert result.steps == ["End of term: Thu 31 Dec 2026", "− 90 calendar days → Fri 2 Oct 2026"]

    # Weekend case: Sun 3 Jan 2027 − 3 months = Sat 3 Oct 2026 → rolled to Fri 2 Oct.
    rolled = compute_deadline(
        date(2027, 1, 3),
        "End of term",
        Period(3, Unit.MONTHS),
        Direction.BEFORE,
        UK,
        Roll.PRECEDING,
    )
    assert rolled.date == date(2026, 10, 2)
    assert "is a Saturday" in rolled.steps[-1]


def test_deemed_receipt_moves_send_date_earlier() -> None:
    result = compute_deadline(
        date(2026, 12, 31),
        "End of term",
        DAYS_90,
        Direction.BEFORE,
        UK,
        Roll.PRECEDING,
        delivery=Period(2, Unit.DAYS, DayBasis.BUSINESS),
    )
    # Fri 2 Oct − 2 business days = Wed 30 Sep.
    assert result.date == date(2026, 9, 30)
    assert "deemed receipt" in result.steps[-1]


def test_term_containing_follows_auto_renewals() -> None:
    term = term_containing(date(2023, 1, 1), MONTHS_12, MONTHS_12, as_of=date(2026, 6, 1))
    assert (term.start, term.end, term.number) == (date(2026, 1, 1), date(2026, 12, 31), 4)

    no_renewal = term_containing(date(2023, 1, 1), MONTHS_12, None, as_of=date(2026, 6, 1))
    assert no_renewal.end == date(2023, 12, 31)


def test_terms_sequence() -> None:
    ends = [t.end for t in terms(date(2025, 1, 1), Period(24, Unit.MONTHS), MONTHS_12, 3)]
    assert ends == [date(2026, 12, 31), date(2027, 12, 31), date(2028, 12, 31)]
    assert len(list(terms(date(2025, 1, 1), MONTHS_12, None, 5))) == 1


def test_notice_deadline_rolls_to_next_term_once_missed() -> None:
    # Term ends 31 Dec 2026, notice deadline Fri 2 Oct 2026.
    term, result = notice_deadline(
        date(2025, 1, 1),
        Period(24, Unit.MONTHS),
        MONTHS_12,
        DAYS_90,
        as_of=date(2026, 9, 1),
        calendar=UK,
    )
    assert term.end == date(2026, 12, 31)
    assert result.date == date(2026, 10, 2)

    # After that deadline, the next opportunity is for the renewal term ending 31 Dec 2027.
    term, result = notice_deadline(
        date(2025, 1, 1),
        Period(24, Unit.MONTHS),
        MONTHS_12,
        DAYS_90,
        as_of=date(2026, 10, 3),
        calendar=UK,
    )
    assert term.number == 2
    assert term.end == date(2027, 12, 31)
    assert result.date == date(2027, 10, 1)  # Sat 2 Oct 2027 → Fri 1 Oct
    assert result.steps[0].startswith("End of renewal term 1")


def test_notice_deadline_without_renewal_returns_past_deadline() -> None:
    _, result = notice_deadline(
        date(2025, 1, 1), MONTHS_12, None, DAYS_90, as_of=date(2026, 1, 1), calendar=UK
    )
    assert result.date == date(2025, 10, 2)
