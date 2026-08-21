"""The twelve comparable figures, and the ways a filing can mislead them."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from finagentic.compare.extract import metrics_for
from finagentic.compare.metrics import ALIASES, BY_ELEMENT, INSTANT, LABELS, Metric, rank
from finagentic.ingest.rfiles import AsFiledColumn, AsFiledRow, AsFiledStatement

ACCESSION = "0000320193-25-000079"


def column(key: str, label: str, duration: str | None, when: date | None) -> AsFiledColumn:
    return AsFiledColumn(key=key, label=label, duration=duration, date=when)


def row(label: str, element: str, values: dict[str, str]) -> AsFiledRow:
    return AsFiledRow(
        label=label,
        element=f"us-gaap_{element}",
        is_abstract=False,
        is_total=False,
        indent=0,
        values={k: Decimal(v) for k, v in values.items()},
    )


def statement(title: str, columns: list[AsFiledColumn], rows: list[AsFiledRow]):
    return AsFiledStatement(title=title, columns=tuple(columns), rows=tuple(rows))


PERIOD = [
    column("0", "Sep. 27, 2025", "12 Months Ended", date(2025, 9, 27)),
    column("1", "Sep. 28, 2024", "12 Months Ended", date(2024, 9, 28)),
]
INSTANTS = [
    column("0", "Sep. 27, 2025", None, date(2025, 9, 27)),
    column("1", "Sep. 28, 2024", None, date(2024, 9, 28)),
]


def income(**rows_by_element: dict[str, str]):
    return statement(
        "CONSOLIDATED STATEMENTS OF OPERATIONS",
        PERIOD,
        [row(k, k, v) for k, v in rows_by_element.items()],
    )


# ---------------------------------------------------------------------------
# the map itself
# ---------------------------------------------------------------------------


def test_every_metric_has_a_label_and_at_least_one_element():
    for metric in Metric:
        assert metric in LABELS, metric
        assert ALIASES.get(metric), metric


def test_no_element_serves_two_metrics():
    """An element meaning two things would make one of them wrong, silently."""
    seen: dict[str, Metric] = {}
    for metric, elements in ALIASES.items():
        for element in elements:
            assert element not in seen, f"{element} claimed by {seen.get(element)} and {metric}"
            seen[element] = metric
    assert set(BY_ELEMENT) == set(seen)


def test_the_map_stays_small():
    """The whole argument for this vocabulary is that it is small enough for
    its failures to be obvious. A hundred entries is the other design."""
    assert len(list(Metric)) <= 15
    assert sum(len(v) for v in ALIASES.values()) <= 30


def test_balance_sheet_metrics_are_instants_and_flows_are_not():
    assert Metric.TOTAL_ASSETS in INSTANT
    assert Metric.REVENUE not in INSTANT
    # A weighted average is taken over a period, however much it reads as a
    # balance.
    assert Metric.SHARES_DILUTED not in INSTANT


def test_precedence_prefers_the_headline_element():
    assert rank(Metric.REVENUE, "RevenueFromContractWithCustomerExcludingAssessedTax") < rank(
        Metric.REVENUE, "Revenues"
    )
    # Equity including non-controlling interests wins: comparing one company's
    # whole equity against another's parent-only share is the error to avoid.
    assert rank(
        Metric.TOTAL_EQUITY,
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ) < rank(Metric.TOTAL_EQUITY, "StockholdersEquity")


# ---------------------------------------------------------------------------
# extraction
# ---------------------------------------------------------------------------


def test_a_metric_is_read_from_every_period_the_filing_prints():
    found = metrics_for(
        [income(RevenueFromContractWithCustomerExcludingAssessedTax={"0": "416161", "1": "391035"})],
        ACCESSION,
        "10-K",
    )
    values = [p.value for p in found.periods[Metric.REVENUE]]
    assert values == [Decimal("416161"), Decimal("391035")]
    assert found.newest(Metric.REVENUE).value == Decimal("416161")


def test_the_better_alias_wins_when_a_filer_reports_both():
    """A filer using both reports the newer standard's figure as the headline
    and `Revenues` as a broader total."""
    found = metrics_for(
        [
            income(
                Revenues={"0": "999999"},
                RevenueFromContractWithCustomerExcludingAssessedTax={"0": "416161"},
            )
        ],
        ACCESSION,
        "10-K",
    )
    assert found.newest(Metric.REVENUE).value == Decimal("416161")


def test_a_segment_breakout_does_not_stand_in_for_the_total():
    """Apple prints revenue for the consolidated total and again under each of
    Products and Services. The total comes first."""
    consolidated = row(
        "Net sales", "RevenueFromContractWithCustomerExcludingAssessedTax", {"0": "416161"}
    )
    products = row(
        "Net sales", "RevenueFromContractWithCustomerExcludingAssessedTax", {"0": "298085"}
    )
    found = metrics_for(
        [statement("OPERATIONS", PERIOD, [consolidated, products])], ACCESSION, "10-K"
    )
    assert found.newest(Metric.REVENUE).value == Decimal("416161")


def test_equity_component_columns_are_not_periods():
    """The bug that made Tesla's equity read 45.5bn against a balance sheet
    saying 82.1bn.

    A statement of shareholders' equity is laid out with equity *components*
    across the top -- "Common Stock", "Total", "Cumulative Effect, Period of
    Adoption" -- and its rows are the roll-forward, so a value there is one
    movement in one component rather than a balance at a date.
    """
    components = [
        column("0", "Total", None, None),
        column("1", "Common Stock", None, None),
    ]
    equity_statement = statement(
        "Consolidated Statements of Redeemable Noncontrolling Interests and Equity",
        components,
        [
            row(
                "Balance",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
                {"0": "45489", "1": "3"},
            )
        ],
    )
    balance_sheet = statement(
        "Consolidated Balance Sheets",
        INSTANTS,
        [row("Total stockholders equity", "StockholdersEquity", {"0": "82137"})],
    )

    found = metrics_for([balance_sheet, equity_statement], ACCESSION, "10-K")
    assert found.newest(Metric.TOTAL_EQUITY).value == Decimal("82137")


def test_a_balance_is_never_taken_from_a_duration_column():
    """A category error that would otherwise surface as an inexplicable number."""
    found = metrics_for(
        [statement("OPERATIONS", PERIOD, [row("Total assets", "Assets", {"0": "359241"})])],
        ACCESSION,
        "10-K",
    )
    assert Metric.TOTAL_ASSETS not in found.periods


def test_a_flow_is_never_taken_from_an_instant_column():
    found = metrics_for(
        [
            statement(
                "BALANCE SHEETS",
                INSTANTS,
                [row("Net sales", "RevenueFromContractWithCustomerExcludingAssessedTax", {"0": "1"})],
            )
        ],
        ACCESSION,
        "10-K",
    )
    assert Metric.REVENUE not in found.periods


def test_capital_expenditure_comes_back_as_an_amount_spent():
    """The exhibit prints it as "(11,000)" because it reduces cash. A reader
    comparing capex means eleven billion spent, not negative eleven billion."""
    cash_flow = statement(
        "STATEMENTS OF CASH FLOWS",
        PERIOD,
        [row("Payments for PP&E", "PaymentsToAcquirePropertyPlantAndEquipment", {"0": "-12720"})],
    )
    assert metrics_for([cash_flow], ACCESSION, "10-K").newest(Metric.CAPEX).value == Decimal(
        "12720"
    )


def test_a_line_the_filer_does_not_print_is_absent_not_invented():
    """Costco reports no gross profit and Coca-Cola no total liabilities.
    Both are the filer's choice, and an empty cell is the honest answer."""
    found = metrics_for(
        [income(RevenueFromContractWithCustomerExcludingAssessedTax={"0": "275235"})],
        ACCESSION,
        "10-K",
    )
    assert found.newest(Metric.GROSS_PROFIT) is None


def test_the_element_used_is_reported_alongside_the_value():
    """Two filers reporting the same metric under different names is the whole
    reason this map exists, so which line was used has to be visible."""
    found = metrics_for(
        [income(Revenues={"0": "47936"})], ACCESSION, "10-K"
    )
    assert found.newest(Metric.REVENUE).element == "us-gaap_Revenues"


def test_a_filing_printing_nothing_comparable_yields_nothing():
    empty = statement("OPERATIONS", PERIOD, [row("Something else", "Goodwill", {"0": "1"})])
    assert metrics_for([empty], ACCESSION, "10-K").periods == {}
