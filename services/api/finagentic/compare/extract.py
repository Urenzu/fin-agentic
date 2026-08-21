"""Pulling the twelve comparable figures out of a filing.

Read from the rendered statements rather than from `companyfacts`, for two
reasons. The exhibits exist the moment a filing is submitted while the facts
API catches up later -- Coca-Cola's 10-Q filed 29 July 2026 rendered in full
while contributing no observations at all -- and the exhibits are this system's
source of truth everywhere else, so comparison reads what the reader is
looking at.

The cost is signs. The exhibit prints presentation signs, so capital
expenditure appears as "(11,000)" because it reduces cash. Only outflow metrics
are affected and they are named here, so each is normalised to a magnitude on
the way out rather than a rule being inferred from the value.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from finagentic.compare.metrics import ALIASES, INSTANT, Metric, rank
from finagentic.ingest.rfiles import AsFiledStatement

#: Metrics the filing prints as a deduction, and that a reader means as a
#: positive amount. Capital expenditure of 11bn is 11bn spent, not -11bn.
OUTFLOWS: frozenset[Metric] = frozenset({Metric.CAPEX})


@dataclass(frozen=True, slots=True)
class MetricPeriod:
    """One metric for one column of one filing."""

    metric: Metric
    value: Decimal
    #: The element the value came from, so a reader can see which line was used
    #: when two filers report the same metric under different names.
    element: str
    label: str
    duration: str | None
    end_date: date | None

    @property
    def is_instant(self) -> bool:
        return self.duration is None


@dataclass(frozen=True, slots=True)
class FilingMetrics:
    """Every comparable figure a filing reports, by metric."""

    accession: str
    form: str
    periods: dict[Metric, tuple[MetricPeriod, ...]]

    def newest(self, metric: Metric) -> MetricPeriod | None:
        """The most recent period this filing reports for `metric`.

        Statements print the current period first, so that is what is taken --
        rather than the latest date, which for a 10-Q's balance sheet is the
        quarter end while its comparative is the prior fiscal year end.
        """
        found = self.periods.get(metric)
        return found[0] if found else None


def _best_row(statement: AsFiledStatement, metric: Metric):
    """The row that means `metric`, or None.

    A statement can print the same element more than once: Apple's income
    statement carries revenue for the consolidated total and again under each
    of Products and Services. The consolidated figure comes first -- a
    statement states a total before breaking it down -- so the first match on
    the best-ranked alias present is the one meant.
    """
    best = None
    best_rank = len(ALIASES[metric])
    for row in statement.rows:
        if row.is_abstract or not row.tag or not row.values or not row.is_us_gaap:
            continue
        position = rank(metric, row.tag)
        if position < best_rank:
            best, best_rank = row, position
    return best


def metrics_for(
    statements: list[AsFiledStatement], accession: str, form: str
) -> FilingMetrics:
    """Extract every comparable figure the filing reports.

    A metric may appear on more than one statement -- cash sits on the balance
    sheet and closes the cash flow statement -- so the best-ranked alias across
    the whole filing wins, and ties are broken by statement order, which puts
    the primary statements first.
    """
    collected: dict[Metric, tuple[int, list[MetricPeriod]]] = {}

    for statement in statements:
        for metric in Metric:
            row = _best_row(statement, metric)
            if row is None:
                continue

            position = rank(metric, row.tag or "")
            existing = collected.get(metric)
            if existing is not None and existing[0] <= position:
                continue

            found: list[MetricPeriod] = []
            for column in statement.columns:
                raw = row.values.get(column.key)
                if raw is None:
                    continue
                # A column has to be a period. The statement of shareholders'
                # equity is laid out with equity *components* across the top --
                # "Common Stock", "Total", "Cumulative Effect, Period of
                # Adoption" -- and its rows are the roll-forward, so a value
                # there is one movement in one component, not a balance at a
                # date. Tesla's equity read 45.5bn against a balance sheet
                # saying 82.1bn for exactly this reason. A heading that does
                # not parse as a date is not a period.
                if column.date is None:
                    continue
                # An instant metric taken from a duration column, or the
                # reverse, is a category error: a balance has no period and a
                # flow has no date.
                if (metric in INSTANT) != (column.duration is None):
                    continue
                value = abs(raw) if metric in OUTFLOWS else raw
                found.append(
                    MetricPeriod(
                        metric=metric,
                        value=value,
                        element=row.element or "",
                        label=column.label,
                        duration=column.duration,
                        end_date=column.date,
                    )
                )

            if found:
                collected[metric] = (position, found)

    return FilingMetrics(
        accession=accession,
        form=form,
        periods={metric: tuple(rows) for metric, (_, rows) in collected.items()},
    )


__all__ = ["OUTFLOWS", "FilingMetrics", "MetricPeriod", "metrics_for"]
