"""Fiscal period modelling.

Periods are the second most common source of silent extraction error after scale
(the first being a column header misread, the second a fiscal-vs-calendar year
mismatch). Modelling them explicitly -- rather than as a bare year integer --
lets the validation layer check period arithmetic (Q1+Q2+Q3+Q4 == FY) and lets
the analytics engine refuse to compare a quarter against a full year.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from finagentic.domain.concepts import PeriodKind


class FiscalPeriod(StrEnum):
    FY = "FY"
    Q1 = "Q1"
    Q2 = "Q2"
    Q3 = "Q3"
    Q4 = "Q4"
    H1 = "H1"
    H2 = "H2"
    NINE_MONTHS = "9M"

    @property
    def months(self) -> int:
        return _PERIOD_MONTHS[self]

    @property
    def is_quarter(self) -> bool:
        return self in (FiscalPeriod.Q1, FiscalPeriod.Q2, FiscalPeriod.Q3, FiscalPeriod.Q4)


_PERIOD_MONTHS: dict[FiscalPeriod, int] = {
    FiscalPeriod.Q1: 3,
    FiscalPeriod.Q2: 3,
    FiscalPeriod.Q3: 3,
    FiscalPeriod.Q4: 3,
    FiscalPeriod.H1: 6,
    FiscalPeriod.H2: 6,
    FiscalPeriod.NINE_MONTHS: 9,
    FiscalPeriod.FY: 12,
}

#: Cumulative periods and the quarters that sum to them. Used by the period
#: arithmetic validator and by the "derive Q4 from FY minus 9M" reconciler.
PERIOD_COMPOSITION: dict[FiscalPeriod, tuple[FiscalPeriod, ...]] = {
    FiscalPeriod.H1: (FiscalPeriod.Q1, FiscalPeriod.Q2),
    FiscalPeriod.H2: (FiscalPeriod.Q3, FiscalPeriod.Q4),
    FiscalPeriod.NINE_MONTHS: (FiscalPeriod.Q1, FiscalPeriod.Q2, FiscalPeriod.Q3),
    FiscalPeriod.FY: (FiscalPeriod.Q1, FiscalPeriod.Q2, FiscalPeriod.Q3, FiscalPeriod.Q4),
}

#: Tolerance in days when checking a reported period span against its nominal
#: length. Accommodates 52/53-week fiscal calendars (Apple, retailers) where a
#: "quarter" may be 13 or 14 weeks and a "year" 52 or 53 weeks.
SPAN_TOLERANCE_DAYS = 14


class Period(BaseModel):
    """A fiscal period, either an instant or a duration.

    `fiscal_year` is the year the period is *reported under*, which is not
    necessarily the calendar year of `end_date`. A company with a January
    fiscal year-end reports FY2024 ending 2024-01-31.
    """

    model_config = ConfigDict(frozen=True)

    kind: PeriodKind
    fiscal_year: int = Field(ge=1900, le=2200)
    fiscal_period: FiscalPeriod
    #: Inclusive start of a duration period; None for an instant.
    start_date: date | None = None
    #: The measurement date for an instant, or the inclusive end of a duration.
    end_date: date

    @model_validator(mode="after")
    def _check_shape(self) -> Self:
        if self.kind is PeriodKind.INSTANT:
            if self.start_date is not None:
                raise ValueError("instant period must not have a start_date")
            return self

        if self.start_date is None:
            raise ValueError("duration period requires a start_date")
        if self.start_date > self.end_date:
            raise ValueError(f"start_date {self.start_date} is after end_date {self.end_date}")

        nominal = self.fiscal_period.months * 30.44
        actual = (self.end_date - self.start_date).days + 1
        if abs(actual - nominal) > _span_tolerance(self.fiscal_period):
            raise ValueError(
                f"{self.fiscal_period} span of {actual} days is inconsistent with a "
                f"{self.fiscal_period.months}-month period ending {self.end_date}"
            )
        return self

    @property
    def label(self) -> str:
        """Human-facing label, e.g. 'FY2024' or 'Q3 2024'."""
        if self.fiscal_period is FiscalPeriod.FY:
            return f"FY{self.fiscal_year}"
        return f"{self.fiscal_period.value} {self.fiscal_year}"

    @property
    def key(self) -> tuple[int, str, str]:
        """Stable identity used to group facts describing the same period."""
        return (self.fiscal_year, self.fiscal_period.value, self.kind.value)

    def is_comparable_to(self, other: Period) -> bool:
        """True when two periods measure spans of the same type and length.

        Comparing a quarter to a fiscal year produces a meaningless growth rate,
        so the analytics engine gates every period-over-period metric on this.
        """
        return self.kind is other.kind and self.fiscal_period.months == other.fiscal_period.months

    def prior_year(self) -> Period:
        """The same fiscal period one year earlier.

        Dates are shifted by exactly 364 days (52 weeks) rather than by calendar
        year so that 52/53-week fiscal calendars stay aligned to the same weekday.
        The result is a *query template*: it locates the comparable period by
        `fiscal_year` and `fiscal_period`, and its dates are approximate.
        """
        shift = 364
        return Period(
            kind=self.kind,
            fiscal_year=self.fiscal_year - 1,
            fiscal_period=self.fiscal_period,
            start_date=None if self.start_date is None else _shift(self.start_date, shift),
            end_date=_shift(self.end_date, shift),
        )


def _span_tolerance(period: FiscalPeriod) -> float:
    """Days of slack allowed on a period span.

    A 53-week fiscal year is 7 days longer than a 52-week one, and month-length
    variation alone moves a nominal 30.44-day month by up to ~3 days. The base
    tolerance covers the 52/53-week case; the per-month term covers accumulated
    month-length drift in longer periods.
    """
    return SPAN_TOLERANCE_DAYS + 1.5 * period.months


def _shift(d: date, days: int) -> date:
    from datetime import timedelta

    return d + timedelta(days=days)
