"""An indexed, queryable collection of facts.

`FactSet` is the in-memory working surface the validators and analytics engine
operate over. It is immutable and index-backed so that lookup by
(concept, period) is O(1) -- the identity checks and metric definitions do a
great many such lookups and they should not each scan the ledger.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from decimal import Decimal
from typing import overload

from finagentic.domain.concepts import Concept, Statement, meta
from finagentic.domain.facts import FactKey, FactStatus, FinancialFact
from finagentic.domain.periods import Period


class FactSet:
    """An immutable, indexed collection of `FinancialFact`."""

    __slots__ = ("_by_key", "_by_period", "_facts")

    def __init__(self, facts: Iterable[FinancialFact] = ()) -> None:
        self._facts: tuple[FinancialFact, ...] = tuple(facts)
        self._by_key: dict[FactKey, list[FinancialFact]] = {}
        self._by_period: dict[tuple[str, str | None, str], list[FinancialFact]] = {}
        for fact in self._facts:
            self._by_key.setdefault(FactKey.of(fact), []).append(fact)
            self._by_period.setdefault(fact.period.key, []).append(fact)

    def __len__(self) -> int:
        return len(self._facts)

    def __iter__(self) -> Iterator[FinancialFact]:
        return iter(self._facts)

    def __repr__(self) -> str:
        return f"FactSet({len(self._facts)} facts)"

    # ---- lookup -----------------------------------------------------------

    def get(
        self,
        concept: Concept,
        period: Period,
        *,
        usable_only: bool = False,
    ) -> FinancialFact | None:
        """Return the single fact for `concept` in `period`, or None.

        When several facts occupy the same slot the set is ambiguous and this
        returns None rather than guessing. Run the reconciler first to collapse
        duplicates and mark genuine disagreements CONFLICTED.
        """
        candidates = [f for f in self._by_period.get(period.key, ()) if f.concept is concept]
        if usable_only:
            candidates = [f for f in candidates if f.is_usable]
        if len(candidates) != 1:
            return None
        return candidates[0]

    def value(
        self,
        concept: Concept,
        period: Period,
        *,
        usable_only: bool = False,
    ) -> Decimal | None:
        """Return the normalised value for `concept` in `period`, or None."""
        fact = self.get(concept, period, usable_only=usable_only)
        return None if fact is None else fact.value

    @overload
    def require(self, concepts: Concept, period: Period) -> Decimal | None: ...
    @overload
    def require(
        self, concepts: tuple[Concept, ...], period: Period
    ) -> tuple[Decimal, ...] | None: ...

    def require(
        self,
        concepts: Concept | tuple[Concept, ...],
        period: Period,
    ) -> Decimal | tuple[Decimal, ...] | None:
        """Fetch one or several values, returning None if *any* is missing.

        Metrics use this so that a partially-populated period yields "not
        available" rather than a number computed from an implicit zero.
        """
        if isinstance(concepts, Concept):
            return self.value(concepts, period)
        values = tuple(self.value(c, period) for c in concepts)
        if any(v is None for v in values):
            return None
        return values  # type: ignore[return-value]

    def sum_of(self, concepts: Iterable[Concept], period: Period) -> Decimal:
        """Sum the values present for `concepts`, skipping those absent.

        Only appropriate where absence genuinely means zero -- an optional line
        item a company does not report, such as minority interest. Never use it
        for a component that must exist for the result to mean anything.
        """
        total = Decimal(0)
        for concept in concepts:
            v = self.value(concept, period)
            if v is not None:
                total += v
        return total

    # ---- slicing ----------------------------------------------------------

    def periods(self) -> list[Period]:
        """Distinct periods present, ordered chronologically."""
        seen: dict[tuple[str, str | None, str], Period] = {}
        for fact in self._facts:
            seen.setdefault(fact.period.key, fact.period)
        return sorted(seen.values(), key=lambda p: (p.end_date, p.fiscal_period.months))

    def for_statement(self, statement: Statement) -> FactSet:
        return FactSet(f for f in self._facts if meta(f.concept).statement is statement)

    def for_period(self, period: Period) -> FactSet:
        return FactSet(self._by_period.get(period.key, ()))

    def with_status(self, *statuses: FactStatus) -> FactSet:
        wanted = set(statuses)
        return FactSet(f for f in self._facts if f.status in wanted)

    def usable(self) -> FactSet:
        """Only facts cleared for display and for quoting by the agent."""
        return self.with_status(FactStatus.VERIFIED)

    def duplicates(self) -> dict[FactKey, list[FinancialFact]]:
        """Fact slots occupied by more than one fact."""
        return {k: v for k, v in self._by_key.items() if len(v) > 1}

    # ---- mutation (producing new sets) ------------------------------------

    def merge(self, other: FactSet) -> FactSet:
        return FactSet((*self._facts, *other._facts))

    def replace(self, facts: Iterable[FinancialFact]) -> FactSet:
        """Return a new set with `facts` substituted in by id.

        Verification produces status-updated copies of existing facts; this
        swaps them in while preserving order.
        """
        by_id = {f.id: f for f in facts}
        return FactSet(by_id.get(f.id, f) for f in self._facts)
