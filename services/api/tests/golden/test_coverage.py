"""How much of a statement the concept vocabulary can actually represent.

The as-filed exhibits are the SEC's own rendering, so their rows are exactly
the lines a reader sees. A row whose element has no concept is a hole the
ledger cannot fill: no error, no wrong number, just a line that silently is not
there. Measuring against the exhibits rather than against `companyfacts` is
what makes the number honest -- the denominator is chosen by the filer, and we
cannot improve it by deciding a tag does not count.

Not a target of 100% for its own sake. Coverage matters because a missing
component is what turns an accounting identity from a check into a skip, and a
skipped check corroborates nothing.

The floors are ratchets. They are set at what the code achieves today, so any
regression fails immediately and any improvement asks to be recorded.
"""

from __future__ import annotations

from collections import Counter

import pytest

from finagentic.ingest.tag_map import concept_for
from tests.golden.conftest import CapturedFiling, load

#: Per statement, per filing: the share of us-gaap rows carrying a concept.
#:
#: The shape of this table is the finding, and it has moved. The equity
#: roll-forward went from a fifth covered to complete for Apple, and
#: comprehensive income from a tenth to three fifths, once those two statements
#: were given a vocabulary. What remains is the cash flow statement, whose gaps
#: are individually-named operating adjustments rather than a missing category.
FLOORS: dict[tuple[str, str], float] = {
    ("aapl_10k", "OPERATIONS"): 1.00,
    ("aapl_10k", "COMPREHENSIVE"): 0.60,
    ("aapl_10k", "BALANCE"): 0.89,
    ("aapl_10k", "SHAREHOLDERS"): 1.00,
    ("aapl_10k", "CASH FLOWS"): 0.62,
    ("aapl_10q", "OPERATIONS"): 1.00,
    ("aapl_10q", "COMPREHENSIVE"): 0.60,
    ("aapl_10q", "BALANCE"): 0.96,
    ("aapl_10q", "SHAREHOLDERS"): 1.00,
    ("aapl_10q", "CASH FLOWS"): 0.62,
    ("tsla_10k", "OPERATIONS"): 1.00,
    ("tsla_10k", "COMPREHENSIVE"): 0.57,
    ("tsla_10k", "BALANCE"): 0.75,
    ("tsla_10k", "REDEEMABLE NONCON"): 0.51,
    ("tsla_10k", "CASH FLOWS"): 0.50,
}

#: Overall, per filing.
OVERALL_FLOORS = {"aapl_10k": 0.84, "aapl_10q": 0.87, "tsla_10k": 0.68}

#: How far above its floor a measurement may drift before the floor is stale.
#: Generous, because the point is to notice a step change rather than to
#: complain about a rounding difference.
RATCHET_SLACK = 0.05


def _rows(filing: CapturedFiling, short_name: str):
    """The rows a reader sees a number on.

    Rows carrying no value in any column are excluded. The equity statement
    repeats a `[Roll Forward]` element as a structural header once per year
    column, and counting those as unmapped lines charged the vocabulary for
    failing to represent something that is not a figure.
    """
    statement = filing.statement(short_name)
    return [
        r
        for r in statement.rows
        if not r.is_abstract and r.tag and r.is_us_gaap and r.values
    ]


def measure(name: str) -> tuple[dict[str, tuple[int, int]], tuple[int, int], Counter]:
    """Coverage per statement, overall, and what is missing."""
    filing = CapturedFiling(name)
    per_statement: dict[str, tuple[int, int]] = {}
    unmapped: Counter = Counter()
    hit = total = 0

    for report in load(name)["reports"]:
        rows = _rows(filing, report["short_name"])
        if not rows:
            continue
        mapped = 0
        for row in rows:
            if concept_for(row.tag) is not None:
                mapped += 1
            else:
                unmapped[row.tag] += 1
        per_statement[report["short_name"].upper()] = (mapped, len(rows))
        hit += mapped
        total += len(rows)

    return per_statement, (hit, total), unmapped


@pytest.mark.parametrize("name", sorted(OVERALL_FLOORS))
def test_overall_coverage_does_not_regress(name):
    _, (hit, total), unmapped = measure(name)
    share = hit / total
    floor = OVERALL_FLOORS[name]
    assert share >= floor, (
        f"{name}: {hit}/{total} = {share:.1%} of statement lines carry a concept, "
        f"below the floor of {floor:.0%}. Most common elements with no concept: "
        f"{[t for t, _ in unmapped.most_common(8)]}"
    )


@pytest.mark.parametrize(("name", "fragment"), sorted(FLOORS))
def test_per_statement_coverage_does_not_regress(name, fragment):
    """Per statement as well as overall, so a gain in one cannot hide a loss in
    another -- the equity statement is a quarter of the rows in a 10-Q."""
    per_statement, _, _ = measure(name)
    matches = [(k, v) for k, v in per_statement.items() if fragment in k]
    assert len(matches) == 1, f"{fragment!r} matched {[k for k, _ in matches]}"

    short_name, (mapped, total) = matches[0]
    share = mapped / total
    assert share >= FLOORS[(name, fragment)], (
        f"{name} / {short_name}: {mapped}/{total} = {share:.1%}, below "
        f"{FLOORS[(name, fragment)]:.0%}"
    )


@pytest.mark.parametrize(("name", "fragment"), sorted(FLOORS))
def test_a_floor_that_has_been_left_behind_is_reported(name, fragment):
    """Coverage well above its floor means the floor stopped protecting
    anything. Raising it is the point of doing the work."""
    per_statement, _, _ = measure(name)
    short_name, (mapped, total) = next(
        (k, v) for k, v in per_statement.items() if fragment in k
    )
    share = mapped / total
    floor = FLOORS[(name, fragment)]
    assert share <= floor + RATCHET_SLACK, (
        f"{name} / {short_name} is now {share:.1%}, well above its floor of "
        f"{floor:.0%}. Raise the floor in FLOORS so it protects the gain."
    )


def test_the_income_statement_is_completely_covered():
    """The one statement with no holes, stated as an expectation rather than
    an observation: a regression here would be a serious one."""
    for name in OVERALL_FLOORS:
        per_statement, _, _ = measure(name)
        mapped, total = next(
            v for k, v in per_statement.items() if "OPERATIONS" in k
        )
        assert mapped == total, f"{name}: {total - mapped} operations rows lost a concept"


def test_the_equity_statement_is_completely_covered_for_apple():
    """It was a fifth covered. Every movement between one balance sheet's
    equity and the next now has a concept, which is what makes the
    roll-forward identity possible at all."""
    for name in ("aapl_10k", "aapl_10q"):
        per_statement, _, _ = measure(name)
        mapped, total = next(v for k, v in per_statement.items() if "SHAREHOLDERS" in k)
        assert mapped == total, f"{name}: {total - mapped} equity rows lost a concept"


def test_the_remaining_gap_has_moved_to_the_cash_flow_statement():
    """Where the next round of work is, asserted so the claim stays current.

    Comprehensive income and the equity roll-forward were most of the gap and
    are no longer. What is left is dominated by the cash flow statement, whose
    holes are individually-named operating adjustments -- a long tail of
    filer-specific lines rather than a missing category, so closing it is
    steady work rather than one more design decision.
    """
    per_kind: dict[str, int] = {}
    for name in OVERALL_FLOORS:
        per_statement, _, _ = measure(name)
        for short_name, (mapped, total) in per_statement.items():
            kind = "cash flow" if "CASH FLOW" in short_name else "everything else"
            per_kind[kind] = per_kind.get(kind, 0) + (total - mapped)

    assert sum(per_kind.values()) > 0
    share = per_kind.get("cash flow", 0) / sum(per_kind.values())
    assert share >= 0.35, (
        f"the cash flow statement is only {share:.0%} of what remains unmapped; "
        f"the next round of coverage work may belong somewhere else: {per_kind}"
    )
