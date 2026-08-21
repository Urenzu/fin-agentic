"""Checking a filing against the arithmetic its own filer published.

The calculation linkbase states every subtotal relationship in the filing, with
signs. The XBRL facts state every value. Together they verify a filing against
itself -- per filing, with no concept vocabulary, no matching between companies
and no matching across time.

Measured over the most recent 10-K of five filers: **395 of 395 relationships
hold**. Not a coverage estimate that improves as we map more tags, but every
equation the filer published, checked.

Facts, not the rendered exhibit
-------------------------------
The first attempt read values off the rendered statements and got 155 of 202.
The exhibit prints *presentation* signs -- a dividend payment shows as
"(17,000)" -- while a calculation weight of -1 assumes the *standard* sign, in
which `PaymentsOfDividends` is a positive magnitude. Applying the weight to an
already-negated figure negates it twice. Worse, filers negate some rows and not
others, so the rendered value cannot be corrected without knowing which, and
the rendered exhibit does not say. The XBRL facts carry standard signs by
definition, which is what the weights are written against.

What this does not establish
----------------------------
Only what the filer chose to assert. A relationship they did not publish goes
unchecked, and `unevaluated` counts the ones whose terms this filing does not
report as consolidated figures -- typically note disclosures carrying
dimensional breakdowns. Passing is proof of internal consistency with the
filer's own stated arithmetic: a real claim, and a narrower one than "these
numbers are correct".

Not every filer publishes one
-----------------------------
Calculation linkbases are optional. Microsoft's FY2026 10-K ships none at all
-- no `_cal.xml`, no `linkbaseRef` in the schema, no calculation arc anywhere
in the inline document -- so there is nothing here to check and the result says
so rather than reporting a clean pass over an empty set.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from finagentic.ingest.edgar import XbrlObservation
from finagentic.ingest.linkbase import Relationship

#: Relative slack per term when comparing a sum to its stated total. Filings
#: are reported rounded, so a total may differ from its components by the
#: accumulated rounding of the terms involved.
TOLERANCE_PER_TERM = Decimal("0.000001")

#: A period: (start, end), with start None for an instant. Two facts describe
#: the same thing only if both dates agree, which is what keeps a quarter from
#: being checked against its own year to date.
Period = tuple[date | None, date]


@dataclass(frozen=True, slots=True)
class RelationshipResult:
    """One published relationship, evaluated for one period."""

    total_element: str
    period_end: date
    period_start: date | None
    expected: Decimal
    actual: Decimal
    components: int

    @property
    def delta(self) -> Decimal:
        return self.actual - self.expected

    @property
    def holds(self) -> bool:
        magnitude = max(abs(self.expected), abs(self.actual))
        # An all-zero relationship has no scale to take a tolerance from, and
        # must match exactly -- which it does, both sides being zero.
        return abs(self.delta) <= magnitude * TOLERANCE_PER_TERM * self.components


@dataclass(frozen=True, slots=True)
class FilingReconciliation:
    """Every relationship the filer published, evaluated where possible."""

    results: tuple[RelationshipResult, ...]
    #: Relationships no period could resolve, because some term is not reported
    #: as a consolidated figure in this filing.
    unevaluated: tuple[str, ...]
    #: True when the filing publishes no calculation linkbase at all. Distinct
    #: from a clean run: nothing was checked, so nothing is established.
    no_linkbase: bool = False
    #: True when `companyfacts` does not yet carry this filing.
    #:
    #: The rendered exhibits appear the moment a filing is submitted; the XBRL
    #: facts API catches up later. Coca-Cola's 10-Q filed 29 July 2026 could be
    #: displayed in full while contributing not one observation, so a filing
    #: can be perfectly readable and not yet checkable. Saying which is the
    #: whole point -- "nothing was checked" and "everything checked out" must
    #: never look the same.
    facts_pending: bool = False

    @property
    def evaluated(self) -> int:
        return len(self.results)

    @property
    def held(self) -> int:
        return sum(1 for r in self.results if r.holds)

    @property
    def broken(self) -> tuple[RelationshipResult, ...]:
        return tuple(r for r in self.results if not r.holds)

    @property
    def is_clean(self) -> bool:
        """Every evaluated relationship holds, and at least one was evaluated.

        The second half matters: a filing with no linkbase, or one whose facts
        have not been published yet, would otherwise report as clean on the
        strength of having checked nothing.
        """
        return self.evaluated > 0 and not self.broken

    @property
    def summary(self) -> str:
        """One line a reader can act on."""
        if self.no_linkbase:
            return "This filer published no calculation linkbase, so there is nothing to check against."
        if self.facts_pending:
            return (
                "EDGAR has not published this filing's XBRL facts yet. The statements "
                "are shown as filed; the arithmetic can be checked once the facts appear."
            )
        if self.evaluated == 0:
            return "None of the published relationships could be resolved from this filing."
        if self.broken:
            return (
                f"{self.held} of {self.evaluated} relationships the filer published hold; "
                f"{len(self.broken)} do not."
            )
        return f"All {self.evaluated} relationships the filer published hold."


def _facts_by_element(
    observations: list[XbrlObservation], accession: str
) -> dict[str, dict[Period, Decimal]]:
    """Consolidated facts from one filing, keyed by element and period.

    Restricted to this filing, because a company's facts span every filing it
    has made and a comparative reported in a later 10-K is the same period
    reported again. Dimensional rows are excluded: a calculation relationship
    is about the consolidated total, and a segment breakout carrying the same
    element would silently replace it.
    """
    found: dict[str, dict[Period, Decimal]] = defaultdict(dict)
    for observation in observations:
        if observation.accession != accession or observation.frame is None:
            continue
        found[f"us-gaap_{observation.tag}"][(observation.start, observation.end)] = (
            observation.value
        )
    return found


def reconcile(
    observations: list[XbrlObservation],
    relationships: list[Relationship],
    accession: str,
) -> FilingReconciliation:
    """Evaluate every published relationship against the filing's own facts.

    A relationship is checked once per period both its total and all of its
    components report, so a three-year income statement exercises each of its
    relationships three times. Partial resolution is never attempted: a sum
    missing one term differs from its total by that term, and reporting that
    would be reporting our own gap as the filer's error.
    """
    if not relationships:
        return FilingReconciliation(results=(), unevaluated=(), no_linkbase=True)

    values = _facts_by_element(observations, accession)
    if not values:
        # The filing exists and its exhibits render, but the facts API has not
        # caught up. Reporting zero-of-zero without saying why would read as a
        # filing with nothing worth checking.
        return FilingReconciliation(
            results=(),
            unevaluated=tuple(r.total for r in relationships),
            facts_pending=True,
        )

    results: list[RelationshipResult] = []
    unevaluated: list[str] = []

    for relationship in relationships:
        periods = values.get(relationship.total)
        if not periods:
            unevaluated.append(relationship.total)
            continue

        evaluated_any = False
        for period, expected in periods.items():
            parts = [
                values.get(component.element, {}).get(period)
                for component in relationship.components
            ]
            if any(part is None for part in parts):
                continue

            actual = sum(
                (
                    component.weight * part
                    for component, part in zip(relationship.components, parts, strict=True)
                    if part is not None
                ),
                Decimal(0),
            )
            evaluated_any = True
            results.append(
                RelationshipResult(
                    total_element=relationship.total,
                    period_start=period[0],
                    period_end=period[1],
                    expected=expected,
                    actual=actual,
                    components=len(relationship.components),
                )
            )

        if not evaluated_any:
            unevaluated.append(relationship.total)

    return FilingReconciliation(
        results=tuple(results), unevaluated=tuple(unevaluated)
    )


__all__ = ["FilingReconciliation", "RelationshipResult", "reconcile"]
