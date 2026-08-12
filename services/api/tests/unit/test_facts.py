"""Normalisation invariants on FinancialFact.

These tests pin the transformation from "what the document printed" to "what
the ledger stores". Getting this wrong is the highest-consequence bug class in
the system: a sign or scale error produces a number that is wrong by orders of
magnitude yet still looks entirely plausible on a chart.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from finagentic.domain.concepts import Concept, PeriodKind, SignConvention, Unit, meta
from finagentic.domain.facts import (
    SCALE_MILLIONS,
    SCALE_THOUSANDS,
    SCALE_UNITS,
    FactStatus,
    FinancialFact,
    PdfProvenance,
)
from finagentic.domain.periods import FiscalPeriod, Period
from tests.conftest import DOC_ID, ENTITY_ID, make_fact, make_provenance

# ---------------------------------------------------------------------------
# scaling
# ---------------------------------------------------------------------------


def test_millions_scale_is_applied(fy2024):
    fact = make_fact(Concept.REVENUE, fy2024, Decimal("10000"))
    assert fact.value == Decimal("10000000000")
    assert fact.raw_value == Decimal("10000")


def test_thousands_scale_is_applied(fy2024):
    fact = make_fact(Concept.REVENUE, fy2024, Decimal("10000"), scale=SCALE_THOUSANDS)
    assert fact.value == Decimal("10000000")


def test_scale_is_exact_for_fractional_values(fy2024):
    """Decimal arithmetic, not float: 1.1 million is exactly 1,100,000."""
    fact = make_fact(Concept.REVENUE, fy2024, Decimal("1.1"))
    assert fact.value == Decimal("1100000")


def test_an_unrecognised_scale_is_rejected(fy2024):
    with pytest.raises(ValidationError, match="scale"):
        FinancialFact(
            entity_id=ENTITY_ID,
            concept=Concept.REVENUE,
            period=fy2024,
            value=Decimal("500"),
            unit=Unit.USD,
            raw_value=Decimal("5"),
            scale=Decimal("100"),
            provenance=make_provenance("Revenue"),
        )


def test_per_share_amounts_reject_a_reporting_scale(fy2024):
    """EPS is never printed 'in millions'; scaling it is always an error."""
    with pytest.raises(ValidationError, match="per-share"):
        make_fact(Concept.EPS_DILUTED, fy2024, Decimal("1.60"), scale=SCALE_MILLIONS)


def test_per_share_amounts_accept_the_unit_scale(fy2024):
    fact = make_fact(Concept.EPS_DILUTED, fy2024, Decimal("1.60"), scale=SCALE_UNITS)
    assert fact.value == Decimal("1.60")


# ---------------------------------------------------------------------------
# sign normalisation
# ---------------------------------------------------------------------------


def test_a_cost_printed_in_parentheses_is_stored_positive(fy2024):
    """Filings print capex as '(1,000)'. The ledger stores the magnitude."""
    fact = make_fact(Concept.CAPITAL_EXPENDITURES, fy2024, Decimal("-1000"))

    assert meta(Concept.CAPITAL_EXPENDITURES).sign is SignConvention.MAGNITUDE
    assert fact.value == Decimal("1000000000")
    assert fact.raw_value == Decimal("-1000")
    assert fact.sign_flipped is True


def test_a_cost_printed_positive_is_left_alone(fy2024):
    fact = make_fact(Concept.COST_OF_REVENUE, fy2024, Decimal("4000"))
    assert fact.value == Decimal("4000000000")
    assert fact.sign_flipped is False


def test_a_loss_keeps_its_sign(fy2024):
    """Net income is AS_REPORTED: a loss must stay negative."""
    fact = make_fact(Concept.NET_INCOME, fy2024, Decimal("-500"))

    assert meta(Concept.NET_INCOME).sign is SignConvention.AS_REPORTED
    assert fact.value == Decimal("-500000000")
    assert fact.sign_flipped is False


def test_negative_operating_cash_flow_keeps_its_sign(fy2024):
    fact = make_fact(Concept.NET_CASH_OPERATING, fy2024, Decimal("-250"))
    assert fact.value == Decimal("-250000000")


def test_an_accumulated_deficit_keeps_its_sign(fy2024_instant):
    fact = make_fact(Concept.RETAINED_EARNINGS, fy2024_instant, Decimal("-1200"))
    assert fact.value == Decimal("-1200000000")


def test_a_magnitude_concept_cannot_be_constructed_negative(fy2024):
    """Bypassing from_reported must not be able to smuggle in a bad sign."""
    with pytest.raises(ValidationError, match="MAGNITUDE"):
        FinancialFact(
            entity_id=ENTITY_ID,
            concept=Concept.CAPITAL_EXPENDITURES,
            period=fy2024,
            value=Decimal("-1000"),
            unit=Unit.USD,
            raw_value=Decimal("-1000"),
            scale=SCALE_UNITS,
            sign_flipped=False,
            provenance=make_provenance("Capital expenditures"),
        )


def test_value_must_be_consistent_with_raw_value_and_scale(fy2024):
    """A hand-constructed fact whose value does not follow from its inputs is
    rejected -- there is no way to store a number that is not derivable."""
    with pytest.raises(ValidationError, match="does not equal"):
        FinancialFact(
            entity_id=ENTITY_ID,
            concept=Concept.REVENUE,
            period=fy2024,
            value=Decimal("999"),
            unit=Unit.USD,
            raw_value=Decimal("10000"),
            scale=SCALE_MILLIONS,
            provenance=make_provenance("Revenue"),
        )


# ---------------------------------------------------------------------------
# period / concept agreement
# ---------------------------------------------------------------------------


def test_a_duration_concept_rejects_an_instant_period(fy2024_instant):
    """Revenue measured 'at' a date rather than 'over' one is an extraction bug."""
    with pytest.raises(ValidationError, match="duration"):
        make_fact(Concept.REVENUE, fy2024_instant, Decimal("10000"))


def test_an_instant_concept_rejects_a_duration_period(fy2024):
    with pytest.raises(ValidationError, match="instant"):
        make_fact(Concept.TOTAL_ASSETS, fy2024, Decimal("14000"))


# ---------------------------------------------------------------------------
# provenance
# ---------------------------------------------------------------------------


def test_provenance_is_required(fy2024):
    with pytest.raises(ValidationError):
        FinancialFact(
            entity_id=ENTITY_ID,
            concept=Concept.REVENUE,
            period=fy2024,
            value=Decimal("10000"),
            unit=Unit.USD,
            raw_value=Decimal("10000"),
            scale=SCALE_UNITS,
        )


def test_provenance_rejects_an_empty_quotation():
    """An extractor that cannot quote its source cannot record a fact."""
    with pytest.raises(ValidationError):
        PdfProvenance(
            document_id=DOC_ID,
            page=1,
            raw_text="",
            row_label="Revenue",
            extractor="test",
        )


def test_provenance_rejects_an_empty_row_label():
    with pytest.raises(ValidationError):
        PdfProvenance(
            document_id=DOC_ID,
            page=1,
            raw_text="10,000",
            row_label="",
            extractor="test",
        )


def test_page_numbers_are_one_indexed():
    with pytest.raises(ValidationError):
        PdfProvenance(
            document_id=DOC_ID,
            page=0,
            raw_text="10,000",
            row_label="Revenue",
            extractor="test",
        )


# ---------------------------------------------------------------------------
# status and immutability
# ---------------------------------------------------------------------------


def test_facts_start_unverified(fy2024):
    assert make_fact(Concept.REVENUE, fy2024, Decimal("1")).status is FactStatus.UNVERIFIED


def test_only_verified_facts_are_usable(fy2024):
    fact = make_fact(Concept.REVENUE, fy2024, Decimal("1"))
    assert not fact.is_usable
    assert fact.with_status(FactStatus.VERIFIED).is_usable
    assert not fact.with_status(FactStatus.INCONSISTENT).is_usable
    assert not fact.with_status(FactStatus.CONFLICTED).is_usable


def test_with_status_does_not_mutate_the_original(fy2024):
    fact = make_fact(Concept.REVENUE, fy2024, Decimal("1"))
    promoted = fact.with_status(FactStatus.VERIFIED)

    assert fact.status is FactStatus.UNVERIFIED
    assert promoted.id == fact.id
    assert promoted.provenance == fact.provenance


def test_facts_are_frozen(fy2024):
    fact = make_fact(Concept.REVENUE, fy2024, Decimal("1"))
    with pytest.raises(ValidationError):
        fact.value = Decimal("2")


# ---------------------------------------------------------------------------
# periods
# ---------------------------------------------------------------------------


def test_a_duration_requires_a_start_date():
    with pytest.raises(ValidationError, match="requires a start_date"):
        Period(
            kind=PeriodKind.DURATION,
            fiscal_year=2024,
            fiscal_period=FiscalPeriod.FY,
            end_date=date(2024, 12, 31),
        )


def test_an_instant_rejects_a_start_date():
    with pytest.raises(ValidationError, match="must not have a start_date"):
        Period(
            kind=PeriodKind.INSTANT,
            fiscal_year=2024,
            fiscal_period=FiscalPeriod.FY,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )


def test_a_span_inconsistent_with_its_label_is_rejected():
    """A three-month span labelled FY is a misread column header."""
    with pytest.raises(ValidationError, match="inconsistent"):
        Period(
            kind=PeriodKind.DURATION,
            fiscal_year=2024,
            fiscal_period=FiscalPeriod.FY,
            start_date=date(2024, 10, 1),
            end_date=date(2024, 12, 31),
        )


def test_a_53_week_fiscal_year_is_accepted():
    """Retailers and Apple report 53-week years; these are legitimate."""
    period = Period(
        kind=PeriodKind.DURATION,
        fiscal_year=2024,
        fiscal_period=FiscalPeriod.FY,
        start_date=date(2023, 10, 1),
        end_date=date(2024, 9, 28),
    )
    assert period.label == "FY2024"


def test_a_quarter_is_not_comparable_to_a_year(fy2024):
    q1 = Period(
        kind=PeriodKind.DURATION,
        fiscal_year=2024,
        fiscal_period=FiscalPeriod.Q1,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 3, 31),
    )
    assert not fy2024.is_comparable_to(q1)
    assert q1.is_comparable_to(q1.prior_year())


def test_prior_year_steps_back_one_fiscal_year(fy2024):
    assert fy2024.prior_year().fiscal_year == 2023
    assert fy2024.prior_year().fiscal_period is FiscalPeriod.FY
