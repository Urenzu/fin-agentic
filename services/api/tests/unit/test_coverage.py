"""How much of a company's history EDGAR holds.

All four figures come from the observations' own dates and accessions. The
canonical ledger used to produce the same summary as a by-product of mapping
every observation onto a concept vocabulary; these assert the answers do not
depend on that, which is the point of it being gone.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from finagentic.ingest.coverage import summarise
from finagentic.ingest.edgar import XbrlObservation


def obs(
    *,
    end: str,
    accession: str,
    form: str = "10-K",
    tag: str = "Assets",
) -> XbrlObservation:
    return XbrlObservation(
        tag=tag,
        unit="USD",
        value=Decimal("1"),
        end=date.fromisoformat(end),
        start=None,
        fiscal_year=None,
        fiscal_period=None,
        form=form,
        accession=accession,
        filed=date.fromisoformat(end),
        frame="CY2025",
    )


def test_an_empty_filer_reports_nothing_rather_than_zero_years():
    coverage = summarise([])
    assert coverage.earliest is None
    assert coverage.latest is None
    assert coverage.history_years == 0.0


def test_the_span_is_the_range_of_the_dates_reported():
    coverage = summarise(
        [
            obs(end="2006-09-30", accession="a"),
            obs(end="2026-06-27", accession="b"),
            obs(end="2015-01-01", accession="c"),
        ]
    )
    assert coverage.earliest == date(2006, 9, 30)
    assert coverage.latest == date(2026, 6, 27)
    assert round(coverage.history_years, 1) == 19.7


def test_annual_reports_are_counted_by_submission():
    """One accession is one filing, however many figures it carries.

    The ledger counted annual revenue figures instead, which a filer tagging
    revenue under an element nobody mapped would have made zero.
    """
    coverage = summarise(
        [
            obs(end="2025-09-27", accession="one"),
            obs(end="2025-09-27", accession="one", tag="Liabilities"),
            obs(end="2024-09-28", accession="two"),
        ]
    )
    assert coverage.annual_reports == 2


def test_quarterly_filings_are_not_annual_reports():
    coverage = summarise(
        [
            obs(end="2026-06-27", accession="q1", form="10-Q"),
            obs(end="2026-03-28", accession="q2", form="10-Q"),
        ]
    )
    assert coverage.annual_reports == 0
    assert coverage.observations == 2


def test_a_foreign_filer_reports_annually_too():
    """A 20-F is an annual report, and a filer with two decades of them is not
    a truncated history."""
    coverage = summarise(
        [obs(end=f"{year}-12-31", accession=str(year), form="20-F") for year in range(2006, 2026)]
    )
    assert coverage.annual_reports == 20
    assert not coverage.looks_truncated


def test_a_long_history_is_not_flagged():
    coverage = summarise(
        [obs(end=f"{year}-09-27", accession=str(year)) for year in range(2006, 2026)]
    )
    assert not coverage.looks_truncated


def test_a_short_history_is_flagged():
    """A ticker resolves to whichever CIK holds it now, which after a
    reorganisation is the new holding company with a year of filings."""
    coverage = summarise(
        [obs(end="2025-09-27", accession="a"), obs(end="2026-06-27", accession="b")]
    )
    assert coverage.looks_truncated


def test_a_filer_with_a_long_span_but_no_annual_report_is_still_flagged():
    """Twenty years of quarterlies is not twenty years of annual reports, and
    an analysis built on it would look complete and not be."""
    coverage = summarise(
        [
            obs(end=f"{year}-06-30", accession=str(year), form="10-Q")
            for year in range(2006, 2026)
        ]
    )
    assert coverage.annual_reports == 0
    assert coverage.looks_truncated


def test_the_summary_never_consults_a_concept_vocabulary():
    """An element nobody has ever mapped still counts toward the history.

    This is the whole reason the summary moved off the ledger: a company's
    filing history is a fact about its filings, not about our vocabulary.
    """
    coverage = summarise(
        [
            obs(end=f"{year}-09-27", accession=str(year), tag="SomeElementNobodyMapped")
            for year in range(2006, 2026)
        ]
    )
    assert coverage.annual_reports == 20
    assert not coverage.looks_truncated
