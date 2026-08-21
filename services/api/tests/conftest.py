"""Shared fixtures.

`clean_filing` is a synthetic but *fully internally consistent* set of three
statements. Every accounting identity the validation layer knows about holds
exactly. Tests then perturb single values to assert that a specific check
catches a specific error -- which is a far sharper test than checking a real
filing, where a failure could be blamed on extraction rather than on the check.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from hypothesis import HealthCheck, settings

from finagentic.domain.concepts import Concept, PeriodKind, meta
from finagentic.domain.facts import SCALE_MILLIONS, FinancialFact, PdfProvenance
from finagentic.domain.ledger import FactSet
from finagentic.domain.periods import FiscalPeriod, Period

DOC_ID = UUID("11111111-1111-1111-1111-111111111111")
ENTITY_ID = UUID("22222222-2222-2222-2222-222222222222")

# Hypothesis profiles. `dev` is the fast default for the inner loop; `deep` is
# what CI and pre-release runs use, since the interesting counterexamples in the
# validation layer only surface after a few hundred examples.
settings.register_profile("dev", max_examples=50, deadline=None)
settings.register_profile(
    "deep",
    max_examples=1500,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "dev"))


@pytest.fixture
def entity_id() -> UUID:
    return ENTITY_ID


@pytest.fixture
def doc_id() -> UUID:
    return DOC_ID


def make_provenance(row_label: str, page: int = 1, raw_text: str | None = None) -> PdfProvenance:
    return PdfProvenance(
        document_id=DOC_ID,
        page=page,
        raw_text=raw_text or row_label,
        row_label=row_label,
        extractor="test:fixture",
    )


def make_fact(
    concept: Concept,
    period: Period,
    raw_value: Decimal | int | str,
    *,
    scale: Decimal = SCALE_MILLIONS,
    entity_id: UUID = ENTITY_ID,
) -> FinancialFact:
    """Build a fact the way an adapter would, with normalisation applied."""
    return FinancialFact.from_reported(
        entity_id=entity_id,
        concept=concept,
        period=period,
        raw_value=Decimal(str(raw_value)),
        scale=scale,
        provenance=make_provenance(meta(concept).label),
    )


@pytest.fixture
def fy2024() -> Period:
    """The FY2024 duration period: income statement and cash flow."""
    return Period(
        kind=PeriodKind.DURATION,
        fiscal_year=2024,
        fiscal_period=FiscalPeriod.FY,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )


@pytest.fixture
def fy2024_instant() -> Period:
    """The 2024-12-31 instant: balance sheet."""
    return Period(
        kind=PeriodKind.INSTANT,
        fiscal_year=2024,
        fiscal_period=FiscalPeriod.FY,
        end_date=date(2024, 12, 31),
    )


#: Income statement, in millions. Internally consistent:
#:   gross profit  = 10,000 - 4,000            = 6,000
#:   total opex    = 1,500 + 1,800 + 700       = 4,000
#:   operating inc = 6,000 - 4,000             = 2,000
#:   pretax        = 2,000 - 100 + 150         = 2,050
#:   net income    = 2,050 - 450               = 1,600
#:   diluted EPS   = 1,600 / 1,000             = 1.60
INCOME_STATEMENT: dict[Concept, str] = {
    Concept.REVENUE: "10000",
    Concept.COST_OF_REVENUE: "4000",
    Concept.GROSS_PROFIT: "6000",
    Concept.RESEARCH_AND_DEVELOPMENT: "1500",
    Concept.SALES_AND_MARKETING: "1800",
    Concept.GENERAL_AND_ADMIN: "700",
    Concept.TOTAL_OPERATING_EXPENSES: "4000",
    Concept.OPERATING_INCOME: "2000",
    Concept.INTEREST_EXPENSE: "100",
    Concept.INTEREST_INCOME: "150",
    Concept.PRETAX_INCOME: "2050",
    Concept.INCOME_TAX_EXPENSE: "450",
    Concept.NET_INCOME: "1600",
    # Reported explicitly so the net income check takes its strict path, as it
    # does for any filer with consolidated subsidiaries. Zero here means the
    # parent owns them outright.
    Concept.NET_INCOME_TO_NCI: "0",
    Concept.NET_INCOME_TO_COMMON: "1600",
}

#: Balance sheet, in millions. Assets 14,000 = Liabilities 8,000 + Equity 6,000.
BALANCE_SHEET: dict[Concept, str] = {
    Concept.CASH_AND_EQUIVALENTS: "2500",
    Concept.SHORT_TERM_INVESTMENTS: "1200",
    Concept.ACCOUNTS_RECEIVABLE: "1400",
    Concept.INVENTORY: "800",
    Concept.PREPAID_EXPENSES: "300",
    Concept.OTHER_CURRENT_ASSETS: "200",
    Concept.TOTAL_CURRENT_ASSETS: "6400",
    Concept.PROPERTY_PLANT_EQUIPMENT_NET: "3000",
    Concept.LONG_TERM_INVESTMENTS: "1500",
    Concept.GOODWILL: "2000",
    Concept.INTANGIBLE_ASSETS: "600",
    Concept.OTHER_NONCURRENT_ASSETS: "500",
    Concept.TOTAL_NONCURRENT_ASSETS: "7600",
    Concept.TOTAL_ASSETS: "14000",
    Concept.ACCOUNTS_PAYABLE: "900",
    Concept.ACCRUED_LIABILITIES: "1100",
    Concept.DEFERRED_REVENUE_CURRENT: "1300",
    Concept.SHORT_TERM_DEBT: "200",
    Concept.CURRENT_PORTION_LONG_TERM_DEBT: "300",
    Concept.OTHER_CURRENT_LIABILITIES: "200",
    Concept.TOTAL_CURRENT_LIABILITIES: "4000",
    Concept.LONG_TERM_DEBT: "3000",
    Concept.DEFERRED_TAX_LIABILITIES: "400",
    Concept.OTHER_NONCURRENT_LIABILITIES: "600",
    Concept.TOTAL_NONCURRENT_LIABILITIES: "4000",
    Concept.TOTAL_LIABILITIES: "8000",
    Concept.COMMON_STOCK_AND_APIC: "4000",
    Concept.RETAINED_EARNINGS: "2200",
    Concept.ACCUMULATED_OCI: "-200",
    Concept.TOTAL_STOCKHOLDERS_EQUITY: "6000",
    # Reported explicitly, as filings with any consolidated subsidiary do. Its
    # presence lets the balance sheet check take its strict path; see
    # test_a_missing_nci_line_is_not_reported_as_an_imbalance for the other case.
    Concept.MINORITY_INTEREST: "0",
    Concept.TOTAL_LIABILITIES_AND_EQUITY: "14000",
}

#: Cash flow, in millions. Roll-forward: 2,150 + 3,000 - 1,600 - 1,000 - 50 = 2,500.
#: Note the printed signs: the filing shows capex as "(1,000)" and the extractor
#: stores it as a positive magnitude, so the fixture supplies the printed value.
CASH_FLOW_DURATION: dict[Concept, str] = {
    Concept.DEPRECIATION_AND_AMORTIZATION: "800",
    Concept.STOCK_BASED_COMPENSATION: "600",
    Concept.DEFERRED_INCOME_TAXES: "-100",
    Concept.CHANGE_IN_RECEIVABLES: "-200",
    Concept.CHANGE_IN_INVENTORY: "-100",
    Concept.CHANGE_IN_PAYABLES: "150",
    Concept.CHANGE_IN_DEFERRED_REVENUE: "250",
    Concept.NET_CASH_OPERATING: "3000",
    Concept.CAPITAL_EXPENDITURES: "(1000)",
    Concept.ACQUISITIONS_NET_OF_CASH: "(300)",
    Concept.PURCHASES_OF_INVESTMENTS: "(1500)",
    Concept.SALES_MATURITIES_OF_INVESTMENTS: "1200",
    Concept.NET_CASH_INVESTING: "-1600",
    Concept.DEBT_ISSUED: "500",
    Concept.DEBT_REPAID: "(400)",
    Concept.SHARE_REPURCHASES: "(800)",
    Concept.DIVIDENDS_PAID: "(300)",
    Concept.NET_CASH_FINANCING: "-1000",
    Concept.FX_EFFECT_ON_CASH: "-50",
    Concept.NET_CHANGE_IN_CASH: "350",
}

#: Cash flow concepts that are instants, keyed to the statement's period end.
#: Comprehensive income, in millions. Internally consistent:
#:   other comprehensive income = 40 - 15 + 25   = 50
#:   comprehensive income       = 1,600 + 50     = 1,650
COMPREHENSIVE_INCOME: dict[Concept, str] = {
    Concept.OCI_FOREIGN_CURRENCY: "40",
    Concept.OCI_DERIVATIVES: "(15)",
    Concept.OCI_SECURITIES: "25",
    Concept.OTHER_COMPREHENSIVE_INCOME: "50",
    Concept.COMPREHENSIVE_INCOME: "1650",
}

#: What moved equity over the year, in millions. Stored as magnitudes: the
#: direction belongs to the identity, not to the value.
#:   5,400 + 1,600 + 50 + 200 + 150 - 900 - 400 - 100 = 6,000
EQUITY_MOVEMENTS: dict[Concept, str] = {
    Concept.STOCK_ISSUED: "200",
    Concept.SHARE_BASED_COMP_EQUITY: "150",
    Concept.STOCK_REPURCHASED: "900",
    Concept.DIVIDENDS_DECLARED: "400",
    Concept.TAX_WITHHOLDING_SHARE_BASED: "100",
}

#: Equity as it stood at the start of the year, for `two_year_filing`.
#: The roll-forward is the only identity spanning two balance sheets.
OPENING_BALANCE: dict[Concept, str] = {
    Concept.TOTAL_STOCKHOLDERS_EQUITY: "5400",
}

CASH_FLOW_INSTANT: dict[Concept, str] = {
    Concept.CASH_BEGINNING_OF_PERIOD: "2150",
    Concept.CASH_END_OF_PERIOD: "2500",
}

#: Share counts, in units rather than millions.
SHARE_COUNTS: dict[Concept, str] = {
    Concept.SHARES_DILUTED: "1000",
}

EPS: dict[Concept, str] = {
    Concept.EPS_DILUTED: "1.60",
}


def _parse(raw: str) -> Decimal:
    """Parse a printed figure, honouring accounting parentheses for negatives."""
    raw = raw.strip().replace(",", "")
    if raw.startswith("(") and raw.endswith(")"):
        return -Decimal(raw[1:-1])
    return Decimal(raw)


def build_clean_filing(duration: Period, instant: Period) -> FactSet:
    """Assemble the fully consistent fixture ledger."""
    facts: list[FinancialFact] = []

    for concept, raw in {
        **INCOME_STATEMENT,
        **CASH_FLOW_DURATION,
        **COMPREHENSIVE_INCOME,
        **EQUITY_MOVEMENTS,
    }.items():
        facts.append(make_fact(concept, duration, _parse(raw)))


    for concept, raw in {**BALANCE_SHEET, **CASH_FLOW_INSTANT}.items():
        facts.append(make_fact(concept, instant, _parse(raw)))

    for concept, raw in SHARE_COUNTS.items():
        facts.append(make_fact(concept, duration, _parse(raw)))

    # EPS is printed per share, not in millions.
    for concept, raw in EPS.items():
        facts.append(make_fact(concept, duration, _parse(raw), scale=Decimal(1)))

    return FactSet(facts)


@pytest.fixture
def fy2023_instant() -> Period:
    """The 2023-12-31 instant: the balance sheet the year opened from."""
    return Period(
        kind=PeriodKind.INSTANT,
        fiscal_year=2023,
        fiscal_period=FiscalPeriod.FY,
        end_date=date(2023, 12, 31),
    )


@pytest.fixture
def clean_filing(fy2024: Period, fy2024_instant: Period) -> FactSet:
    return build_clean_filing(fy2024, fy2024_instant)


@pytest.fixture
def two_year_filing(clean_filing: FactSet, fy2023_instant: Period) -> FactSet:
    """The clean filing plus the equity it opened the year with.

    Kept apart from `clean_filing` deliberately. A second instant makes every
    balance sheet check skip on the opening date as well as pass at year end,
    so folding it in would turn "this check passes" into "this check passes and
    also skips" for every test in the suite -- weakening dozens of assertions
    to serve one. Only the identity that genuinely spans two periods needs it.
    """
    return FactSet(
        [
            *clean_filing,
            *(
                make_fact(concept, fy2023_instant, _parse(raw))
                for concept, raw in OPENING_BALANCE.items()
            ),
        ]
    )


@pytest.fixture
def new_uuid():
    return uuid4
