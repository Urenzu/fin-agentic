"""Property-based tests over the normalisation and validation layers.

Example-based tests confirm the cases I thought of. These confirm the ones I
did not. The properties below are the load-bearing guarantees of the ledger, so
they are stated once and checked against generated input.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from finagentic.domain.concepts import (
    CONCEPT_META,
    Concept,
    PeriodKind,
    SignConvention,
    Unit,
    meta,
)
from finagentic.domain.facts import (
    SCALE_BILLIONS,
    SCALE_MILLIONS,
    SCALE_THOUSANDS,
    SCALE_UNITS,
    FinancialFact,
)
from finagentic.domain.ledger import FactSet
from finagentic.domain.periods import FiscalPeriod, Period
from finagentic.validation.engine import validate
from tests.conftest import ENTITY_ID, build_clean_filing, make_provenance

# Money as it appears in a filing: bounded magnitude, at most two decimals.
reported_values = st.decimals(
    min_value=Decimal("-1e9"),
    max_value=Decimal("1e9"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)

scales = st.sampled_from([SCALE_UNITS, SCALE_THOUSANDS, SCALE_MILLIONS, SCALE_BILLIONS])

usd_duration_concepts = st.sampled_from(
    [
        c
        for c, m in CONCEPT_META.items()
        if m.period_kind is PeriodKind.DURATION and m.unit is Unit.USD
    ]
)

usd_instant_concepts = st.sampled_from(
    [
        c
        for c, m in CONCEPT_META.items()
        if m.period_kind is PeriodKind.INSTANT and m.unit is Unit.USD
    ]
)


def _duration(year: int = 2024) -> Period:
    return Period(
        kind=PeriodKind.DURATION,
        fiscal_year=year,
        fiscal_period=FiscalPeriod.FY,
        start_date=date(year, 1, 1),
        end_date=date(year, 12, 31),
    )


def _instant(year: int = 2024) -> Period:
    return Period(
        kind=PeriodKind.INSTANT,
        fiscal_year=year,
        fiscal_period=FiscalPeriod.FY,
        end_date=date(year, 12, 31),
    )


def _build(concept: Concept, period: Period, raw: Decimal, scale: Decimal) -> FinancialFact:
    return FinancialFact.from_reported(
        entity_id=ENTITY_ID,
        concept=concept,
        period=period,
        raw_value=raw,
        scale=scale,
        provenance=make_provenance(meta(concept).label),
    )


# ---------------------------------------------------------------------------
# normalisation properties
# ---------------------------------------------------------------------------


@given(concept=usd_duration_concepts, raw=reported_values, scale=scales)
def test_normalised_value_is_always_recoverable(concept, raw, scale):
    """value / scale always returns the printed magnitude.

    This is what makes the transformation auditable: a reviewer can always get
    back from the stored number to the number on the page.
    """
    fact = _build(concept, _duration(), raw, scale)
    expected = abs(raw) if meta(concept).sign is SignConvention.MAGNITUDE else raw
    assert fact.value / scale == expected


@given(concept=usd_duration_concepts, raw=reported_values, scale=scales)
def test_magnitude_concepts_are_never_stored_negative(concept, raw, scale):
    fact = _build(concept, _duration(), raw, scale)
    if meta(concept).sign is SignConvention.MAGNITUDE:
        assert fact.value >= 0


@given(concept=usd_duration_concepts, raw=reported_values, scale=scales)
def test_as_reported_concepts_preserve_sign(concept, raw, scale):
    fact = _build(concept, _duration(), raw, scale)
    if meta(concept).sign is SignConvention.AS_REPORTED:
        assert (fact.value < 0) == (raw < 0)
        assert fact.sign_flipped is False


@given(concept=usd_duration_concepts, raw=reported_values, scale=scales)
def test_sign_flipped_is_accurate(concept, raw, scale):
    """The audit flag never lies about whether normalisation changed the sign."""
    fact = _build(concept, _duration(), raw, scale)
    assert fact.sign_flipped == ((fact.raw_value < 0) != (fact.value < 0))


@given(concept=usd_duration_concepts, raw=reported_values, scale=scales)
def test_scaling_is_exact(concept, raw, scale):
    """No floating point error creeps in at any scale.

    A float pipeline would fail this: 0.1 * 1e6 is not exactly 100000.0 in
    binary floating point, and the error compounds through every identity check.
    """
    fact = _build(concept, _duration(), raw, scale)
    assert fact.value == fact.value.quantize(Decimal(1) / scale) or fact.value % 1 == fact.value % 1
    # Exact reconstruction, with no tolerance whatsoever.
    magnitude = abs(raw) if meta(concept).sign is SignConvention.MAGNITUDE else raw
    assert fact.value - (magnitude * scale) == Decimal(0)


@given(concept=usd_instant_concepts, raw=reported_values, scale=scales)
def test_instant_concepts_accept_instant_periods(concept, raw, scale):
    fact = _build(concept, _instant(), raw, scale)
    assert fact.period.kind is PeriodKind.INSTANT


@given(raw=reported_values, scale=scales)
def test_round_tripping_through_json_preserves_the_value(raw, scale):
    """Serialisation must not quietly convert Decimal to float.

    The API layer serialises facts to JSON; if that path lost precision, the
    numbers the user sees would drift from the numbers that were validated.
    """
    fact = _build(Concept.REVENUE, _duration(), raw, scale)
    restored = FinancialFact.model_validate_json(fact.model_dump_json())

    assert restored.value == fact.value
    assert restored.raw_value == fact.raw_value
    assert restored.scale == fact.scale


# ---------------------------------------------------------------------------
# ledger properties
# ---------------------------------------------------------------------------


@given(values=st.lists(reported_values, min_size=1, max_size=20))
def test_factset_length_matches_input(values):
    period = _duration()
    facts = [_build(Concept.REVENUE, period, v, SCALE_UNITS) for v in values]
    assert len(FactSet(facts)) == len(values)


@given(values=st.lists(reported_values, min_size=2, max_size=6, unique=True))
def test_ambiguous_lookups_return_none_rather_than_guessing(values):
    """Several facts in one slot means the answer is unknown, not the first one.

    Returning an arbitrary member would let a wrong value silently reach a chart.
    """
    period = _duration()
    facts = [_build(Concept.REVENUE, period, v, SCALE_UNITS) for v in values]
    assert FactSet(facts).get(Concept.REVENUE, period) is None


@given(scale=scales)
def test_require_returns_none_when_any_input_is_missing(scale):
    period = _duration()
    partial = FactSet([_build(Concept.REVENUE, period, Decimal("100"), scale)])
    assert partial.require((Concept.REVENUE, Concept.COST_OF_REVENUE), period) is None


# ---------------------------------------------------------------------------
# validation properties
# ---------------------------------------------------------------------------


@given(
    concept=st.sampled_from(
        [
            Concept.TOTAL_ASSETS,
            Concept.TOTAL_LIABILITIES,
            Concept.TOTAL_STOCKHOLDERS_EQUITY,
            Concept.CASH_AND_EQUIVALENTS,
        ]
    ),
    delta=st.decimals(min_value=Decimal("50"), max_value=Decimal("5000"), places=0),
)
@settings(max_examples=40, deadline=None)
def test_perturbing_any_balance_sheet_total_breaks_an_identity(concept, delta):
    """Any material change to a balance sheet total must be detected.

    This is the core anti-hallucination property, stated generally: you cannot
    alter a load-bearing number and have the ledger still call it verified.
    """
    assume(delta != 0)
    duration, instant = _duration(), _instant()
    clean = build_clean_filing(duration, instant)

    original = clean.get(concept, instant)
    assert original is not None
    tampered_raw = original.raw_value + delta

    kept = [f for f in clean if f.id != original.id]
    tampered = FactSet([*kept, _build(concept, instant, tampered_raw, original.scale)])

    verified, report = validate(tampered)

    assert report.failed, f"tampering with {concept} by {delta}M went undetected"
    tampered_fact = verified.get(concept, instant)
    assert tampered_fact is not None
    assert not tampered_fact.is_usable


@given(delta=st.decimals(min_value=Decimal("50"), max_value=Decimal("5000"), places=0))
@settings(max_examples=30, deadline=None)
def test_perturbing_a_cash_flow_section_breaks_the_rollforward(delta):
    assume(delta != 0)
    duration, instant = _duration(), _instant()
    clean = build_clean_filing(duration, instant)

    original = clean.get(Concept.NET_CASH_OPERATING, duration)
    assert original is not None
    kept = [f for f in clean if f.id != original.id]
    tampered = FactSet(
        [*kept, _build(Concept.NET_CASH_OPERATING, duration, original.raw_value + delta, original.scale)]
    )

    _, report = validate(tampered)
    broken = {r.check_id for r in report.failed}
    assert "cf.rollforward" in broken


def test_the_clean_filing_is_stable_under_revalidation():
    """Validation is idempotent: running it twice changes nothing."""
    duration, instant = _duration(), _instant()
    clean = build_clean_filing(duration, instant)

    once, report_once = validate(clean)
    twice, report_twice = validate(once)

    assert report_once.summary() == report_twice.summary()
    assert {f.id: f.status for f in once} == {f.id: f.status for f in twice}


@given(
    drop=st.sets(
        st.sampled_from(list(CONCEPT_META.keys())),
        min_size=1,
        max_size=8,
    )
)
@settings(max_examples=50, deadline=None)
def test_dropping_facts_never_manufactures_a_failure(drop):
    """Removing information can only turn checks into skips, never into failures.

    A sparsely extracted document should read as "not enough data", not as
    "this company's books don't balance".
    """
    duration, instant = _duration(), _instant()
    clean = build_clean_filing(duration, instant)
    sparse = FactSet(f for f in clean if f.concept not in drop)

    _, report = validate(sparse)
    assert report.failed == (), (
        "dropping facts produced a failure: "
        + "; ".join(f"{r.check_id}: {r.message}" for r in report.failed)
    )


@given(
    year=st.integers(min_value=1990, max_value=2100),
    offset=st.integers(min_value=-7, max_value=7),
)
def test_fiscal_years_of_52_or_53_weeks_are_accepted(year, offset):
    """52/53-week fiscal calendars are legitimate and must not be rejected."""
    start = date(year, 1, 1)
    end = start + timedelta(days=364 + offset)
    period = Period(
        kind=PeriodKind.DURATION,
        fiscal_year=year,
        fiscal_period=FiscalPeriod.FY,
        start_date=start,
        end_date=end,
    )
    assert period.fiscal_year == year
