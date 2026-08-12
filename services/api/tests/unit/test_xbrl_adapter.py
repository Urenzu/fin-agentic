"""Adapter behaviour on EDGAR-shaped input.

These use hand-built observations rather than live data so they are fast,
offline and deterministic. The cases are drawn from real filings -- each one
here is a bug that reached the ledger before being caught.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from finagentic.domain.concepts import Concept, PeriodKind
from finagentic.domain.periods import FiscalPeriod
from finagentic.ingest.edgar import Registrant, XbrlObservation
from finagentic.ingest.tag_map import TAG_PRECEDENCE, TAG_TO_CONCEPT, concept_for, tag_rank
from finagentic.ingest.xbrl_adapter import AdaptationReport, infer_period, to_facts

REGISTRANT = Registrant(cik=320193, ticker="AAPL", name="Apple Inc.")


def obs(
    tag: str,
    *,
    end: str,
    start: str | None = None,
    value: str = "100",
    fy: int | None = 2024,
    fp: str | None = "FY",
    form: str = "10-K",
    filed: str = "2024-11-01",
    accession: str = "0000320193-24-000123",
    unit: str = "USD",
    frame: str | None = "CY2024",
) -> XbrlObservation:
    return XbrlObservation(
        tag=tag,
        unit=unit,
        value=Decimal(value),
        end=date.fromisoformat(end),
        start=date.fromisoformat(start) if start else None,
        fiscal_year=fy,
        fiscal_period=fp,
        form=form,
        accession=accession,
        filed=date.fromisoformat(filed),
        frame=frame,
    )


# ---------------------------------------------------------------------------
# period inference
# ---------------------------------------------------------------------------


def test_an_annual_span_is_recognised():
    period = infer_period(obs("Revenues", start="2023-10-01", end="2024-09-28"))
    assert period is not None
    assert period.kind is PeriodKind.DURATION
    assert period.fiscal_period is FiscalPeriod.FY


def test_a_quarter_uses_the_filing_label():
    period = infer_period(obs("Revenues", start="2024-04-01", end="2024-06-29", fp="Q3"))
    assert period is not None
    assert period.fiscal_period is FiscalPeriod.Q3


def test_a_quarterly_span_labelled_fy_is_the_fourth_quarter():
    """A three-month span in an annual filing is Q4, not a fiscal year."""
    period = infer_period(obs("Revenues", start="2024-07-01", end="2024-09-28", fp="FY"))
    assert period is not None
    assert period.fiscal_period is FiscalPeriod.Q4


def test_an_unlabelled_quarter_is_left_unplaced():
    """Which quarter a three-month span belongs to cannot be read off dates.

    Guessing would silently file Q2 revenue under Q1.
    """
    assert infer_period(obs("Revenues", start="2024-04-01", end="2024-06-29", fp=None)) is None


def test_a_53_week_year_is_accepted():
    period = infer_period(obs("Revenues", start="2017-10-01", end="2018-09-29"))
    assert period is not None
    assert period.fiscal_period is FiscalPeriod.FY


def test_an_instant_has_no_span():
    period = infer_period(obs("Assets", end="2024-09-28"))
    assert period is not None
    assert period.kind is PeriodKind.INSTANT
    assert period.start_date is None


def test_comparative_balance_sheets_do_not_collide():
    """A 10-K reports two balance sheet dates, both tagged with the filing's year.

    EDGAR's `fy` describes the filing, not the value, so the prior-year
    comparative arrives as fy=2024 with a 2023 date. Keying on the label would
    merge two distinct balance sheets into one slot, where they then look like
    contradictory values for the same date.
    """
    current = infer_period(obs("Assets", end="2024-09-28", fy=2024))
    prior = infer_period(obs("Assets", end="2023-09-30", fy=2024))

    assert current is not None and prior is not None
    assert current.key != prior.key


# ---------------------------------------------------------------------------
# filtering
# ---------------------------------------------------------------------------


def test_dimensional_rows_are_dropped():
    """Segment breakouts carry no frame and would double-count against totals."""
    facts, report = to_facts(
        [
            obs("Assets", end="2024-09-28", value="1000", frame="CY2024Q3I"),
            obs("Assets", end="2024-09-28", value="400", frame=None),
        ],
        REGISTRANT,
    )
    assert report.skipped_dimensional == 1
    assert len(facts) == 1


def test_earnings_releases_are_excluded():
    """8-K figures are preliminary and routinely revised in the next 10-Q."""
    _, report = to_facts([obs("Assets", end="2024-09-28", form="8-K")], REGISTRANT)
    assert report.skipped_form == 1
    assert report.accepted == 0


def test_unmapped_tags_are_counted_not_dropped_silently():
    _, report = to_facts([obs("SomeExoticFootnoteTag", end="2024-09-28")], REGISTRANT)
    assert report.skipped_unmapped_tag == 1


def test_a_unit_mismatch_is_rejected():
    """A per-share unit on a dollar concept is a tagging error, not a rounding one."""
    _, report = to_facts(
        [obs("Assets", end="2024-09-28", unit="USD/shares")], REGISTRANT
    )
    assert report.skipped_unsupported_unit == 1


# ---------------------------------------------------------------------------
# restatement and tag precedence
# ---------------------------------------------------------------------------


def test_the_most_recently_filed_value_wins():
    """A restatement supersedes the original figure for the same period."""
    facts, report = to_facts(
        [
            obs("Assets", end="2023-09-30", value="352583", filed="2023-11-03",
                accession="0000320193-23-000106"),
            obs("Assets", end="2023-09-30", value="352999", filed="2024-11-01",
                accession="0000320193-24-000123"),
        ],
        REGISTRANT,
    )
    period = facts.periods()[0]
    fact = facts.get(Concept.TOTAL_ASSETS, period)

    assert fact is not None
    assert fact.raw_value == Decimal("352999")
    assert report.superseded_by_restatement == 1


def test_identical_repeats_are_not_counted_as_restatements():
    """The same figure repeated as a comparative is agreement, not revision."""
    _, report = to_facts(
        [
            obs("Assets", end="2023-09-30", value="352583", filed="2023-11-03"),
            obs("Assets", end="2023-09-30", value="352583", filed="2024-02-02",
                accession="0000320193-24-000006"),
        ],
        REGISTRANT,
    )
    assert report.superseded_by_restatement == 0


def test_the_preferred_tag_wins_over_a_legacy_alias():
    """A filing emitting both a current and a superseded revenue tag means the
    current one; taking the legacy tag would break the series at the changeover."""
    facts, _ = to_facts(
        [
            obs("Revenues", start="2023-10-01", end="2024-09-28", value="1"),
            obs(
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                start="2023-10-01",
                end="2024-09-28",
                value="391035",
            ),
        ],
        REGISTRANT,
    )
    period = facts.periods()[0]
    fact = facts.get(Concept.REVENUE, period)

    assert fact is not None
    assert fact.raw_value == Decimal("391035")


# ---------------------------------------------------------------------------
# truncated history
# ---------------------------------------------------------------------------


def test_a_thin_ledger_is_flagged_as_truncated():
    """A ticker resolves to whichever CIK currently holds it.

    After a reorganisation that is the new holding company, whose history starts
    at the reorganisation -- XOM returns months of data while decades of Exxon
    Mobil filings sit under the predecessor CIK. Rendering that without a
    warning is the failure this system exists to prevent.
    """
    report = AdaptationReport(
        accepted=66,
        earliest=date(2024, 12, 31),
        latest=date(2026, 6, 30),
        annual_reports=0,
    )
    assert report.looks_truncated
    assert "TRUNCATED" in report.summary()


def test_a_full_history_is_not_flagged():
    report = AdaptationReport(
        accepted=2770,
        earliest=date(2006, 12, 31),
        latest=date(2026, 3, 31),
        annual_reports=17,
    )
    assert not report.looks_truncated
    assert "TRUNCATED" not in report.summary()


def test_a_ledger_with_no_annual_report_is_flagged_however_long():
    """Quarterly-only coverage cannot support annual analysis."""
    report = AdaptationReport(
        accepted=500,
        earliest=date(2010, 1, 1),
        latest=date(2024, 1, 1),
        annual_reports=0,
    )
    assert report.looks_truncated


# ---------------------------------------------------------------------------
# tag map integrity
# ---------------------------------------------------------------------------


def test_profit_loss_is_not_aliased_to_net_income():
    """ProfitLoss includes the non-controlling interest share; NetIncomeLoss does
    not. Aliasing them reported a break on every period for any company with
    consolidated subsidiaries it does not wholly own."""
    assert concept_for("NetIncomeLoss") is Concept.NET_INCOME
    assert concept_for("ProfitLoss") is Concept.NET_INCOME_INCLUDING_NCI


def test_costs_and_expenses_is_not_the_operating_expense_subtotal():
    """CostsAndExpenses includes cost of revenue, so subtracting it from gross
    profit double-counts COGS."""
    assert concept_for("CostsAndExpenses") is None


def test_every_precedence_entry_is_mapped_to_its_own_concept():
    for concept, ranked in TAG_PRECEDENCE.items():
        for tag in ranked:
            assert TAG_TO_CONCEPT.get(tag) is concept, f"{tag} misfiled under {concept}"


def test_unranked_tags_never_outrank_preferred_ones():
    preferred = TAG_PRECEDENCE[Concept.REVENUE][0]
    assert tag_rank(Concept.REVENUE, preferred) < tag_rank(Concept.REVENUE, "SomeOtherTag")
