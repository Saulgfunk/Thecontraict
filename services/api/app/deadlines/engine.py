"""Deterministic deadline computation.

The AI extracts *rules* from contracts ("notice must be received at least 90 days
before the end of the term"); this module turns rules into concrete dates and records
every step so users can verify the result. No AI is involved here, by design.

Conventions:
- A term of N months starting on S ends on ``S + N months - 1 day`` (inclusive end),
  and a renewal term starts the day after the previous term ends.
- Month arithmetic clamps to the end of the month (31 Jan + 1 month = 28/29 Feb).
- Business days skip weekends (Sat/Sun unless configured) and public holidays of the
  given country (and optional subdivision).
"""

import enum
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache

import holidays as holidays_lib
from dateutil.relativedelta import relativedelta


class Unit(enum.StrEnum):
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"
    YEARS = "years"


class DayBasis(enum.StrEnum):
    CALENDAR = "calendar"
    BUSINESS = "business"


class Direction(enum.StrEnum):
    BEFORE = "before"
    AFTER = "after"


class Roll(enum.StrEnum):
    """How to adjust a date that falls on a non-business day."""

    NONE = "none"
    PRECEDING = "preceding"  # conservative choice for "must act by" deadlines
    FOLLOWING = "following"


DEFAULT_WEEKEND = frozenset({5, 6})  # Saturday, Sunday (date.weekday())


class DeadlineError(ValueError):
    pass


@dataclass(frozen=True)
class Period:
    amount: int
    unit: Unit
    basis: DayBasis = DayBasis.CALENDAR

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise DeadlineError("Period amount must not be negative")
        if self.basis is DayBasis.BUSINESS and self.unit is not Unit.DAYS:
            raise DeadlineError("Business-day periods must be expressed in days")

    def describe(self) -> str:
        unit = self.unit.value if self.amount != 1 else self.unit.value.rstrip("s")
        if self.basis is DayBasis.BUSINESS:
            unit = "business " + unit
        elif self.unit is Unit.DAYS:
            unit = "calendar " + unit
        return f"{self.amount} {unit}"


@dataclass(frozen=True)
class Calendar:
    """Which days count as business days."""

    country: str | None = None
    subdivision: str | None = None
    weekend: frozenset[int] = DEFAULT_WEEKEND

    def holiday_name(self, day: date) -> str | None:
        if self.country is None:
            return None
        return _holidays(self.country, self.subdivision, day.year).get(day)

    def is_business_day(self, day: date) -> bool:
        return day.weekday() not in self.weekend and self.holiday_name(day) is None

    def why_not_business_day(self, day: date) -> str:
        if day.weekday() in self.weekend:
            return f"a {day.strftime('%A')}"
        return f"a public holiday ({self.holiday_name(day)})"


@lru_cache(maxsize=256)
def _holidays(country: str, subdivision: str | None, year: int) -> holidays_lib.HolidayBase:
    try:
        return holidays_lib.country_holidays(country, subdiv=subdivision, years=year)
    except NotImplementedError as exc:
        raise DeadlineError(f"No holiday calendar available for {country}") from exc


@dataclass
class Result:
    date: date
    steps: list[str] = field(default_factory=list)

    @property
    def derivation(self) -> str:
        return "\n".join(self.steps)


def fmt(day: date) -> str:
    return f"{day.strftime('%a')} {day.day} {day.strftime('%b %Y')}"


def shift(
    start: date,
    period: Period,
    direction: Direction,
    calendar: Calendar | None = None,
) -> date:
    """Move ``start`` by ``period`` in ``direction``."""
    sign = 1 if direction is Direction.AFTER else -1
    if period.basis is DayBasis.BUSINESS:
        if calendar is None:
            raise DeadlineError("A calendar is required for business-day periods")
        day, remaining = start, period.amount
        while remaining:
            day += timedelta(days=sign)
            if calendar.is_business_day(day):
                remaining -= 1
        return day
    delta = {
        Unit.DAYS: relativedelta(days=period.amount),
        Unit.WEEKS: relativedelta(weeks=period.amount),
        Unit.MONTHS: relativedelta(months=period.amount),
        Unit.YEARS: relativedelta(years=period.amount),
    }[period.unit]
    return start + delta if sign > 0 else start - delta


def roll(day: date, mode: Roll, calendar: Calendar, steps: list[str] | None = None) -> date:
    if mode is Roll.NONE or calendar.is_business_day(day):
        return day
    reason = calendar.why_not_business_day(day)
    step = timedelta(days=-1 if mode is Roll.PRECEDING else 1)
    rolled = day
    while not calendar.is_business_day(rolled):
        rolled += step
    if steps is not None:
        label = "preceding" if mode is Roll.PRECEDING else "following"
        steps.append(f"{fmt(day)} is {reason} → moved to {fmt(rolled)} ({label} business day)")
    return rolled


def term_end(start: date, term: Period) -> date:
    """Inclusive last day of a term that starts on ``start``."""
    if term.amount == 0:
        raise DeadlineError("Term length must be positive")
    return shift(start, term, Direction.AFTER) - timedelta(days=1)


@dataclass(frozen=True)
class Term:
    start: date
    end: date
    number: int  # 1 = initial term, 2 = first renewal, ...

    @property
    def is_renewal(self) -> bool:
        return self.number > 1


def term_containing(
    effective: date,
    initial_term: Period,
    renewal_term: Period | None,
    as_of: date,
    max_renewals: int | None = None,
) -> Term:
    """The term in force on ``as_of`` (or the last term, if the contract has ended).

    ``renewal_term`` None means no automatic renewal.
    """
    current = Term(effective, term_end(effective, initial_term), 1)
    while current.end < as_of and renewal_term is not None:
        if max_renewals is not None and current.number > max_renewals:
            break
        start = current.end + timedelta(days=1)
        current = Term(start, term_end(start, renewal_term), current.number + 1)
    return current


def terms(
    effective: date, initial_term: Period, renewal_term: Period | None, count: int
) -> Iterable[Term]:
    """The first ``count`` terms (stops after the initial term if there is no renewal)."""
    current = Term(effective, term_end(effective, initial_term), 1)
    for _ in range(count):
        yield current
        if renewal_term is None:
            return
        start = current.end + timedelta(days=1)
        current = Term(start, term_end(start, renewal_term), current.number + 1)


def compute_deadline(
    anchor: date,
    anchor_label: str,
    offset: Period,
    direction: Direction,
    calendar: Calendar | None = None,
    roll_mode: Roll = Roll.NONE,
    delivery: Period | None = None,
) -> Result:
    """Compute a deadline relative to an anchor date.

    ``delivery`` handles deemed-receipt clauses: if notice is only deemed received
    e.g. 2 business days after sending, the notice must be *sent* that much earlier.
    """
    calendar = calendar or Calendar()
    steps = [f"{anchor_label}: {fmt(anchor)}"]

    day = shift(anchor, offset, direction, calendar)
    sign = "−" if direction is Direction.BEFORE else "+"
    steps.append(f"{sign} {offset.describe()} → {fmt(day)}")
    day = roll(day, roll_mode, calendar, steps)

    if delivery is not None and delivery.amount:
        day = shift(day, delivery, Direction.BEFORE, calendar)
        steps.append(f"− {delivery.describe()} for deemed receipt → send by {fmt(day)}")
        day = roll(day, roll_mode, calendar, steps)

    return Result(day, steps)


def notice_deadline(
    effective: date,
    initial_term: Period,
    renewal_term: Period | None,
    notice: Period,
    as_of: date,
    calendar: Calendar | None = None,
    roll_mode: Roll = Roll.PRECEDING,
    delivery: Period | None = None,
) -> tuple[Term, Result]:
    """Last day to give notice of non-renewal for the next upcoming opportunity.

    If the notice deadline for the current term has already passed on ``as_of`` and the
    contract auto-renews, the deadline for the following term is returned instead.
    """
    term = term_containing(effective, initial_term, renewal_term, as_of)
    while True:
        label = f"renewal term {term.number - 1}" if term.is_renewal else "initial term"
        result = compute_deadline(
            term.end,
            f"End of {label}",
            notice,
            Direction.BEFORE,
            calendar,
            roll_mode,
            delivery,
        )
        if result.date >= as_of or renewal_term is None:
            return term, result
        start = term.end + timedelta(days=1)
        term = Term(start, term_end(start, renewal_term), term.number + 1)
