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
#: The shape of this table is the finding. Operations is complete; the balance
#: sheet and cash flow are most of the way there; comprehensive income and the
#: equity roll-forward are barely modelled at all, and between them account for
#: nearly every hole. They are also the two statements that tie the other three
#: together across periods, so the missing coverage costs more than its size.
FLOORS: dict[tuple[str, str], float] = {
    ("aapl_10k", "OPERATIONS"): 1.00,
    ("aapl_10k", "COMPREHENSIVE"): 0.10,
    ("aapl_10k", "BALANCE"): 0.86,
    ("aapl_10k", "SHAREHOLDERS"): 0.21,
    ("aapl_10k", "CASH FLOWS"): 0.62,
    ("aapl_10q", "OPERATIONS"): 1.00,
    ("aapl_10q", "COMPREHENSIVE"): 0.10,
    ("aapl_10q", "BALANCE"): 0.92,
    ("aapl_10q", "SHAREHOLDERS"): 0.25,
    ("aapl_10q", "CASH FLOWS"): 0.62,
    ("tsla_10k", "OPERATIONS"): 1.00,
    ("tsla_10k", "COMPREHENSIVE"): 0.14,
    ("tsla_10k", "BALANCE"): 0.67,
    ("tsla_10k", "REDEEMABLE NONCON"): 0.24,
    ("tsla_10k", "CASH FLOWS"): 0.50,
}

#: Overall, per filing.
OVERALL_FLOORS = {"aapl_10k": 0.59, "aapl_10q": 0.56, "tsla_10k": 0.57}

#: How far above its floor a measurement may drift before the floor is stale.
#: Generous, because the point is to notice a step change rather than to
#: complain about a rounding difference.
RATCHET_SLACK = 0.05


def _rows(filing: CapturedFiling, short_name: str):
    statement = filing.statement(short_name)
    return [r for r in statement.rows if not r.is_abstract and r.tag and r.is_us_gaap]


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


def test_the_gap_is_concentrated_in_two_statements():
    """The claim the roadmap rests on, asserted rather than asserted-about.

    If most unmapped rows ever stopped being comprehensive income and the
    equity roll-forward, the plan to close the gap by modelling those two would
    no longer be the right plan.
    """
    missing_in_those = missing_total = 0
    for name in OVERALL_FLOORS:
        per_statement, _, _ = measure(name)
        for short_name, (mapped, total) in per_statement.items():
            gap = total - mapped
            missing_total += gap
            if any(
                marker in short_name
                for marker in ("COMPREHENSIVE", "SHAREHOLDERS", "REDEEMABLE NONCON")
            ):
                missing_in_those += gap

    assert missing_total > 0
    share = missing_in_those / missing_total
    assert share >= 0.60, (
        f"only {share:.0%} of unmapped statement lines are in comprehensive "
        f"income and the equity roll-forward; the coverage plan assumes most are"
    )
