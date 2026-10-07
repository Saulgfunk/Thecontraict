"""Stateless deadline calculator, used by the UI to preview and explain dates."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.deadlines import engine
from app.models import User

router = APIRouter(prefix="/deadlines", tags=["deadlines"])


class PeriodIn(BaseModel):
    amount: int = Field(ge=0, le=36500)
    unit: engine.Unit
    basis: engine.DayBasis = engine.DayBasis.CALENDAR

    def to_engine(self) -> engine.Period:
        return engine.Period(self.amount, self.unit, self.basis)


class CalendarIn(BaseModel):
    country: str | None = Field(default=None, min_length=2, max_length=2)
    subdivision: str | None = None
    weekend: list[int] = Field(default=[5, 6], description="0=Monday … 6=Sunday")

    def to_engine(self) -> engine.Calendar:
        return engine.Calendar(
            country=self.country.upper() if self.country else None,
            subdivision=self.subdivision,
            weekend=frozenset(self.weekend),
        )


class NoticePreviewIn(BaseModel):
    effective_date: date
    initial_term: PeriodIn
    renewal_term: PeriodIn | None = None
    notice_period: PeriodIn
    delivery_period: PeriodIn | None = None
    calendar: CalendarIn = CalendarIn()
    roll: engine.Roll = engine.Roll.PRECEDING
    as_of: date | None = None


class TermOut(BaseModel):
    number: int
    start: date
    end: date


class NoticePreviewOut(BaseModel):
    term: TermOut
    notice_deadline: date
    days_left: int
    derivation: list[str]


@router.post("/notice-preview", response_model=NoticePreviewOut)
def notice_preview(body: NoticePreviewIn, _: User = Depends(get_current_user)) -> NoticePreviewOut:
    as_of = body.as_of or date.today()
    try:
        term, result = engine.notice_deadline(
            effective=body.effective_date,
            initial_term=body.initial_term.to_engine(),
            renewal_term=body.renewal_term.to_engine() if body.renewal_term else None,
            notice=body.notice_period.to_engine(),
            as_of=as_of,
            calendar=body.calendar.to_engine(),
            roll_mode=body.roll,
            delivery=body.delivery_period.to_engine() if body.delivery_period else None,
        )
    except engine.DeadlineError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return NoticePreviewOut(
        term=TermOut(number=term.number, start=term.start, end=term.end),
        notice_deadline=result.date,
        days_left=(result.date - as_of).days,
        derivation=result.steps,
    )
