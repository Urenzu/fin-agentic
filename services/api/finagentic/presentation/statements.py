"""Assembling a renderable statement from the ledger.

This is the boundary between the ledger and the UI. It turns an unordered bag of
verified facts into the thing a reader recognises: ordered lines, indented
components, subtotals, and a column per period.

Two decisions shape the output.

**Ordering comes from the concept registry, not from the filing.** `companyfacts`
returns values with no presentation information -- no line order, no hierarchy,
no filer labels. Those live in the filing's presentation linkbase, which this
endpoint does not expose. So the canonical view renders every company in the
same order, which makes two filers directly comparable. A future "view as filed"
mode will reproduce each company's own layout from the SEC's rendered exhibits.

**Absence and unverified are different, and both are visible.** A line the
company did not report is omitted. A line reported but not corroborated by any
identity check is present and marked. Silently dropping the latter would hide a
gap; silently showing it as normal would overstate what we know.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from finagentic.domain.concepts import (
    Concept,
    ConceptMeta,
    Statement,
    Unit,
    statement_layout,
)
from finagentic.domain.facts import FactStatus
from finagentic.domain.ledger import FactSet
from finagentic.domain.periods import Period


@dataclass(frozen=True, slots=True)
class Cell:
    """One value, for one line, in one period column."""

    value: Decimal
    status: FactStatus
    fact_id: UUID
    #: Where the figure came from, ready to render as a link.
    source_url: str | None = None
    #: The us-gaap tag or printed row label it was mapped from. Shown on hover so
    #: a reader can check the mapping decision without leaving the statement.
    source_label: str | None = None

    @property
    def is_verified(self) -> bool:
        return self.status is FactStatus.VERIFIED


@dataclass(frozen=True, slots=True)
class StatementLine:
    """One row of a rendered statement."""

    concept: Concept
    label: str
    indent: int
    is_subtotal: bool
    unit: Unit
    #: Keyed by period label. Absent keys are genuinely unreported, not zero.
    cells: dict[str, Cell]

    @property
    def is_empty(self) -> bool:
        return not self.cells


@dataclass(frozen=True, slots=True)
class StatementView:
    """A statement, ready to render."""

    statement: Statement
    #: Column order, oldest first.
    periods: tuple[Period, ...]
    lines: tuple[StatementLine, ...]

    @property
    def period_labels(self) -> tuple[str, ...]:
        return tuple(p.label for p in self.periods)

    @property
    def verified_ratio(self) -> float:
        """Share of rendered values corroborated by an identity check.

        Surfaced so a reader can tell at a glance whether they are looking at a
        statement that reconciles or a collection of unchecked figures.
        """
        cells = [c for line in self.lines for c in line.cells.values()]
        if not cells:
            return 0.0
        return sum(1 for c in cells if c.is_verified) / len(cells)

    def line_for(self, concept: Concept) -> StatementLine | None:
        return next((line for line in self.lines if line.concept is concept), None)


def build_statement(
    facts: FactSet,
    statement: Statement,
    periods: list[Period] | tuple[Period, ...],
    *,
    include_unverified: bool = True,
) -> StatementView:
    """Assemble `statement` for `periods` from `facts`.

    Lines with no data in any requested period are dropped rather than rendered
    blank -- a company that reports no inventory should not show an empty
    inventory row, because that implies a zero it never stated.
    """
    ordered_periods = tuple(sorted(periods, key=lambda p: p.end_date))
    lines: list[StatementLine] = []

    for concept, cm in statement_layout(statement):
        cells: dict[str, Cell] = {}
        for period in ordered_periods:
            fact = facts.get(concept, period)
            if fact is None:
                continue
            if not include_unverified and not fact.is_usable:
                continue
            cells[period.label] = Cell(
                value=fact.value,
                status=fact.status,
                fact_id=fact.id,
                source_url=_source_url(fact),
                source_label=_source_label(fact),
            )

        if cells:
            lines.append(_line(concept, cm, cells))

    return StatementView(
        statement=statement,
        periods=ordered_periods,
        lines=tuple(lines),
    )


def _line(concept: Concept, cm: ConceptMeta, cells: dict[str, Cell]) -> StatementLine:
    return StatementLine(
        concept=concept,
        label=cm.label,
        indent=cm.indent,
        is_subtotal=cm.is_subtotal,
        unit=cm.unit,
        cells=cells,
    )


def _source_url(fact: object) -> str | None:
    provenance = getattr(fact, "provenance", None)
    return getattr(provenance, "filing_url", None)


def _source_label(fact: object) -> str | None:
    provenance = getattr(fact, "provenance", None)
    # XBRL facts carry the us-gaap tag; PDF facts carry the printed row label.
    return getattr(provenance, "tag", None) or getattr(provenance, "row_label", None)


def annual_periods(facts: FactSet, statement: Statement, limit: int = 5) -> list[Period]:
    """The most recent annual periods for `statement`, oldest first.

    Balance sheets are instants and the other statements are durations, so the
    period kind is taken from the statement rather than requested separately --
    asking for "FY2024" means a different thing on each.
    """
    from finagentic.domain.concepts import PeriodKind
    from finagentic.domain.periods import FiscalPeriod

    wanted_kind = (
        PeriodKind.INSTANT if statement is Statement.BALANCE_SHEET else PeriodKind.DURATION
    )
    candidates = [
        p
        for p in facts.periods()
        if p.kind is wanted_kind and p.fiscal_period is FiscalPeriod.FY
    ]
    return sorted(candidates, key=lambda p: p.end_date)[-limit:]


def render_text(view: StatementView, *, scale: Decimal = Decimal(10**6)) -> str:
    """Plain-text rendering, for tests and terminal inspection.

    Not what the UI uses, but it keeps the view model checkable without a
    browser and makes failures in this module legible in a test log.
    """
    width = 52
    header = " " * width + "".join(f"{lbl:>16s}" for lbl in view.period_labels)
    rows = [header, "-" * len(header)]

    for line in view.lines:
        label = "  " * line.indent + line.label
        cells = []
        for period_label in view.period_labels:
            cell = line.cells.get(period_label)
            if cell is None:
                cells.append(f"{'':>16s}")
                continue
            if line.unit is Unit.USD:
                shown = f"{cell.value / scale:,.0f}"
            elif line.unit is Unit.USD_PER_SHARE:
                shown = f"{cell.value:,.2f}"
            else:
                shown = f"{cell.value / scale:,.1f}"
            mark = "" if cell.is_verified else " ?"
            cells.append(f"{shown + mark:>16s}")
        rows.append(f"{label:<{width}.{width}s}" + "".join(cells))
        if line.is_subtotal:
            rows.append(" " * width + "".join("  " + "-" * 14 for _ in view.period_labels))

    return "\n".join(rows)
