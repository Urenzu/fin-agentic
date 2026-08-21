"""How much of a filing the comparison vocabulary can address.

This file used to measure something else: the share of statement lines the
canonical ledger had a concept for, floored per statement so the vocabulary
could be grown deliberately. That goal is retired. Growing a general vocabulary
to cover every line of every filer is an unbounded matching problem, and it was
reached about 56% before the approach was abandoned in favour of two things
that do not need it -- statements rendered as filed, and arithmetic checked
against the filer's own calculation linkbase.

What is left needing a vocabulary is comparison, and only comparison: putting
two companies side by side means deciding their lines correspond. So what is
measured here is the twelve metrics that job actually needs, over real filings.

An absence is not a gap in the vocabulary when the filer prints no such line.
Costco reports no gross profit and Coca-Cola no total liabilities; both are the
filer's own choice, and the expectations below name them so a genuine
regression is not lost among them.
"""

from __future__ import annotations

import pytest

from finagentic.compare.extract import metrics_for
from finagentic.compare.metrics import Metric
from tests.golden.conftest import CapturedFiling, load

#: Metrics each captured filing genuinely does not report, with the reason.
#: Anything absent and not listed here is a regression.
#: All three captured filings currently report all twelve. A filer that prints
#: fewer belongs here with the reason, not silently.
EXPECTED_ABSENT: dict[str, set[Metric]] = {
    "aapl_10k": set(),
    "aapl_10q": set(),
    "tsla_10k": set(),
}


def metrics_of(name: str):
    filing = CapturedFiling(name)
    raw = load(name)
    statements = [filing.statement(r["short_name"]) for r in raw["reports"]]
    return metrics_for(statements, raw["filing"]["accession"], raw["filing"]["form"])


@pytest.mark.parametrize("name", sorted(EXPECTED_ABSENT))
def test_every_comparable_metric_resolves(name):
    found = metrics_of(name)
    absent = {m for m in Metric if found.newest(m) is None}
    assert absent == EXPECTED_ABSENT[name], (
        f"{name}: metrics that did not resolve are {sorted(m.value for m in absent)}, "
        f"expected {sorted(m.value for m in EXPECTED_ABSENT[name])}"
    )


@pytest.mark.parametrize("name", sorted(EXPECTED_ABSENT))
def test_the_balance_sheet_balances_in_the_extracted_metrics(name):
    """A cheap end-to-end proof that the right rows were picked.

    Assets, liabilities and equity are read independently, from different rows
    and sometimes different statements. That they add up means none of them
    landed on a segment breakout or an equity-statement component -- which is
    exactly how Tesla's equity once read 45.5bn against a balance sheet saying
    82.1bn.

    Loose by design: this does not model non-controlling interests or the
    mezzanine, which are genuinely outside the twelve.
    """
    found = metrics_of(name)
    assets = found.newest(Metric.TOTAL_ASSETS)
    liabilities = found.newest(Metric.TOTAL_LIABILITIES)
    equity = found.newest(Metric.TOTAL_EQUITY)
    if not (assets and liabilities and equity):
        pytest.skip("this filer does not print all three")

    residual = abs(assets.value - liabilities.value - equity.value)
    assert residual <= assets.value / 100, (
        f"{name}: assets {assets.value} vs liabilities {liabilities.value} plus "
        f"equity {equity.value} leaves {residual}, too much to be minority "
        f"interests and the mezzanine"
    )


@pytest.mark.parametrize("name", sorted(EXPECTED_ABSENT))
def test_a_metric_never_comes_from_a_column_that_is_not_a_period(name):
    """A statement of shareholders' equity puts equity *components* across the
    top, so a value there is a movement in one component, not a balance."""
    found = metrics_of(name)
    for periods in found.periods.values():
        for period in periods:
            assert period.end_date is not None, (
                f"{name}: {period.metric.value} came from column "
                f"{period.label!r}, which is not a period"
            )


@pytest.mark.parametrize("name", sorted(EXPECTED_ABSENT))
def test_instants_and_flows_do_not_change_places(name):
    """A balance has no period and a flow has no date. Reading one as the other
    is a category error that surfaces as an inexplicable number."""
    from finagentic.compare.metrics import INSTANT

    found = metrics_of(name)
    for metric, periods in found.periods.items():
        for period in periods:
            assert (metric in INSTANT) == (period.duration is None), (
                f"{name}: {metric.value} taken from a "
                f"{'duration' if period.duration else 'instant'} column"
            )


def test_capital_expenditure_is_reported_as_an_amount_spent():
    """The exhibit prints it as a deduction from cash."""
    capex = metrics_of("aapl_10k").newest(Metric.CAPEX)
    assert capex is not None
    assert capex.value > 0
