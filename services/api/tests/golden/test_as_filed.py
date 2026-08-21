"""Real filings, real figures.

Every number below was read from the SEC's own rendered exhibit and typed in by
hand. That is the point: the rest of the suite proves that given input X the
code produces Y, using numbers we invented. It cannot notice that we read the
wrong element, or that a filer's line never arrives, because it never compares
anything to a real filing.

These do. Each expectation is the digits printed on the page, which anyone can
check by opening the filing at the accession named in the test.

When one fails
--------------
Assume our code broke, not the expectation. A figure changes only if EDGAR
restated the filing, which is worth reading about before editing a number here.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.golden.conftest import MILLIONS, figure

#: Tesla labels its equity lines with a typographic apostrophe. Spelled from a
#: codepoint so the exact character is unambiguous in source -- the renderer
#: mangles non-ASCII in FilingSummary, and this is what proves we avoid it.
APOSTROPHE = chr(0x2019)

# ---------------------------------------------------------------------------
# Apple FY2025 10-K, accession 0000320193-25-000079
# https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/
# ---------------------------------------------------------------------------


def test_apple_income_statement_matches_the_filing(aapl_10k):
    """Three annual periods, $ in millions, as printed."""
    operations = aapl_10k.statement("operations")

    assert [c.label for c in operations.columns] == [
        "Sep. 27, 2025",
        "Sep. 28, 2024",
        "Sep. 30, 2023",
    ]
    assert [c.duration for c in operations.columns] == ["12 Months Ended"] * 3

    for label, expected in [
        ("Net sales", ["416161", "391035", "383285"]),
        ("Cost of sales", ["220960", "210352", "214137"]),
        ("Gross margin", ["195201", "180683", "169148"]),
        ("Research and development", ["34550", "31370", "29915"]),
        ("Selling, general and administrative", ["27601", "26097", "24932"]),
        ("Total operating expenses", ["62151", "57467", "54847"]),
    ]:
        for column, value in enumerate(expected):
            assert figure(operations, label, column) == Decimal(value) * MILLIONS, (
                f"{label!r} column {column}"
            )


def test_apple_income_statement_is_internally_consistent(aapl_10k):
    """Gross margin is revenue less cost, in the filing and in our reading."""
    operations = aapl_10k.statement("operations")
    for column in range(3):
        sales = figure(operations, "Net sales", column)
        cost = figure(operations, "Cost of sales", column)
        assert sales - cost == figure(operations, "Gross margin", column)


def test_apple_balance_sheet_matches_the_filing(aapl_10k):
    balance = aapl_10k.statement("balance")

    assert [c.label for c in balance.columns] == ["Sep. 27, 2025", "Sep. 28, 2024"]
    # Instants, not periods: a balance sheet column has no duration.
    assert [c.duration for c in balance.columns] == [None, None]

    for label, expected in [
        ("Cash and cash equivalents", ["35934", "29943"]),
        ("Marketable securities", ["18763", "35228"]),
        ("Accounts receivable, net", ["39777", "33410"]),
        # A line no canonical vocabulary would think to include, which is
        # exactly why the statements are rendered as filed.
        ("Vendor non-trade receivables", ["33180", "32833"]),
        ("Inventories", ["5718", "7286"]),
        ("Total current assets", ["147957", "152987"]),
    ]:
        for column, value in enumerate(expected):
            assert figure(balance, label, column) == Decimal(value) * MILLIONS, (
                f"{label!r} column {column}"
            )


def test_apple_scale_is_millions(aapl_10k):
    """The multiplier is read from the exhibit title, and everything downstream
    depends on it: getting it wrong is a factor of a thousand, silently."""
    assert aapl_10k.statement("operations").monetary_scale == Decimal(10) ** 6


# ---------------------------------------------------------------------------
# Apple Q3 FY2026 10-Q, accession 0000320193-26-000020
# https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/
#
# The filing that broke: two blocks side by side, both printing the same two
# period end dates. Keying values by the printed date collapsed them, and the
# statement reported nine months of revenue as the quarter's, four columns wide.
# ---------------------------------------------------------------------------


def test_apple_quarter_and_year_to_date_are_different_numbers(aapl_10q):
    operations = aapl_10q.statement("operations")

    assert [(c.label, c.duration) for c in operations.columns] == [
        ("Jun. 27, 2026", "3 Months Ended"),
        ("Jun. 28, 2025", "3 Months Ended"),
        ("Jun. 27, 2026", "9 Months Ended"),
        ("Jun. 28, 2025", "9 Months Ended"),
    ]

    for label, expected in [
        ("Net sales", ["109417", "94036", "364357", "313695"]),
        ("Cost of sales", ["54647", "50318", "185575", "166835"]),
        ("Gross margin", ["54770", "43718", "178782", "146860"]),
    ]:
        for column, value in enumerate(expected):
            assert figure(operations, label, column) == Decimal(value) * MILLIONS, (
                f"{label!r} column {column}"
            )


def test_a_quarter_is_smaller_than_its_own_year_to_date(aapl_10q):
    """The shape of the bug, asserted directly.

    When the year-to-date figures overwrote the quarterly ones, all four
    columns held the nine-month number and this comparison was an equality.
    """
    operations = aapl_10q.statement("operations")
    for quarter, cumulative in ((0, 2), (1, 3)):
        assert figure(operations, "Net sales", quarter) < figure(
            operations, "Net sales", cumulative
        )


def test_every_column_of_a_quarterly_statement_is_addressable(aapl_10q):
    """Four distinct keys for four columns, however the labels repeat."""
    operations = aapl_10q.statement("operations")
    keys = [c.key for c in operations.columns]
    assert len(set(keys)) == 4

    sales = next(r for r in operations.rows if r.label == "Net sales")
    assert len({sales.values[key] for key in keys}) == 4


# ---------------------------------------------------------------------------
# Tesla FY2025 10-K, accession 0001628280-26-003952
# https://www.sec.gov/Archives/edgar/data/1318605/000162828026003952/
# ---------------------------------------------------------------------------


def test_tesla_balance_sheet_matches_the_filing(tsla_10k):
    balance = tsla_10k.statement("balance")
    assert [c.label for c in balance.columns] == ["Dec. 31, 2025", "Dec. 31, 2024"]

    for label, expected in [
        ("Total assets", ["137806", "122070"]),
        ("Total liabilities", ["54941", "48390"]),
        ("Redeemable noncontrolling interests in subsidiaries", ["58", "63"]),
        (f"Total stockholders{APOSTROPHE} equity", ["82137", "72913"]),
        ("Noncontrolling interests in subsidiaries", ["670", "704"]),
        ("Total liabilities and equity", ["137806", "122070"]),
    ]:
        for column, value in enumerate(expected):
            assert figure(balance, label, column) == Decimal(value) * MILLIONS, (
                f"{label!r} column {column}"
            )


@pytest.mark.parametrize("column", [0, 1])
def test_teslas_balance_sheet_needs_its_mezzanine_to_balance(tsla_10k, column):
    """Assets = Liabilities + Temporary equity + Equity, on a real filing.

    Tesla prints redeemable non-controlling interests between liabilities and
    equity. Dropping that line leaves the equation short by exactly its
    carrying amount -- 58 here -- which is how 92 of Tesla's validation
    failures arose. Asserting the shortfall too means the test still means
    something if the term is ever quietly dropped again.
    """
    balance = tsla_10k.statement("balance")
    assets = figure(balance, "Total assets", column)
    liabilities = figure(balance, "Total liabilities", column)
    mezzanine = figure(balance, "Redeemable noncontrolling interests in subsidiaries", column)
    equity = figure(balance, f"Total stockholders{APOSTROPHE} equity", column)
    minority = figure(balance, "Noncontrolling interests in subsidiaries", column)

    assert liabilities + mezzanine + equity + minority == assets
    assert liabilities + equity + minority == assets - mezzanine


def test_tesla_uses_a_curly_apostrophe_the_renderer_would_have_mangled(tsla_10k):
    """FilingSummary's ShortName arrives with non-ASCII already replaced by
    question marks, so statement names are taken from the exhibit itself."""
    balance = tsla_10k.statement("balance")
    assert any(APOSTROPHE in row.label for row in balance.rows)
    assert "?" not in balance.display_name
