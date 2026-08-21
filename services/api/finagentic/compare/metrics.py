"""A deliberately small vocabulary, for the one job that needs one.

Everything else in this system is per filing: the statements are rendered as
the filer laid them out, and the arithmetic is checked against what the filer
themselves published. Neither needs to know that Apple's "Net sales" and
Tesla's "Total revenues" are the same thing.

Comparison does. There is no way around it -- putting two companies side by
side means deciding their lines correspond -- so this is the one place a
mapping is unavoidable, and it is kept as small as the job allows.

Why twelve and not a hundred
----------------------------
A general vocabulary of the whole balance sheet is an unbounded matching
problem: filers use 500 to 900 distinct elements each, the set changes with
every accounting standard, and a concept that silently fails to match
disappears from the ledger without a symptom. That was tried here and reached
about half the lines on a statement.

These twelve are what anyone actually compares between two companies. The
variation among filers is narrow, the aliases are few and stable, and -- the
part that matters -- an error is *visible*: revenue landing on the wrong
element produces a number nobody could mistake for right. A vocabulary whose
failures are obvious can be small and honest; one whose failures are silent has
to be exhaustive, and cannot be.

Anything outside this list is not missing. It is on the statement, rendered as
filed, where it always was.
"""

from __future__ import annotations

from enum import StrEnum


class Metric(StrEnum):
    """The headline figures a reader compares between two companies."""

    REVENUE = "revenue"
    GROSS_PROFIT = "gross_profit"
    OPERATING_INCOME = "operating_income"
    NET_INCOME = "net_income"
    TOTAL_ASSETS = "total_assets"
    TOTAL_LIABILITIES = "total_liabilities"
    TOTAL_EQUITY = "total_equity"
    CASH = "cash"
    OPERATING_CASH_FLOW = "operating_cash_flow"
    CAPEX = "capex"
    SHARES_DILUTED = "shares_diluted"
    EPS_DILUTED = "eps_diluted"


#: Human-facing names. Chosen to be neutral rather than to match any one
#: filer's wording, since the whole point is that filers differ.
LABELS: dict[Metric, str] = {
    Metric.REVENUE: "Revenue",
    Metric.GROSS_PROFIT: "Gross profit",
    Metric.OPERATING_INCOME: "Operating income",
    Metric.NET_INCOME: "Net income",
    Metric.TOTAL_ASSETS: "Total assets",
    Metric.TOTAL_LIABILITIES: "Total liabilities",
    Metric.TOTAL_EQUITY: "Total equity",
    Metric.CASH: "Cash and equivalents",
    Metric.OPERATING_CASH_FLOW: "Operating cash flow",
    Metric.CAPEX: "Capital expenditure",
    Metric.SHARES_DILUTED: "Diluted shares",
    Metric.EPS_DILUTED: "Diluted EPS",
}

#: Balance sheet metrics are measured at an instant; the rest over a period.
#: A duration figure matched to an instant, or the reverse, is a category error
#: that would otherwise surface as an inexplicable number.
#: Diluted shares are deliberately absent: a weighted average is taken over a
#: period, not at a date, however much it looks like a balance.
INSTANT: frozenset[Metric] = frozenset(
    {
        Metric.TOTAL_ASSETS,
        Metric.TOTAL_LIABILITIES,
        Metric.TOTAL_EQUITY,
        Metric.CASH,
    }
)

#: us-gaap elements for each metric, best first.
#:
#: Order is precedence, not preference: where a filer reports several, the
#: first is the one that means the metric. `Revenues` sits behind the
#: contract-with-customer elements because a filer using both reports the
#: newer standard's figure as the headline and `Revenues` as a broader total.
ALIASES: dict[Metric, tuple[str, ...]] = {
    Metric.REVENUE: (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ),
    Metric.GROSS_PROFIT: ("GrossProfit",),
    Metric.OPERATING_INCOME: ("OperatingIncomeLoss",),
    # Attributable to the parent, which is the "net income" a reader means and
    # the numerator of EPS. `ProfitLoss` includes non-controlling interests and
    # is a different population, so it is not an alias.
    Metric.NET_INCOME: ("NetIncomeLoss",),
    Metric.TOTAL_ASSETS: ("Assets",),
    Metric.TOTAL_LIABILITIES: ("Liabilities",),
    # Including non-controlling interests first: comparing one company's whole
    # equity against another's parent-only share is the mistake this ordering
    # exists to avoid.
    Metric.TOTAL_EQUITY: (
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "StockholdersEquity",
    ),
    Metric.CASH: (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    Metric.OPERATING_CASH_FLOW: (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    Metric.CAPEX: (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ),
    Metric.SHARES_DILUTED: ("WeightedAverageNumberOfDilutedSharesOutstanding",),
    Metric.EPS_DILUTED: ("EarningsPerShareDiluted",),
}

#: Element -> metric, with the first alias winning where one element could
#: serve two metrics. Built once; the map is small enough to be exhaustive.
BY_ELEMENT: dict[str, Metric] = {
    element: metric for metric, elements in ALIASES.items() for element in reversed(elements)
}


def rank(metric: Metric, element: str) -> int:
    """Where `element` sits in the metric's precedence, lower being better."""
    try:
        return ALIASES[metric].index(element)
    except ValueError:
        return len(ALIASES[metric])


def is_instant(metric: Metric) -> bool:
    return metric in INSTANT


__all__ = ["ALIASES", "BY_ELEMENT", "INSTANT", "LABELS", "Metric", "is_instant", "rank"]
