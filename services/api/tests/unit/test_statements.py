"""Building a renderable statement from the ledger."""

from __future__ import annotations

from decimal import Decimal

from finagentic.domain.concepts import Concept, Statement
from finagentic.domain.facts import FactStatus
from finagentic.domain.ledger import FactSet
from finagentic.presentation.statements import annual_periods, build_statement, render_text
from finagentic.validation.engine import validate
from tests.conftest import make_fact


def test_lines_render_in_statement_order(clean_filing, fy2024):
    """Declaration order in the concept registry is the reading order."""
    view = build_statement(clean_filing, Statement.INCOME_STATEMENT, [fy2024])
    concepts = [line.concept for line in view.lines]

    assert concepts.index(Concept.REVENUE) < concepts.index(Concept.GROSS_PROFIT)
    assert concepts.index(Concept.GROSS_PROFIT) < concepts.index(Concept.OPERATING_INCOME)
    assert concepts.index(Concept.OPERATING_INCOME) < concepts.index(Concept.NET_INCOME)


def test_components_are_indented_under_their_subtotal(clean_filing, fy2024):
    view = build_statement(clean_filing, Statement.INCOME_STATEMENT, [fy2024])

    rnd = view.line_for(Concept.RESEARCH_AND_DEVELOPMENT)
    total = view.line_for(Concept.TOTAL_OPERATING_EXPENSES)
    assert rnd is not None and total is not None
    assert rnd.indent == 1
    assert total.indent == 0
    assert total.is_subtotal


def test_headline_lines_are_not_indented(clean_filing, fy2024):
    """Revenue heads the statement; it is not a component of anything."""
    view = build_statement(clean_filing, Statement.INCOME_STATEMENT, [fy2024])
    revenue = view.line_for(Concept.REVENUE)
    assert revenue is not None
    assert revenue.indent == 0


def test_unreported_lines_are_omitted_not_blank(clean_filing, fy2024):
    """A blank row implies a zero the company never stated."""
    view = build_statement(clean_filing, Statement.INCOME_STATEMENT, [fy2024])
    assert view.line_for(Concept.OTHER_OPERATING_EXPENSE) is None


def test_a_line_reported_in_only_one_period_still_renders(fy2024, fy2024_instant):
    """Partial coverage across columns must not drop the whole row."""
    facts = FactSet([make_fact(Concept.REVENUE, fy2024, Decimal("10000"))])
    view = build_statement(facts, Statement.INCOME_STATEMENT, [fy2024])

    line = view.line_for(Concept.REVENUE)
    assert line is not None
    assert set(line.cells) == {fy2024.label}


def test_periods_are_ordered_oldest_first(clean_filing, fy2024):
    prior = fy2024.prior_year()
    facts = FactSet(
        [*clean_filing, make_fact(Concept.REVENUE, prior, Decimal("9000"))]
    )
    view = build_statement(facts, Statement.INCOME_STATEMENT, [fy2024, prior])
    assert view.period_labels == (prior.label, fy2024.label)


def test_cells_carry_verification_status(clean_filing, fy2024):
    verified, _ = validate(clean_filing)
    view = build_statement(verified, Statement.INCOME_STATEMENT, [fy2024])

    revenue = view.line_for(Concept.REVENUE)
    assert revenue is not None
    assert revenue.cells[fy2024.label].status is FactStatus.VERIFIED
    assert revenue.cells[fy2024.label].is_verified


def test_unverified_values_are_shown_and_marked(fy2024):
    """Hiding an unverified figure would conceal a gap; showing it unmarked
    would overstate what we know. It is rendered, and flagged."""
    facts = FactSet([make_fact(Concept.REVENUE, fy2024, Decimal("10000"))])
    verified, _ = validate(facts)
    view = build_statement(verified, Statement.INCOME_STATEMENT, [fy2024])

    line = view.line_for(Concept.REVENUE)
    assert line is not None
    assert not line.cells[fy2024.label].is_verified
    assert "?" in render_text(view)


def test_unverified_values_can_be_excluded_on_request(fy2024):
    facts = FactSet([make_fact(Concept.REVENUE, fy2024, Decimal("10000"))])
    view = build_statement(
        facts, Statement.INCOME_STATEMENT, [fy2024], include_unverified=False
    )
    assert view.lines == ()


def test_verified_ratio_reports_statement_confidence(clean_filing, fy2024):
    verified, _ = validate(clean_filing)
    view = build_statement(verified, Statement.INCOME_STATEMENT, [fy2024])
    assert 0.0 < view.verified_ratio <= 1.0


def test_cells_carry_a_source_label_for_auditing(clean_filing, fy2024):
    """A reader must be able to check the mapping without leaving the statement."""
    view = build_statement(clean_filing, Statement.INCOME_STATEMENT, [fy2024])
    revenue = view.line_for(Concept.REVENUE)
    assert revenue is not None
    assert revenue.cells[fy2024.label].source_label


def test_the_balance_sheet_uses_instants(clean_filing, fy2024_instant):
    view = build_statement(clean_filing, Statement.BALANCE_SHEET, [fy2024_instant])
    assert view.line_for(Concept.TOTAL_ASSETS) is not None
    assert view.line_for(Concept.REVENUE) is None


def test_annual_periods_picks_instants_for_the_balance_sheet(clean_filing):
    """"FY2024" means a different thing on a balance sheet than on an income
    statement, so the period kind follows from the statement."""
    bs = annual_periods(clean_filing, Statement.BALANCE_SHEET)
    is_ = annual_periods(clean_filing, Statement.INCOME_STATEMENT)

    assert bs and is_
    assert all(p.kind.value == "instant" for p in bs)
    assert all(p.kind.value == "duration" for p in is_)


def test_annual_periods_returns_the_most_recent_first_limit(clean_filing, fy2024):
    older = [fy2024.prior_year()]
    facts = FactSet(
        [*clean_filing, *(make_fact(Concept.REVENUE, p, Decimal("9000")) for p in older)]
    )
    picked = annual_periods(facts, Statement.INCOME_STATEMENT, limit=1)
    assert len(picked) == 1
    assert picked[0].end_date == fy2024.end_date


def test_an_empty_ledger_renders_an_empty_view(fy2024):
    view = build_statement(FactSet(), Statement.INCOME_STATEMENT, [fy2024])
    assert view.lines == ()
    assert view.verified_ratio == 0.0


def test_render_text_includes_every_period_column(clean_filing, fy2024):
    view = build_statement(clean_filing, Statement.INCOME_STATEMENT, [fy2024])
    assert fy2024.label in render_text(view)
