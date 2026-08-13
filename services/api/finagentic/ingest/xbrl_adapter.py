"""Turning raw EDGAR observations into ledger facts.

Three problems have to be solved between "JSON from data.sec.gov" and "a
coherent time series", and each is handled explicitly here rather than being
allowed to resolve itself by accident:

1. **Period inference.** EDGAR gives start/end dates and usually a fiscal
   year/period label, but the label is missing on older filings and occasionally
   disagrees with the dates. Dates are authoritative; the label is a hint.

2. **Dimensional rows.** `companyfacts` mixes consolidated totals with segment
   and other dimensional breakouts. Summing them double-counts, so anything that
   is not a consolidated total is dropped.

3. **Restatements and repetition.** The same fiscal period is re-reported as a
   comparative in every subsequent filing -- FY2023 total assets appears in the
   FY2023 10-K and in four later filings. Usually all agree. When they do not,
   the company restated, and the most recently *filed* value is authoritative
   while the superseded one is retained for audit.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid5

from finagentic.domain.concepts import Concept, PeriodKind, Unit, meta
from finagentic.domain.facts import (
    SCALE_UNITS,
    FactStatus,
    FinancialFact,
    XbrlProvenance,
)
from finagentic.domain.ledger import FactSet
from finagentic.domain.periods import FiscalPeriod, Period
from finagentic.ingest.edgar import Registrant, XbrlObservation
from finagentic.ingest.tag_map import concept_for, tag_rank

#: Namespace for deriving a stable entity UUID from a CIK, so the same company
#: keeps the same id across runs without a database round-trip.
ENTITY_NAMESPACE = UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

#: Units EDGAR reports that the ledger understands. Anything else (pure ratios,
#: per-unit measures, foreign currencies) is out of scope for a USD three-
#: statement view and is skipped rather than silently treated as dollars.
UNIT_MAP: dict[str, Unit] = {
    "USD": Unit.USD,
    "shares": Unit.SHARES,
    "USD/shares": Unit.USD_PER_SHARE,
}

#: Forms whose figures belong in a three-statement history. Excludes 8-K
#: earnings releases, which carry preliminary unaudited numbers that are
#: routinely revised in the subsequent 10-Q/10-K.
ACCEPTED_FORMS = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F"})

#: How far a reported span may sit from its nominal length and still be accepted
#: as that period. Wide enough for 52/53-week fiscal calendars.
_SPAN_SLACK_DAYS = 20

_NOMINAL_SPANS: tuple[tuple[FiscalPeriod, int], ...] = (
    (FiscalPeriod.Q1, 91),
    (FiscalPeriod.H1, 182),
    (FiscalPeriod.NINE_MONTHS, 273),
    (FiscalPeriod.FY, 365),
)


#: A registrant filing less than this much history is almost certainly not the
#: entity the user meant. Set just above two years so a genuine recent IPO is
#: flagged too -- in that case the flag is still correct, since there really is
#: no long history to analyse.
MIN_EXPECTED_HISTORY_YEARS = 2.5


@dataclass(frozen=True, slots=True)
class AdaptationReport:
    """What happened during adaptation, so gaps are visible rather than implied."""

    accepted: int = 0
    skipped_unmapped_tag: int = 0
    skipped_dimensional: int = 0
    skipped_unsupported_unit: int = 0
    skipped_form: int = 0
    skipped_unresolvable_period: int = 0
    superseded_by_restatement: int = 0
    conflicting_tags_resolved: int = 0
    earliest: date | None = None
    latest: date | None = None
    annual_reports: int = 0

    @property
    def history_years(self) -> float:
        if self.earliest is None or self.latest is None:
            return 0.0
        return (self.latest - self.earliest).days / 365.25

    @property
    def looks_truncated(self) -> bool:
        """Whether this ledger is too thin to be the company the user meant.

        A ticker resolves to whichever CIK currently holds it. After a corporate
        reorganisation that is the new holding company, whose history begins at
        the reorganisation -- so `XOM` returns a few months of data while the
        decades of Exxon Mobil filings sit under the predecessor CIK.

        Returning that quietly would be the exact failure this system exists to
        prevent: not a wrong number, but a confident-looking answer built on
        almost no data. Callers must surface this rather than render a chart.
        """
        return self.history_years < MIN_EXPECTED_HISTORY_YEARS or self.annual_reports == 0

    def summary(self) -> str:
        span = (
            f"{self.earliest} to {self.latest} ({self.history_years:.1f}y, "
            f"{self.annual_reports} annual reports)"
            if self.earliest
            else "no dated facts"
        )
        warning = "  ** HISTORY LOOKS TRUNCATED **" if self.looks_truncated else ""
        return (
            f"{self.accepted} facts accepted covering {span}; skipped "
            f"{self.skipped_unmapped_tag} unmapped-tag, "
            f"{self.skipped_dimensional} dimensional, "
            f"{self.skipped_unsupported_unit} unsupported-unit, "
            f"{self.skipped_form} out-of-scope-form, "
            f"{self.skipped_unresolvable_period} unresolvable-period; "
            f"{self.superseded_by_restatement} superseded by restatement, "
            f"{self.conflicting_tags_resolved} tag conflicts resolved"
            f"{warning}"
        )


def entity_id_for(registrant: Registrant) -> UUID:
    """A stable UUID for a registrant, derived from its CIK."""
    return uuid5(ENTITY_NAMESPACE, f"cik:{registrant.cik}")


@dataclass(frozen=True, slots=True)
class FilingContext:
    """What one filing's own reporting period was.

    EDGAR stamps every row in a filing with that *filing's* fiscal year, not the
    fiscal year of the value. A FY2025 10-K carries FY2024 and FY2023
    comparatives, and all three arrive tagged `fy=2025`. Taking that field at
    face value labels a 2018 fiscal year as FY2020.

    The filing's own period is recoverable: it is the latest date any row in the
    filing refers to. Every earlier period in the same filing is a comparative,
    offset by whole years, so its label can be derived by counting back.
    """

    fiscal_year: int
    period_end: date


def build_filing_contexts(
    observations: list[XbrlObservation],
) -> dict[str, FilingContext]:
    """Map each accession to the reporting period of the filing it came from."""
    latest_end: dict[str, date] = {}
    declared_year: dict[str, int] = {}

    for obs in observations:
        if obs.end > latest_end.get(obs.accession, date.min):
            latest_end[obs.accession] = obs.end
        if obs.fiscal_year is not None:
            declared_year.setdefault(obs.accession, obs.fiscal_year)

    return {
        accession: FilingContext(
            fiscal_year=declared_year.get(accession, end.year),
            period_end=end,
        )
        for accession, end in latest_end.items()
    }


def _fiscal_year_for(obs: XbrlObservation, context: FilingContext | None) -> int:
    """The fiscal year a value belongs to, not the one its filing belongs to.

    Counting whole years back from the filing's own period end respects the
    company's labelling convention -- a January year-end that the filer calls
    FY2025 stays FY2025 -- without inheriting the filing's year wholesale.
    """
    if context is None:
        return obs.fiscal_year if obs.fiscal_year is not None else obs.end.year

    years_back = round((context.period_end - obs.end).days / 365.25)
    return context.fiscal_year - years_back


def infer_period(
    obs: XbrlObservation,
    context: FilingContext | None = None,
) -> Period | None:
    """Derive a `Period` from an observation's dates.

    Dates are authoritative and the filing's fiscal-period label is a hint: the
    label is absent on older filings and describes the filing rather than the
    value, whereas the dates come from the same XBRL context that produced the
    value itself.
    """
    fiscal_year = _fiscal_year_for(obs, context)

    if obs.is_instant:
        # Instants carry no span to classify, so the filing's label is the only
        # signal; FY is a safe default because a balance sheet date is a balance
        # sheet date regardless of which quarter's filing reported it.
        return Period(
            kind=PeriodKind.INSTANT,
            fiscal_year=fiscal_year,
            fiscal_period=_label_to_period(obs.fiscal_period) or FiscalPeriod.FY,
            end_date=obs.end,
        )

    assert obs.start is not None
    span_days = (obs.end - obs.start).days + 1
    fiscal_period = _classify_span(span_days)
    if fiscal_period is None:
        return None

    # A three-month span is some quarter; the filing's label says which. Without
    # a label, the quarter cannot be determined from dates alone and the fact is
    # left unplaced rather than guessed at.
    if fiscal_period is FiscalPeriod.Q1:
        labelled = _label_to_period(obs.fiscal_period)
        if labelled is not None and labelled.is_quarter:
            fiscal_period = labelled
        elif obs.fiscal_period == "FY":
            # A three-month span reported under an FY label is the fourth quarter.
            fiscal_period = FiscalPeriod.Q4
        elif labelled is None:
            return None

    try:
        return Period(
            kind=PeriodKind.DURATION,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            start_date=obs.start,
            end_date=obs.end,
        )
    except ValueError:
        # The span disagreed with the label beyond the tolerance Period allows.
        return None


def _classify_span(days: int) -> FiscalPeriod | None:
    for period, nominal in _NOMINAL_SPANS:
        if abs(days - nominal) <= _SPAN_SLACK_DAYS:
            return period
    return None


def _label_to_period(label: str | None) -> FiscalPeriod | None:
    if not label:
        return None
    try:
        return FiscalPeriod(label)
    except ValueError:
        return None


def _is_consolidated(obs: XbrlObservation) -> bool:
    """Whether an observation is a consolidated total rather than a breakout.

    `companyfacts` does not expose XBRL dimensions directly, but dimensional
    rows are distinguishable: they carry no `frame`, and the same tag/period
    appears many times over. The frame field is the SEC's own marker that a
    value is the comparable consolidated figure, so it is the cleanest available
    signal. Rows from the primary financial statements always carry one.
    """
    return obs.frame is not None


def to_facts(
    observations: list[XbrlObservation],
    registrant: Registrant,
    *,
    require_consolidated: bool = True,
) -> tuple[FactSet, AdaptationReport]:
    """Adapt raw observations into a reconciled `FactSet`."""
    entity_id = entity_id_for(registrant)

    # The filing each observation came from determines how its fiscal-year label
    # is derived, so contexts are built before any observation is placed.
    contexts = build_filing_contexts(observations)

    counters: dict[str, int] = defaultdict(int)
    # Keyed by the ledger slot a fact would occupy; several observations compete
    # for each, and the winner is chosen once all candidates are known.
    candidates: dict[tuple[Concept, tuple[str, str | None, str]], list[_Candidate]] = defaultdict(list)

    for obs in observations:
        if obs.form not in ACCEPTED_FORMS:
            counters["skipped_form"] += 1
            continue

        concept = concept_for(obs.tag)
        if concept is None:
            counters["skipped_unmapped_tag"] += 1
            continue

        unit = UNIT_MAP.get(obs.unit)
        if unit is None or unit is not meta(concept).unit:
            counters["skipped_unsupported_unit"] += 1
            continue

        if require_consolidated and not _is_consolidated(obs):
            counters["skipped_dimensional"] += 1
            continue

        period = infer_period(obs, contexts.get(obs.accession))
        if period is None or period.kind is not meta(concept).period_kind:
            counters["skipped_unresolvable_period"] += 1
            continue

        candidates[(concept, period.key)].append(_Candidate(obs=obs, period=period, concept=concept))

    facts: list[FinancialFact] = []
    for group in candidates.values():
        winner, superseded, tag_conflicts = _resolve(group)
        counters["superseded_by_restatement"] += superseded
        counters["conflicting_tags_resolved"] += tag_conflicts
        facts.append(_build_fact(winner, entity_id))
        counters["accepted"] += 1

    end_dates = [f.period.end_date for f in facts]
    annual = sum(
        1
        for f in facts
        if f.period.fiscal_period is FiscalPeriod.FY
        and f.period.kind is PeriodKind.DURATION
        and f.concept is Concept.REVENUE
    )

    report = AdaptationReport(
        earliest=min(end_dates) if end_dates else None,
        latest=max(end_dates) if end_dates else None,
        annual_reports=annual,
        accepted=counters["accepted"],
        skipped_unmapped_tag=counters["skipped_unmapped_tag"],
        skipped_dimensional=counters["skipped_dimensional"],
        skipped_unsupported_unit=counters["skipped_unsupported_unit"],
        skipped_form=counters["skipped_form"],
        skipped_unresolvable_period=counters["skipped_unresolvable_period"],
        superseded_by_restatement=counters["superseded_by_restatement"],
        conflicting_tags_resolved=counters["conflicting_tags_resolved"],
    )
    return FactSet(facts), report


@dataclass(frozen=True, slots=True)
class _Candidate:
    obs: XbrlObservation
    period: Period
    concept: Concept


def _resolve(group: list[_Candidate]) -> tuple[_Candidate, int, int]:
    """Pick the authoritative candidate for one ledger slot.

    Returns the winner, how many distinct values it superseded, and how many
    tag disagreements were resolved.

    Precedence, in order:
      1. Tag preference -- a filing emitting both a current and a legacy tag for
         the same concept means the current one.
      2. Most recently filed -- a restatement supersedes the original.
      3. Annual reports over quarterly -- the 10-K figure is the audited one.
    """
    if len(group) == 1:
        return group[0], 0, 0

    distinct_values = {c.obs.value for c in group}
    distinct_tags = {c.obs.tag for c in group}

    winner = min(
        group,
        key=lambda c: (
            tag_rank(c.concept, c.obs.tag),
            -c.obs.filed.toordinal(),
            0 if c.obs.form.startswith("10-K") else 1,
        ),
    )

    superseded = len(distinct_values) - 1 if len(distinct_values) > 1 else 0
    tag_conflicts = 1 if len(distinct_tags) > 1 and len(distinct_values) > 1 else 0
    return winner, superseded, tag_conflicts


def _build_fact(candidate: _Candidate, entity_id: UUID) -> FinancialFact:
    obs = candidate.obs
    provenance = XbrlProvenance(
        accession=obs.accession,
        cik=_cik_from_accession(obs.accession),
        tag=obs.tag,
        form=obs.form,
        filed=obs.filed,
        extractor="edgar:companyfacts",
    )
    return FinancialFact.from_reported(
        entity_id=entity_id,
        concept=candidate.concept,
        period=candidate.period,
        # EDGAR reports absolute values in the unit itself, never scaled to
        # thousands or millions, so no scale factor applies.
        raw_value=obs.value,
        scale=SCALE_UNITS,
        provenance=provenance,
    )


def _cik_from_accession(accession: str) -> int:
    """The filer CIK embedded in an accession number's first segment."""
    return int(accession.split("-")[0])


def facts_with_status(facts: FactSet, status: FactStatus) -> FactSet:
    """Bulk status assignment, used by the pipeline after validation."""
    return facts.replace([f.with_status(status) for f in facts])


def coverage(facts: FactSet) -> dict[str, Decimal]:
    """Fraction of the concept vocabulary populated, per period.

    Surfaced in the UI so a sparse period reads as "little was reported" rather
    than looking like a complete statement with unexplained gaps.
    """
    out: dict[str, Decimal] = {}
    total = Decimal(len(Concept))
    for period in facts.periods():
        present = len({f.concept for f in facts.for_period(period)})
        out[period.label] = (Decimal(present) / total).quantize(Decimal("0.001"))
    return out
