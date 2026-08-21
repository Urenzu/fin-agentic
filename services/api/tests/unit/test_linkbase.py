"""Reading the arithmetic a filer publishes with its filing.

Fixtures below are trimmed from Apple's FY2025 10-K calculation linkbase,
preserving the markup exactly so the tests exercise the real structure.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from finagentic.ingest.edgar import XbrlObservation
from finagentic.ingest.linkbase import (
    calculation_filename,
    parse_calculation_linkbase,
)
from finagentic.validation.asfiled import reconcile

# ruff: noqa: E501 -- the locator hrefs are real and wrapping them would stop
# this being a faithful copy of the filing's markup.
OPERATIONS = """
<link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase">
  <link:calculationLink xlink:role="http://www.apple.com/role/CONSOLIDATEDSTATEMENTSOFOPERATIONS">
    <link:loc xlink:type="locator" xlink:label="loc_gp_1" xlink:href="https://xbrl.fasb.org/us-gaap/2025/elts/us-gaap-2025.xsd#us-gaap_GrossProfit"/>
    <link:loc xlink:type="locator" xlink:label="loc_rev_1" xlink:href="https://xbrl.fasb.org/us-gaap/2025/elts/us-gaap-2025.xsd#us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax"/>
    <link:loc xlink:type="locator" xlink:label="loc_cost_1" xlink:href="https://xbrl.fasb.org/us-gaap/2025/elts/us-gaap-2025.xsd#us-gaap_CostOfGoodsAndServicesSold"/>
    <link:calculationArc order="1" weight="1.0" xlink:arcrole="http://www.xbrl.org/2003/arcrole/summation-item" xlink:from="loc_gp_1" xlink:to="loc_rev_1"/>
    <link:calculationArc order="2" weight="-1.0" xlink:arcrole="http://www.xbrl.org/2003/arcrole/summation-item" xlink:from="loc_gp_1" xlink:to="loc_cost_1"/>
  </link:calculationLink>
</link:linkbase>
"""

FILING_SUMMARY = """
<FilingSummary>
<InputFiles>
<File doctype="10-K" original="aapl-20250927.htm">aapl-20250927.htm</File>
<File>aapl-20250927.xsd</File>
<File>aapl-20250927_cal.xml</File>
<File>aapl-20250927_lab.xml</File>
</InputFiles>
</FilingSummary>
"""

ACCESSION = "0000320193-25-000079"
FY_START, FY_END = date(2024, 9, 29), date(2025, 9, 27)


def obs(tag: str, value: str, *, accession: str = ACCESSION, frame: str | None = "CY2025"):
    return XbrlObservation(
        tag=tag,
        unit="USD",
        value=Decimal(value),
        end=FY_END,
        start=FY_START,
        fiscal_year=2025,
        fiscal_period="FY",
        form="10-K",
        accession=accession,
        filed=date(2025, 10, 31),
        frame=frame,
    )


APPLE_FY2025 = [
    obs("GrossProfit", "195201"),
    obs("RevenueFromContractWithCustomerExcludingAssessedTax", "416161"),
    obs("CostOfGoodsAndServicesSold", "220960"),
]


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------


def test_a_relationship_carries_its_total_and_signed_components():
    relationships = parse_calculation_linkbase(OPERATIONS)
    assert len(relationships) == 1

    relationship = relationships[0]
    assert relationship.total == "us-gaap_GrossProfit"
    assert [(c.element, c.weight) for c in relationship.components] == [
        ("us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax", Decimal("1.0")),
        ("us-gaap_CostOfGoodsAndServicesSold", Decimal("-1.0")),
    ]


def test_components_come_back_in_the_order_the_filer_gave():
    """`order` is the filer's presentation order, so a rendered relationship
    reads the way the statement does."""
    reversed_arcs = OPERATIONS.replace('order="1"', 'order="9"').replace(
        'order="2"', 'order="1"'
    )
    components = parse_calculation_linkbase(reversed_arcs)[0].components
    assert components[0].element.endswith("CostOfGoodsAndServicesSold")


def test_the_statement_is_named_by_the_tail_of_the_role():
    assert parse_calculation_linkbase(OPERATIONS)[0].statement_name == (
        "CONSOLIDATEDSTATEMENTSOFOPERATIONS"
    )


def test_an_arc_without_a_weight_is_not_a_relationship():
    """Assuming +1 would invent arithmetic the filer never stated."""
    unweighted = OPERATIONS.replace(' weight="-1.0"', "")
    assert len(parse_calculation_linkbase(unweighted)[0].components) == 1


def test_an_arc_naming_an_undeclared_locator_is_skipped():
    broken = OPERATIONS.replace('xlink:label="loc_cost_1"', 'xlink:label="loc_other"')
    assert len(parse_calculation_linkbase(broken)[0].components) == 1


def test_a_linkbase_with_nothing_in_it_parses_to_nothing():
    assert parse_calculation_linkbase("<link:linkbase/>") == []


def test_the_linkbase_is_found_from_the_filing_summary():
    """Read from the summary, which is already fetched for the exhibit list, so
    discovering the linkbase costs no extra request."""
    assert calculation_filename(FILING_SUMMARY) == "aapl-20250927_cal.xml"


def test_a_filing_shipping_no_linkbase_is_reported_as_such():
    """Microsoft's FY2026 10-K publishes none at all."""
    assert calculation_filename(FILING_SUMMARY.replace("_cal.xml", "_def.xml")) is None


# ---------------------------------------------------------------------------
# reconciliation
# ---------------------------------------------------------------------------


def test_a_filing_that_agrees_with_its_own_arithmetic_is_clean():
    result = reconcile(APPLE_FY2025, parse_calculation_linkbase(OPERATIONS), ACCESSION)

    assert result.evaluated == 1
    assert result.held == 1
    assert result.is_clean
    assert "All 1 relationships" in result.summary


def test_a_wrong_figure_breaks_the_relationship_that_names_it():
    facts = [
        obs("GrossProfit", "195201"),
        obs("RevenueFromContractWithCustomerExcludingAssessedTax", "416161"),
        obs("CostOfGoodsAndServicesSold", "999999"),
    ]
    result = reconcile(facts, parse_calculation_linkbase(OPERATIONS), ACCESSION)

    assert not result.is_clean
    assert len(result.broken) == 1
    assert result.broken[0].total_element == "us-gaap_GrossProfit"


def test_signs_come_from_the_weights_not_from_the_printed_page():
    """The bug this file exists because of.

    Reading values off the rendered exhibit got 155 of 202. The exhibit prints
    a dividend payment as "(17,000)" while the weight of -1 assumes the
    standard sign, in which the fact is a positive magnitude -- so applying the
    weight to an already-negated figure negates it twice. Facts carry standard
    signs, and this asserts the subtraction actually happens.
    """
    result = reconcile(APPLE_FY2025, parse_calculation_linkbase(OPERATIONS), ACCESSION)
    evaluated = result.results[0]

    assert evaluated.actual == Decimal("416161") - Decimal("220960")
    assert evaluated.actual == Decimal("195201")


def test_a_relationship_missing_a_term_is_not_evaluated():
    """A sum short one term differs from its total by that term. Reporting it
    would be reporting our own gap as the filer's error."""
    facts = [f for f in APPLE_FY2025 if f.tag != "CostOfGoodsAndServicesSold"]
    result = reconcile(facts, parse_calculation_linkbase(OPERATIONS), ACCESSION)

    assert result.evaluated == 0
    assert result.unevaluated == ("us-gaap_GrossProfit",)
    assert not result.is_clean


def test_facts_from_other_filings_are_not_borrowed():
    """A company's facts span every filing it has made, and a comparative in a
    later 10-K is the same period reported again."""
    other = [obs(f.tag, str(f.value), accession="0000320193-24-000123") for f in APPLE_FY2025]
    result = reconcile(other, parse_calculation_linkbase(OPERATIONS), ACCESSION)

    assert result.facts_pending
    assert result.evaluated == 0


def test_dimensional_rows_do_not_stand_in_for_the_consolidated_total():
    """Apple tags revenue again under Products and Services. A segment figure
    replacing the total would break the relationship for no good reason."""
    facts = [
        obs("GrossProfit", "195201"),
        obs("RevenueFromContractWithCustomerExcludingAssessedTax", "416161"),
        obs("RevenueFromContractWithCustomerExcludingAssessedTax", "298085", frame=None),
        obs("CostOfGoodsAndServicesSold", "220960"),
    ]
    assert reconcile(facts, parse_calculation_linkbase(OPERATIONS), ACCESSION).is_clean


def test_a_filing_with_no_linkbase_is_not_reported_as_clean():
    """Nothing was checked, so nothing is established -- the failure the old
    'corroborated' percentage made every time."""
    result = reconcile(APPLE_FY2025, [], ACCESSION)

    assert result.no_linkbase
    assert not result.is_clean
    assert "no calculation linkbase" in result.summary


def test_facts_not_yet_published_are_told_apart_from_nothing_to_check():
    """The exhibits appear when a filing is submitted; the facts API catches up
    later. Coca-Cola's 10-Q filed 29 July 2026 rendered in full while
    contributing no observations at all."""
    result = reconcile([], parse_calculation_linkbase(OPERATIONS), ACCESSION)

    assert result.facts_pending
    assert not result.no_linkbase
    assert not result.is_clean
    assert "has not published" in result.summary


def test_rounding_in_the_filing_is_not_reported_as_a_break():
    """Figures are printed rounded, so a total may differ from its components
    by the accumulated rounding of the terms."""
    facts = [
        obs("GrossProfit", "195201"),
        obs("RevenueFromContractWithCustomerExcludingAssessedTax", "416161"),
        obs("CostOfGoodsAndServicesSold", "220960.0001"),
    ]
    assert reconcile(facts, parse_calculation_linkbase(OPERATIONS), ACCESSION).is_clean
