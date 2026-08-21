"""Real filings checked against the arithmetic their own filers published.

This replaces what the golden ledger tests used to give: evidence from two
independent readings of one filing agreeing. That pair was the rendered exhibit
against a canonical ledger built from `companyfacts`. The ledger is gone and
the pair is now stronger -- the filer's own calculation linkbase against the
filer's own facts, with no vocabulary of ours in between, and a denominator we
cannot flatter by deciding an element does not count.

Measured live over five filers' most recent 10-K when this was built: 395 of
395 relationships held. Two of those filings are captured here.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from finagentic.ingest.linkbase import parse_calculation_linkbase
from finagentic.validation.asfiled import reconcile
from tests.golden.conftest import CapturedFactsClient, load

#: Which captured filing's linkbase goes with which captured facts.
CAPTURED = {"aapl": "aapl_10k", "tsla": "tsla_10k"}


def reconciliation(company: str):
    client = CapturedFactsClient(f"{company}_facts")
    filing = load(CAPTURED[company])
    return reconcile(
        client.observations(client.registrant),
        parse_calculation_linkbase(filing["calculation_linkbase"] or ""),
        filing["filing"]["accession"],
    )


@pytest.mark.parametrize("company", sorted(CAPTURED))
def test_the_filing_agrees_with_its_own_arithmetic(company):
    result = reconciliation(company)

    assert result.evaluated > 0, "nothing was evaluated, so nothing is established"
    assert result.broken == (), (
        f"{company}: {len(result.broken)} of {result.evaluated} relationships the "
        f"filer published do not hold: "
        f"{[(r.total_element, str(r.delta)) for r in result.broken[:3]]}"
    )
    assert result.is_clean


@pytest.mark.parametrize(("company", "least"), [("aapl", 60), ("tsla", 40)])
def test_enough_is_checked_for_the_result_to_mean_something(company, least):
    """A denominator floor, because "all of them held" is only as strong as how
    many there were -- and this is the number the whole approach rests on."""
    result = reconciliation(company)
    assert result.evaluated >= least, (
        f"{company} evaluated only {result.evaluated} relationships; the filing "
        f"or the parser has lost most of what the filer published"
    )


@pytest.mark.parametrize("company", sorted(CAPTURED))
def test_a_wrong_figure_would_be_caught(company):
    """The test that proves the others can fail.

    A reconciliation that passes because it checks nothing looks exactly like
    one that passes because everything holds, so one figure is corrupted and
    the break has to appear.
    """
    client = CapturedFactsClient(f"{company}_facts")
    filing = load(CAPTURED[company])
    relationships = parse_calculation_linkbase(filing["calculation_linkbase"] or "")
    accession = filing["filing"]["accession"]

    observations = client.observations(client.registrant)
    # A relationship the clean run actually evaluated. Picking the first one
    # the linkbase happens to declare proves nothing: many are note
    # disclosures whose terms this filing never reports as consolidated
    # figures, so corrupting one would change an answer nobody computed.
    clean = reconcile(observations, relationships, accession)
    evaluated = clean.results[0].total_element
    corrupted = [
        replace(o, value=o.value + 1_000_000)
        if f"us-gaap_{o.tag}" == evaluated and o.accession == accession
        else o
        for o in observations
    ]

    result = reconcile(corrupted, relationships, accession)
    assert result.broken, "corrupting a published total did not break its relationship"


@pytest.mark.parametrize("company", sorted(CAPTURED))
def test_the_filer_published_the_arithmetic_at_all(company):
    """Calculation linkbases are optional, and a filing without one can only be
    displayed, not checked. Microsoft's FY2026 10-K ships none."""
    assert load(CAPTURED[company])["calculation_linkbase"] is not None
