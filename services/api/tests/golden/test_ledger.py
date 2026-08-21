"""The canonical ledger, built from real company facts.

`test_as_filed.py` pins what the SEC's rendered exhibit says. This pins what
the ledger derives from `companyfacts`, which is a different document and a
different code path: observation parsing, tag mapping, period arithmetic,
reconciliation and validation all run for real.

That the two agree is the strongest single assurance in the suite. Apple's
FY2025 revenue is 416,161 on the face of the income statement and 416,161 in
the ledger, and nothing in the code connects those paths -- one reads rendered
HTML, the other reads XBRL JSON. Agreement across them is evidence; agreement
within either alone is not.

Facts are addressed by end date rather than by period label. The label is
derived from EDGAR's `fy`/`fp` fields, which describe the *filing* a value
appeared in rather than the period it measures, and is not a reliable
identifier -- see `Period.key`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from finagentic.api.service import EntityService
from finagentic.domain.concepts import Concept
from finagentic.validation.results import CheckStatus
from tests.golden.conftest import MILLIONS, CapturedFactsClient

# Apple's and Tesla's most recent fiscal year ends, as printed on the filings
# captured in tests/golden/fixtures.
APPLE_FY2025_END = date(2025, 9, 27)
APPLE_FY2025_START = date(2024, 9, 29)
TESLA_FY2025_END = date(2025, 12, 31)


@pytest.fixture(scope="module")
def apple():
    client = CapturedFactsClient("aapl_facts")
    import asyncio

    return asyncio.run(EntityService(client=client).ingest_now(client.registrant))


@pytest.fixture(scope="module")
def tesla():
    client = CapturedFactsClient("tsla_facts")
    import asyncio

    return asyncio.run(EntityService(client=client).ingest_now(client.registrant))


def at(record, concept: Concept, end: date):
    """The fact for `concept` measured at `end`, whatever its label says."""
    matches = [
        f for f in record.facts if f.concept is concept and f.period.end_date == end
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"{concept.value} at {end}: expected one fact, found {len(matches)}"
        )
    return matches[0]


# ---------------------------------------------------------------------------
# Apple
# ---------------------------------------------------------------------------


def test_apple_ingests_cleanly(apple):
    assert apple.state == "ready"
    assert apple.error is None
    assert len(apple.facts) > 3000


def test_apple_annual_figures_match_the_filing(apple):
    """The same numbers `test_as_filed` reads off the rendered income statement,
    arrived at through a completely separate path."""
    for concept, expected in [
        (Concept.REVENUE, "416161"),
        (Concept.COST_OF_REVENUE, "220960"),
        (Concept.GROSS_PROFIT, "195201"),
        (Concept.NET_INCOME, "112010"),
    ]:
        fact = at(apple, concept, APPLE_FY2025_END)
        assert fact.value == Decimal(expected) * MILLIONS, concept.value
        assert fact.period.start_date == APPLE_FY2025_START
        assert fact.period.kind.value == "duration"


def test_apple_balance_sheet_figures_match_the_filing(apple):
    for concept, expected in [
        (Concept.TOTAL_ASSETS, "359241"),
        (Concept.TOTAL_CURRENT_ASSETS, "147957"),
        (Concept.CASH_AND_EQUIVALENTS, "35934"),
        (Concept.INVENTORY, "5718"),
    ]:
        fact = at(apple, concept, APPLE_FY2025_END)
        assert fact.value == Decimal(expected) * MILLIONS, concept.value
        assert fact.period.kind.value == "instant"


def test_apple_gross_margin_reconciles_in_the_ledger(apple):
    revenue = at(apple, Concept.REVENUE, APPLE_FY2025_END).value
    cost = at(apple, Concept.COST_OF_REVENUE, APPLE_FY2025_END).value
    assert revenue - cost == at(apple, Concept.GROSS_PROFIT, APPLE_FY2025_END).value


def test_apples_headline_figures_are_verified_not_merely_present(apple):
    """VERIFIED means the fact took part in a satisfied accounting identity.
    A number nothing corroborates is not one to put in front of a reader."""
    for concept in (Concept.REVENUE, Concept.GROSS_PROFIT, Concept.TOTAL_ASSETS):
        assert at(apple, concept, APPLE_FY2025_END).is_usable, concept.value


def test_apple_has_no_temporary_equity(apple):
    """Apple issues nothing redeemable, so the mezzanine term is genuinely
    absent -- which is what makes it safe to treat as zero."""
    assert not [f for f in apple.facts if f.concept is Concept.TEMPORARY_EQUITY]


# ---------------------------------------------------------------------------
# Tesla
# ---------------------------------------------------------------------------


def test_tesla_ingests_cleanly(tesla):
    assert tesla.state == "ready"
    assert tesla.error is None


def test_tesla_balance_sheet_figures_match_the_filing(tesla):
    for concept, expected in [
        (Concept.TOTAL_ASSETS, "137806"),
        (Concept.TOTAL_LIABILITIES, "54941"),
        (Concept.TOTAL_STOCKHOLDERS_EQUITY, "82137"),
        (Concept.MINORITY_INTEREST, "670"),
    ]:
        fact = at(tesla, concept, TESLA_FY2025_END)
        assert fact.value == Decimal(expected) * MILLIONS, concept.value


def test_teslas_mezzanine_reaches_the_ledger(tesla):
    """58 million of redeemable non-controlling interests, which the equation
    is short by if this concept is not carried."""
    fact = at(tesla, Concept.TEMPORARY_EQUITY, TESLA_FY2025_END)
    assert fact.value == Decimal("58") * MILLIONS


def test_teslas_accounting_equation_holds_in_the_ledger(tesla):
    """The same arithmetic `test_as_filed` does on the rendered balance sheet,
    over facts derived from XBRL instead."""
    assets = at(tesla, Concept.TOTAL_ASSETS, TESLA_FY2025_END).value
    liabilities = at(tesla, Concept.TOTAL_LIABILITIES, TESLA_FY2025_END).value
    mezzanine = at(tesla, Concept.TEMPORARY_EQUITY, TESLA_FY2025_END).value
    equity = at(tesla, Concept.TOTAL_STOCKHOLDERS_EQUITY, TESLA_FY2025_END).value
    minority = at(tesla, Concept.MINORITY_INTEREST, TESLA_FY2025_END).value

    assert liabilities + mezzanine + equity + minority == assets


def test_teslas_balance_sheet_check_passes_at_year_end(tesla):
    """The identity that used to fail in every period from 2014 onward."""
    results = [
        r
        for r in tesla.validation.results
        if r.check_id == "bs.balances" and r.period_label
    ]
    assert results, "the balance sheet check did not run at all"
    assert any(r.status is CheckStatus.PASSED for r in results)


def test_no_filer_reports_a_critical_break_everywhere(apple, tesla):
    """A guard against a regression that breaks one identity for every period.

    Deliberately loose: real filings do contain genuine breaks, and a test that
    demanded zero would be edited into meaninglessness the first time one
    appeared. What it refuses is a check that fails universally, which is what
    a broken identity looks like.
    """
    for record in (apple, tesla):
        by_check: dict[str, list[bool]] = {}
        for result in record.validation.results:
            by_check.setdefault(result.check_id, []).append(
                result.status is CheckStatus.FAILED
            )
        always_failing = [
            check for check, outcomes in by_check.items() if all(outcomes) and len(outcomes) > 3
        ]
        assert always_failing == [], (
            f"{record.registrant.ticker}: these checks fail in every period, which "
            f"means the identity is wrong rather than the filing: {always_failing}"
        )
