"""Parsing the SEC's rendered statement exhibits.

Fixtures below are trimmed from Apple's FY2025 10-K, preserving the markup
exactly so the tests exercise the real structure rather than an idealised one.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from finagentic.ingest.edgar import parse_filing_summary
from finagentic.ingest.rfiles import parse_statement

BALANCE_SHEET = """
<table class="report">
<tr>
<th class="tl" colspan="1" rowspan="1"><div><strong>CONSOLIDATED BALANCE SHEETS - USD ($)<br>
 shares in Thousands, $ in Millions</strong></div></th>
<th class="th"><div>Sep. 27, 2025</div></th>
<th class="th"><div>Sep. 28, 2024</div></th>
</tr>
<tr class="re">
<td class="pl"><a onclick="Show.showAR( this, 'defref_us-gaap_AssetsCurrentAbstract', window );">
<strong>Current assets:</strong></a></td>
<td class="text">&#160;<span></span></td>
<td class="text">&#160;<span></span></td>
</tr>
<tr class="ro">
<td class="pl"><a onclick="Show.showAR( this, 'defref_us-gaap_CashAndCashEquivalentsAtCarryingValue', window );">
Cash and cash equivalents</a></td>
<td class="nump">$ 35,934<span></span></td>
<td class="nump">$ 29,943<span></span></td>
</tr>
<tr class="re">
<td class="pl"><a onclick="Show.showAR( this, 'defref_us-gaap_NontradeReceivablesCurrent', window );">
Vendor non-trade receivables</a></td>
<td class="nump">33,180<span></span></td>
<td class="nump">32,833<span></span></td>
</tr>
<tr class="rou">
<td class="pl"><a onclick="Show.showAR( this, 'defref_us-gaap_AssetsCurrent', window );">
Total current assets</a></td>
<td class="nump">147,957<span></span></td>
<td class="nump">152,987<span></span></td>
</tr>
<tr class="ro">
<td class="pl"><a onclick="Show.showAR( this, 'defref_us-gaap_RetainedEarningsAccumulatedDeficit', window );">
Accumulated deficit</a></td>
<td class="num">(14,264)<span></span></td>
<td class="num">(19,154)<span></span></td>
</tr>
</table>
"""

CASH_FLOW = """
<table class="report">
<tr>
<th class="tl" colspan="1" rowspan="2"><div><strong>CONSOLIDATED STATEMENTS OF CASH FLOWS - USD ($)<br>
 $ in Millions</strong></div></th>
<th class="th" colspan="3">12 Months Ended</th>
</tr>
<tr>
<th class="th"><div>Sep. 27, 2025</div></th>
<th class="th"><div>Sep. 28, 2024</div></th>
<th class="th"><div>Sep. 30, 2023</div></th>
</tr>
<tr class="re">
<td class="pl"><a onclick="Show.showAR( this, 'defref_us-gaap_NetIncomeLoss', window );">Net income</a></td>
<td class="nump">112,010<span></span></td>
<td class="nump">93,736<span></span></td>
<td class="nump">96,995<span></span></td>
</tr>
</table>
"""

PER_SHARE = """
<table class="report">
<tr>
<th class="tl"><div><strong>STATEMENTS OF OPERATIONS - USD ($)<br>
 shares in Thousands, $ in Millions</strong></div></th>
<th class="th"><div>Sep. 27, 2025</div></th>
</tr>
<tr class="ro">
<td class="pl"><a onclick="Show.showAR( this, 'defref_us-gaap_EarningsPerShareDiluted', window );">
Diluted (in dollars per share)</a></td>
<td class="nump">$ 7.46<span></span></td>
</tr>
<tr class="ro">
<td class="pl"><a onclick="Show.showAR( this, 'defref_us-gaap_WeightedAverageNumberOfDilutedSharesOutstanding', window );">
Diluted (in shares)</a></td>
<td class="nump">15,004,730<span></span></td>
</tr>
</table>
"""


# ---------------------------------------------------------------------------
# structure
# ---------------------------------------------------------------------------


def test_the_title_and_columns_are_read():
    st = parse_statement(BALANCE_SHEET)
    assert "CONSOLIDATED BALANCE SHEETS" in st.title
    assert st.columns == ("Sep. 27, 2025", "Sep. 28, 2024")


def test_column_headings_are_parsed_as_dates():
    st = parse_statement(BALANCE_SHEET)
    assert st.column_dates == (date(2025, 9, 27), date(2024, 9, 28))


def test_a_spanning_header_is_not_treated_as_a_column():
    """"12 Months Ended" spans the period columns rather than being one.

    Counting it shifts every value one column left, silently attributing a whole
    statement to the wrong periods.
    """
    st = parse_statement(CASH_FLOW)
    assert st.columns == ("Sep. 27, 2025", "Sep. 28, 2024", "Sep. 30, 2023")


def test_values_align_to_the_right_periods():
    st = parse_statement(CASH_FLOW)
    row = st.row_for("NetIncomeLoss")
    assert row is not None
    assert row.values["Sep. 27, 2025"] == Decimal("112010") * 10**6
    assert row.values["Sep. 28, 2024"] == Decimal("93736") * 10**6


def test_section_headings_are_marked_abstract():
    st = parse_statement(BALANCE_SHEET)
    heading = st.rows[0]
    assert heading.is_abstract
    assert heading.label == "Current assets:"
    assert heading.values == {}


def test_items_are_indented_under_their_section():
    st = parse_statement(BALANCE_SHEET)
    cash = st.row_for("CashAndCashEquivalentsAtCarryingValue")
    assert cash is not None
    assert cash.indent == 1


def test_a_total_row_closes_the_section():
    """Underlined rows are subtotals, and they return to the outer level."""
    st = parse_statement(BALANCE_SHEET)
    total = st.row_for("AssetsCurrent")
    assert total is not None
    assert total.is_total
    assert total.indent == 0


def test_the_filers_own_labels_are_preserved():
    """The point of rendering as filed: Apple's wording, not our vocabulary."""
    st = parse_statement(BALANCE_SHEET)
    labels = [r.label for r in st.rows]
    assert "Vendor non-trade receivables" in labels


def test_lines_outside_any_canonical_vocabulary_still_appear():
    """A $33bn line no canonical model would include is the reason for this path."""
    st = parse_statement(BALANCE_SHEET)
    row = st.row_for("NontradeReceivablesCurrent")
    assert row is not None
    assert row.values["Sep. 27, 2025"] == Decimal("33180") * 10**6


# ---------------------------------------------------------------------------
# values
# ---------------------------------------------------------------------------


def test_the_monetary_scale_is_applied():
    st = parse_statement(BALANCE_SHEET)
    assert st.monetary_scale == Decimal(1_000_000)
    cash = st.row_for("CashAndCashEquivalentsAtCarryingValue")
    assert cash is not None
    assert cash.values["Sep. 27, 2025"] == Decimal("35934") * 10**6


def test_currency_symbols_and_separators_are_stripped():
    st = parse_statement(BALANCE_SHEET)
    cash = st.row_for("CashAndCashEquivalentsAtCarryingValue")
    assert cash is not None
    assert cash.values["Sep. 28, 2024"] == Decimal("29943") * 10**6


def test_parenthesised_values_are_negative():
    st = parse_statement(BALANCE_SHEET)
    deficit = st.row_for("RetainedEarningsAccumulatedDeficit")
    assert deficit is not None
    assert deficit.values["Sep. 27, 2025"] == Decimal("-14264") * 10**6


def test_blank_cells_are_absent_rather_than_zero():
    st = parse_statement(BALANCE_SHEET)
    heading = st.rows[0]
    assert "Sep. 27, 2025" not in heading.values


def test_per_share_amounts_do_not_take_the_monetary_scale():
    """EPS printed under a "$ in Millions" heading is still dollars per share.

    Scaling it produces a figure wrong by six orders of magnitude that still
    looks plausible.
    """
    st = parse_statement(PER_SHARE)
    eps = st.row_for("EarningsPerShareDiluted")
    assert eps is not None
    assert eps.values["Sep. 27, 2025"] == Decimal("7.46")


def test_share_counts_take_the_share_scale_not_the_monetary_one():
    st = parse_statement(PER_SHARE)
    shares = st.row_for("WeightedAverageNumberOfDilutedSharesOutstanding")
    assert shares is not None
    assert shares.values["Sep. 27, 2025"] == Decimal("15004730") * 1000


def test_element_names_are_retained_for_cross_reference():
    """The element is what links an as-filed row back to the canonical ledger."""
    st = parse_statement(BALANCE_SHEET)
    cash = st.row_for("CashAndCashEquivalentsAtCarryingValue")
    assert cash is not None
    assert cash.element == "us-gaap_CashAndCashEquivalentsAtCarryingValue"
    assert cash.is_us_gaap


def test_line_count_excludes_headings():
    st = parse_statement(BALANCE_SHEET)
    assert st.line_count == len(st.rows) - 1


def test_an_empty_document_parses_to_nothing():
    st = parse_statement("<table class='report'></table>")
    assert st.rows == ()
    assert st.columns == ()


# ---------------------------------------------------------------------------
# FilingSummary
# ---------------------------------------------------------------------------

FILING_SUMMARY = """
<FilingSummary>
<MyReports>
<Report instance="aapl.htm">
<HtmlFileName>R5.htm</HtmlFileName>
<LongName>1003 - Statement - CONSOLIDATED BALANCE SHEETS</LongName>
<ShortName>CONSOLIDATED BALANCE SHEETS</ShortName>
<MenuCategory>Statements</MenuCategory>
</Report>
<Report instance="aapl.htm">
<HtmlFileName>R6.htm</HtmlFileName>
<LongName>1004 - Statement - CONSOLIDATED BALANCE SHEETS (Parenthetical)</LongName>
<ShortName>CONSOLIDATED BALANCE SHEETS (Parenthetical)</ShortName>
<MenuCategory>Statements</MenuCategory>
</Report>
<Report instance="aapl.htm">
<HtmlFileName>R9.htm</HtmlFileName>
<LongName>2101 - Disclosure - Summary of Significant Accounting Policies</LongName>
<ShortName>Summary of Significant Accounting Policies</ShortName>
<MenuCategory>Notes</MenuCategory>
</Report>
</MyReports>
</FilingSummary>
"""


def test_filing_summary_lists_reports():
    reports = parse_filing_summary(FILING_SUMMARY)
    assert [r.filename for r in reports] == ["R5.htm", "R6.htm", "R9.htm"]


def test_statements_are_distinguished_from_notes():
    """The SEC's own categorisation is what lets us render only the statements."""
    reports = parse_filing_summary(FILING_SUMMARY)
    statements = [r for r in reports if r.is_statement]

    assert len(statements) == 2
    assert all("BALANCE SHEETS" in r.short_name for r in statements)


def test_parenthetical_exhibits_are_identified():
    """They restate par values and share counts already on the face."""
    reports = parse_filing_summary(FILING_SUMMARY)
    parenthetical = [r for r in reports if r.is_parenthetical]
    assert [r.filename for r in parenthetical] == ["R6.htm"]


def test_display_name_strips_the_units_annotation():
    st = parse_statement(BALANCE_SHEET)
    assert st.display_name == "CONSOLIDATED BALANCE SHEETS"


def test_display_name_preserves_characters_filing_summary_mangles():
    """The SEC's FilingSummary.xml emits Chipotle's "SHAREHOLDERS' EQUITY" as
    "SHAREHOLDERS??? EQUITY". The exhibit itself carries the correct entity, so
    taking the name from here avoids inheriting that corruption."""
    html = BALANCE_SHEET.replace(
        "CONSOLIDATED BALANCE SHEETS", "STATEMENTS OF SHAREHOLDERS&#8217; EQUITY"
    )
    assert parse_statement(html).display_name == "STATEMENTS OF SHAREHOLDERS\u2019 EQUITY"
