"""Every check must catch the error it exists to catch, and stay quiet otherwise.

Each test perturbs exactly one value in an otherwise perfect filing and asserts
that the *specific* responsible check fails. A check that fires on the clean
fixture is a false positive; a check that stays silent on a perturbed fixture is
a false negative. Both are tested.
"""

from __future__ import annotations

from decimal import Decimal

from finagentic.domain.concepts import Concept
from finagentic.domain.facts import SCALE_MILLIONS
from finagentic.domain.ledger import FactSet
from finagentic.domain.periods import Period
from finagentic.validation.engine import run_checks, validate
from finagentic.validation.identities import ALL_CHECKS
from finagentic.validation.results import CheckStatus, Severity
from tests.conftest import make_fact


def _replace_value(
    facts: FactSet, concept: Concept, period: Period, new_raw: Decimal | str
) -> FactSet:
    """Return the ledger with one concept's value swapped out.

    The original fact's reporting scale is preserved -- rebuilding at a default
    scale would silently change the magnitude by orders of magnitude and make
    the perturbation test meaningless.
    """
    original = facts.get(concept, period)
    scale = original.scale if original is not None else SCALE_MILLIONS
    kept = [f for f in facts if not (f.concept is concept and f.period.key == period.key)]
    return FactSet([*kept, make_fact(concept, period, Decimal(str(new_raw)), scale=scale)])


def _result(report, check_id: str):
    matches = [r for r in report.results if r.check_id == check_id]
    assert matches, f"check {check_id!r} did not run; ran: {sorted({r.check_id for r in report.results})}"
    return matches


def _statuses(report, check_id: str) -> set[CheckStatus]:
    return {r.status for r in _result(report, check_id)}


# ---------------------------------------------------------------------------
# the clean filing must be completely clean
# ---------------------------------------------------------------------------


def test_clean_filing_has_no_failures(clean_filing):
    report = run_checks(clean_filing)
    assert report.failed == (), (
        "clean fixture produced failures: "
        + "; ".join(f"{r.check_id}: {r.message}" for r in report.failed)
    )


def test_clean_filing_is_not_blocking(clean_filing):
    assert run_checks(clean_filing).is_clean


def test_clean_filing_exercises_the_critical_checks(clean_filing):
    """Guard against the fixture silently ceasing to reach the important checks.

    A fixture that skips every check would also produce zero failures, so the
    test above would pass vacuously. This pins the checks that must actually
    evaluate.
    """
    report = run_checks(clean_filing)
    passed_ids = {r.check_id for r in report.passed}
    for required in (
        "bs.balances",
        "bs.le_total",
        "bs.assets_split",
        "bs.current_assets",
        "bs.current_liabilities",
        "is.gross_profit",
        "is.operating_income",
        "is.opex_subtotal",
        "is.net_income",
        "is.eps",
        "cf.rollforward",
        "cf.net_change",
        "xs.cash_tie",
    ):
        assert required in passed_ids, f"{required} did not pass on the clean fixture"


# ---------------------------------------------------------------------------
# balance sheet
# ---------------------------------------------------------------------------


def test_unbalanced_balance_sheet_is_caught(clean_filing, fy2024_instant):
    """Inflating total assets must break the fundamental identity."""
    broken = _replace_value(clean_filing, Concept.TOTAL_ASSETS, fy2024_instant, "14500")
    report = run_checks(broken)

    assert CheckStatus.FAILED in _statuses(report, "bs.balances")
    assert any(r.check_id == "bs.balances" and r.is_blocking for r in report.failed)


def test_unbalanced_balance_sheet_reports_the_delta(clean_filing, fy2024_instant):
    broken = _replace_value(clean_filing, Concept.TOTAL_ASSETS, fy2024_instant, "14500")
    result = next(r for r in run_checks(broken).failed if r.check_id == "bs.balances")

    # Assets were inflated by 500M, so liabilities + equity now falls short.
    assert result.delta == Decimal("-500") * Decimal(10**6)


def test_a_missing_nci_line_is_not_reported_as_an_imbalance(clean_filing, fy2024_instant):
    """An unextracted non-controlling interest must not be blamed on the totals.

    Failing here would mark every correctly-extracted balance sheet figure
    INCONSISTENT because of one line item nobody captured. The honest status is
    "could not confirm", naming the missing input.
    """
    without_nci = FactSet(
        f
        for f in clean_filing
        if f.concept not in (Concept.MINORITY_INTEREST, Concept.TOTAL_EQUITY_INCL_MINORITY)
    )
    broken = _replace_value(without_nci, Concept.TOTAL_ASSETS, fy2024_instant, "14500")
    statuses = _statuses(run_checks(broken), "bs.balances")

    assert CheckStatus.FAILED not in statuses
    assert CheckStatus.SKIPPED in statuses

    result = next(
        r for r in run_checks(broken).results
        if r.check_id == "bs.balances" and r.status is CheckStatus.SKIPPED
    )
    assert Concept.MINORITY_INTEREST.value in result.missing


def test_components_exceeding_their_subtotal_is_a_failure(clean_filing, fy2024_instant):
    """Overshoot is a genuine contradiction: parts cannot exceed their whole."""
    broken = _replace_value(clean_filing, Concept.INVENTORY, fy2024_instant, "900")
    assert CheckStatus.FAILED in _statuses(run_checks(broken), "bs.current_assets")


def test_missing_components_do_not_fabricate_a_subtotal_break(clean_filing):
    """A shortfall means "not all line items extracted", not "the books are wrong".

    Reporting this as a failure would put a fabricated accounting break in front
    of the user on every partially-extracted statement, which is the fastest way
    to make the reconciliation panel worth ignoring.
    """
    sparse = FactSet(f for f in clean_filing if f.concept is not Concept.INVENTORY)
    statuses = _statuses(run_checks(sparse), "bs.current_assets")

    assert CheckStatus.FAILED not in statuses
    assert CheckStatus.SKIPPED in statuses


def test_a_subtotal_shortfall_records_the_unexplained_residual(clean_filing):
    """The gap is retained so the UI can show what is still unaccounted for."""
    sparse = FactSet(f for f in clean_filing if f.concept is not Concept.INVENTORY)
    result = next(
        r for r in run_checks(sparse).results
        if r.check_id == "bs.current_assets" and r.status is CheckStatus.SKIPPED
    )

    # Inventory was 800M, so that much of total current assets is unexplained.
    assert result.delta == Decimal("-800") * Decimal(10**6)
    assert "unexplained" in result.message


def test_current_liabilities_overshoot_is_caught(clean_filing, fy2024_instant):
    broken = _replace_value(clean_filing, Concept.ACCOUNTS_PAYABLE, fy2024_instant, "1500")
    assert CheckStatus.FAILED in _statuses(run_checks(broken), "bs.current_liabilities")


def test_assets_split_break_is_caught(clean_filing, fy2024_instant):
    broken = _replace_value(clean_filing, Concept.TOTAL_NONCURRENT_ASSETS, fy2024_instant, "7000")
    assert CheckStatus.FAILED in _statuses(run_checks(broken), "bs.assets_split")


# ---------------------------------------------------------------------------
# income statement
# ---------------------------------------------------------------------------


def test_gross_profit_break_is_caught(clean_filing, fy2024):
    broken = _replace_value(clean_filing, Concept.COST_OF_REVENUE, fy2024, "4500")
    assert CheckStatus.FAILED in _statuses(run_checks(broken), "is.gross_profit")


def test_operating_income_break_is_caught(clean_filing, fy2024):
    broken = _replace_value(clean_filing, Concept.OPERATING_INCOME, fy2024, "2500")
    assert CheckStatus.FAILED in _statuses(run_checks(broken), "is.operating_income")


def test_net_income_break_is_caught(clean_filing, fy2024):
    broken = _replace_value(clean_filing, Concept.INCOME_TAX_EXPENSE, fy2024, "600")
    assert CheckStatus.FAILED in _statuses(run_checks(broken), "is.net_income")


def test_opex_subtotal_avoids_double_counting_sga(clean_filing, fy2024):
    """S&M + G&A and SG&A are alternative presentations, not additive.

    Adding an SG&A aggregate alongside its components must not be read as
    3,700M of extra spend.
    """
    with_sga = FactSet(
        [*clean_filing, make_fact(Concept.SELLING_GENERAL_ADMIN, fy2024, Decimal("2500"))]
    )
    assert CheckStatus.FAILED not in _statuses(run_checks(with_sga), "is.opex_subtotal")


def test_eps_break_is_caught_but_only_informational(clean_filing, fy2024):
    broken = _replace_value(clean_filing, Concept.EPS_DILUTED, fy2024, "2.40")
    results = [r for r in run_checks(broken).results if r.check_id == "is.eps"]
    failed = [r for r in results if r.status is CheckStatus.FAILED]

    assert failed, "a 50% EPS error should be caught"
    assert all(r.severity is Severity.INFO for r in failed)
    assert not any(r.is_blocking for r in failed)


def test_eps_tolerates_rounding(clean_filing, fy2024):
    """EPS printed to the cent must not fail against figures rounded to millions."""
    nudged = _replace_value(clean_filing, Concept.EPS_DILUTED, fy2024, "1.61")
    assert CheckStatus.FAILED not in _statuses(run_checks(nudged), "is.eps")


# ---------------------------------------------------------------------------
# cash flow and cross-statement
# ---------------------------------------------------------------------------


def test_cash_rollforward_break_is_caught(clean_filing, fy2024):
    broken = _replace_value(clean_filing, Concept.NET_CASH_OPERATING, fy2024, "3500")
    report = run_checks(broken)

    assert CheckStatus.FAILED in _statuses(report, "cf.rollforward")
    assert any(r.check_id == "cf.rollforward" and r.is_blocking for r in report.failed)


def test_net_change_in_cash_break_is_caught(clean_filing, fy2024):
    broken = _replace_value(clean_filing, Concept.NET_CHANGE_IN_CASH, fy2024, "500")
    assert CheckStatus.FAILED in _statuses(run_checks(broken), "cf.net_change")


def test_cash_tie_catches_a_column_offset(clean_filing, fy2024_instant):
    """The cross-statement tie is what catches reading the wrong year's column."""
    broken = _replace_value(clean_filing, Concept.CASH_AND_EQUIVALENTS, fy2024_instant, "2150")
    report = run_checks(broken)

    assert CheckStatus.FAILED in _statuses(report, "xs.cash_tie")
    assert any(r.check_id == "xs.cash_tie" and r.is_blocking for r in report.failed)


# ---------------------------------------------------------------------------
# structural
# ---------------------------------------------------------------------------


def test_conflicting_duplicate_values_are_caught(clean_filing, fy2024):
    conflicted = FactSet([*clean_filing, make_fact(Concept.NET_INCOME, fy2024, Decimal("1700"))])
    report = run_checks(conflicted)

    assert CheckStatus.FAILED in _statuses(report, "struct.no_duplicates")
    assert CheckStatus.FAILED in _statuses(report, "xs.net_income_tie")


def test_identical_duplicates_are_not_a_conflict(clean_filing, fy2024):
    """The same figure appearing on two statements is agreement, not conflict."""
    duplicated = FactSet([*clean_filing, make_fact(Concept.NET_INCOME, fy2024, Decimal("1600"))])
    assert CheckStatus.FAILED not in _statuses(
        run_checks(duplicated), "struct.no_duplicates"
    )


# ---------------------------------------------------------------------------
# skip behaviour: absence of evidence is not evidence of a break
# ---------------------------------------------------------------------------


#: Filers commonly tag no total `Liabilities` line at all, running current
#: liabilities, then non-current, then straight into equity.
_LIABILITY_TOTALS = (
    Concept.TOTAL_LIABILITIES,
    Concept.TOTAL_CURRENT_LIABILITIES,
    Concept.TOTAL_NONCURRENT_LIABILITIES,
)


def test_a_missing_liabilities_total_is_recovered_from_its_halves(clean_filing):
    """Current + non-current liabilities reconstructs the total exactly.

    Skipping instead would abandon the balance sheet check for the many filers
    that never tag a `Liabilities` line.
    """
    sparse = FactSet(f for f in clean_filing if f.concept is not Concept.TOTAL_LIABILITIES)
    statuses = _statuses(run_checks(sparse), "bs.balances")

    assert CheckStatus.PASSED in statuses
    assert CheckStatus.FAILED not in statuses


def test_an_imbalance_is_still_caught_via_the_liability_halves(clean_filing, fy2024_instant):
    """The fallback must not become a way for a real break to slip through."""
    sparse = FactSet(f for f in clean_filing if f.concept is not Concept.TOTAL_LIABILITIES)
    broken = _replace_value(sparse, Concept.TOTAL_ASSETS, fy2024_instant, "14500")
    assert CheckStatus.FAILED in _statuses(run_checks(broken), "bs.balances")


def test_missing_inputs_skip_rather_than_fail(clean_filing):
    """With no liabilities figure of any kind, the check cannot be evaluated."""
    sparse = FactSet(f for f in clean_filing if f.concept not in _LIABILITY_TOTALS)
    report = run_checks(sparse)

    assert CheckStatus.SKIPPED in _statuses(report, "bs.balances")
    assert CheckStatus.FAILED not in _statuses(report, "bs.balances")


def test_skipped_checks_name_what_is_missing(clean_filing):
    sparse = FactSet(f for f in clean_filing if f.concept not in _LIABILITY_TOTALS)
    result = next(
        r for r in run_checks(sparse).results
        if r.check_id == "bs.balances" and r.status is CheckStatus.SKIPPED
    )
    assert Concept.TOTAL_LIABILITIES.value in result.missing


def test_total_assets_tie_to_liabilities_and_equity(clean_filing):
    """The cheapest corroboration on the balance sheet; both lines are printed."""
    assert CheckStatus.PASSED in _statuses(run_checks(clean_filing), "bs.assets_tie")


def test_a_broken_assets_tie_is_caught(clean_filing, fy2024_instant):
    broken = _replace_value(
        clean_filing, Concept.TOTAL_LIABILITIES_AND_EQUITY, fy2024_instant, "14500"
    )
    assert CheckStatus.FAILED in _statuses(run_checks(broken), "bs.assets_tie")


def test_an_empty_ledger_produces_no_results():
    assert run_checks(FactSet()).results == ()


def test_every_registered_check_emits_a_result_for_some_input(
    clean_filing, two_year_filing, fy2024
):
    """No check may be dead code.

    Each registered check must produce a result on at least one of the inputs
    below. A check that never fires -- because its concepts are misspelled or
    its period guard is inverted -- would otherwise sit in the registry looking
    like protection the system does not actually have.
    """
    quarterly = _quarterly_filing()
    with_conflict = FactSet([*clean_filing, make_fact(Concept.NET_INCOME, fy2024, Decimal("1700"))])

    ran: set[str] = set()
    for ledger in (clean_filing, two_year_filing, quarterly, with_conflict):
        ran |= {r.check_id for r in run_checks(ledger).results}

    registered = {
        "struct.no_duplicates", "bs.balances", "bs.le_total", "bs.assets_split",
        "bs.current_assets", "bs.current_liabilities", "is.gross_profit",
        "is.opex_subtotal", "is.operating_income", "is.net_income", "is.eps",
        "cf.rollforward", "cf.net_change", "xs.cash_tie", "xs.net_income_tie",
        "period.arithmetic", "bs.assets_tie",
        "ci.total", "ci.components", "eq.rollforward",
    }
    assert len(registered) == len(ALL_CHECKS), (
        "ALL_CHECKS changed; update the expected check-id set in this test"
    )
    assert registered - ran == set(), f"checks never fired: {sorted(registered - ran)}"


def _quarterly_filing() -> FactSet:
    """Four quarters plus a full year, so period arithmetic has something to check."""
    from datetime import date

    from finagentic.domain.concepts import PeriodKind
    from finagentic.domain.periods import FiscalPeriod

    spans = {
        FiscalPeriod.Q1: (date(2024, 1, 1), date(2024, 3, 31), "2000"),
        FiscalPeriod.Q2: (date(2024, 4, 1), date(2024, 6, 30), "2400"),
        FiscalPeriod.Q3: (date(2024, 7, 1), date(2024, 9, 30), "2600"),
        FiscalPeriod.Q4: (date(2024, 10, 1), date(2024, 12, 31), "3000"),
        FiscalPeriod.FY: (date(2024, 1, 1), date(2024, 12, 31), "10000"),
    }
    facts = []
    for fp, (start, end, revenue) in spans.items():
        period = Period(
            kind=PeriodKind.DURATION,
            fiscal_year=2024,
            fiscal_period=fp,
            start_date=start,
            end_date=end,
        )
        facts.append(make_fact(Concept.REVENUE, period, Decimal(revenue)))
    return FactSet(facts)


def test_quarters_summing_to_the_year_pass_period_arithmetic():
    assert CheckStatus.FAILED not in _statuses(
        run_checks(_quarterly_filing()), "period.arithmetic"
    )


def test_a_quarter_inconsistent_with_the_year_is_caught():
    """2,000 + 2,400 + 2,600 + 3,000 = 10,000; breaking one quarter must show."""
    from datetime import date

    from finagentic.domain.concepts import PeriodKind
    from finagentic.domain.periods import FiscalPeriod

    q4 = Period(
        kind=PeriodKind.DURATION,
        fiscal_year=2024,
        fiscal_period=FiscalPeriod.Q4,
        start_date=date(2024, 10, 1),
        end_date=date(2024, 12, 31),
    )
    broken = _replace_value(_quarterly_filing(), Concept.REVENUE, q4, "3500")
    assert CheckStatus.FAILED in _statuses(run_checks(broken), "period.arithmetic")


# ---------------------------------------------------------------------------
# status promotion
# ---------------------------------------------------------------------------


def test_validate_marks_corroborated_facts_verified(clean_filing):
    verified, report = validate(clean_filing)
    assert report.is_clean
    assert len(verified.usable()) > 0


def test_facts_in_a_broken_identity_are_not_verified(clean_filing, fy2024_instant):
    broken = _replace_value(clean_filing, Concept.TOTAL_ASSETS, fy2024_instant, "14500")
    verified, _ = validate(broken)

    total_assets = verified.get(Concept.TOTAL_ASSETS, fy2024_instant)
    assert total_assets is not None
    assert not total_assets.is_usable, "a fact in a failing identity must not be usable"


def test_an_uncorroborated_fact_stays_unverified(fy2024_instant):
    """A lone number no identity can reach is never promoted to VERIFIED.

    This is the anti-hallucination guarantee: a fabricated figure with no
    supporting arithmetic cannot become quotable.
    """
    lone = FactSet([make_fact(Concept.GOODWILL, fy2024_instant, Decimal("9999"))])
    verified, _ = validate(lone)

    fact = verified.get(Concept.GOODWILL, fy2024_instant)
    assert fact is not None
    assert not fact.is_usable
    assert len(verified.usable()) == 0


# ---------------------------------------------------------------------------
# mezzanine (temporary) equity
# ---------------------------------------------------------------------------


def test_a_filer_with_no_mezzanine_is_unaffected(clean_filing):
    """Most companies have no redeemable instruments, and zero is the answer."""
    report = run_checks(clean_filing)
    assert _statuses(report, "bs.balances") == {CheckStatus.PASSED}
    assert _statuses(report, "bs.le_total") == {CheckStatus.PASSED}


def test_the_balance_sheet_balances_once_the_mezzanine_is_counted(
    clean_filing, fy2024_instant
):
    """Assets = Liabilities + Temporary equity + Equity.

    Redeemable instruments are neither a liability nor equity and sit on their
    own line between the two. Leaving the term out failed by exactly their
    carrying amount -- 92 of Tesla's 113 breaks were this and nothing else.
    """
    # Assets grow by the mezzanine, which is where a real filer's would be.
    with_mezzanine = _replace_value(
        clean_filing, Concept.TOTAL_ASSETS, fy2024_instant, "14500"
    )
    with_mezzanine = FactSet(
        [
            *with_mezzanine,
            make_fact(Concept.TEMPORARY_EQUITY, fy2024_instant, Decimal("500")),
        ]
    )

    report = run_checks(with_mezzanine)
    assert _statuses(report, "bs.balances") == {CheckStatus.PASSED}


def test_the_mezzanine_is_summed_when_only_its_parts_are_tagged(
    clean_filing, fy2024_instant
):
    """Tesla tags redeemable NCI and the parent portion, never the total."""
    facts = _replace_value(clean_filing, Concept.TOTAL_ASSETS, fy2024_instant, "14500")
    facts = FactSet(
        [
            *facts,
            make_fact(
                Concept.REDEEMABLE_NONCONTROLLING_INTEREST,
                fy2024_instant,
                Decimal("400"),
            ),
            make_fact(Concept.TEMPORARY_EQUITY_PARENT, fy2024_instant, Decimal("100")),
        ]
    )

    report = run_checks(facts)
    assert _statuses(report, "bs.balances") == {CheckStatus.PASSED}


def test_a_tagged_total_wins_over_its_parts(clean_filing, fy2024_instant):
    """Filers report both. Adding a part to a total that contains it would
    double-count and turn a balanced sheet into a fabricated break."""
    facts = _replace_value(clean_filing, Concept.TOTAL_ASSETS, fy2024_instant, "14500")
    facts = FactSet(
        [
            *facts,
            make_fact(Concept.TEMPORARY_EQUITY, fy2024_instant, Decimal("500")),
            make_fact(
                Concept.REDEEMABLE_NONCONTROLLING_INTEREST,
                fy2024_instant,
                Decimal("400"),
            ),
            make_fact(Concept.TEMPORARY_EQUITY_PARENT, fy2024_instant, Decimal("100")),
        ]
    )

    report = run_checks(facts)
    assert _statuses(report, "bs.balances") == {CheckStatus.PASSED}


def test_a_genuinely_unbalanced_sheet_still_fails(clean_filing, fy2024_instant):
    """The term must not become an excuse that absorbs real breaks."""
    facts = _replace_value(clean_filing, Concept.TOTAL_ASSETS, fy2024_instant, "14500")
    facts = FactSet(
        [*facts, make_fact(Concept.TEMPORARY_EQUITY, fy2024_instant, Decimal("50"))]
    )

    report = run_checks(facts)
    assert CheckStatus.FAILED in _statuses(report, "bs.balances")


def test_the_printed_total_also_counts_the_mezzanine(clean_filing, fy2024_instant):
    """`Total liabilities and equity` includes the mezzanine on the face of the
    statement, so the check that ties it to its parts must include it too."""
    facts = _replace_value(
        clean_filing, Concept.TOTAL_LIABILITIES_AND_EQUITY, fy2024_instant, "14500"
    )
    facts = _replace_value(facts, Concept.TOTAL_ASSETS, fy2024_instant, "14500")
    facts = FactSet(
        [*facts, make_fact(Concept.TEMPORARY_EQUITY, fy2024_instant, Decimal("500"))]
    )

    report = run_checks(facts)
    assert _statuses(report, "bs.le_total") == {CheckStatus.PASSED}


# ---------------------------------------------------------------------------
# comprehensive income and the equity roll-forward
# ---------------------------------------------------------------------------


def test_comprehensive_income_ties_the_two_statements_together(clean_filing):
    """1,600 of net income plus 50 of OCI is 1,650 of comprehensive income.

    The first identity spanning two statements: neither the income statement
    nor the comprehensive income statement can establish it alone.
    """
    assert _statuses(run_checks(clean_filing), "ci.total") == {CheckStatus.PASSED}


def test_a_wrong_comprehensive_income_is_caught(clean_filing, fy2024):
    broken = _replace_value(clean_filing, Concept.COMPREHENSIVE_INCOME, fy2024, "1700")
    assert CheckStatus.FAILED in _statuses(run_checks(broken), "ci.total")


def test_a_wrong_oci_total_breaks_comprehensive_income(clean_filing, fy2024):
    """The OCI total feeds two checks, so an error in it surfaces twice."""
    broken = _replace_value(clean_filing, Concept.OTHER_COMPREHENSIVE_INCOME, fy2024, "120")
    statuses = _statuses(run_checks(broken), "ci.total")
    assert CheckStatus.FAILED in statuses


def test_oci_categories_sum_to_their_total(clean_filing):
    assert _statuses(run_checks(clean_filing), "ci.components") == {CheckStatus.PASSED}


def test_an_oci_residual_is_reported_without_being_called_a_break(clean_filing, fy2024):
    """This check reports; it does not adjudicate.

    US GAAP's list of OCI categories is open -- pension adjustments, equity
    method investee share, others besides the four carried here -- so a
    residual is the size of what is unmodelled, not evidence that a filer's
    arithmetic is wrong. Coca-Cola reported 21 breaks on this check for no
    better reason than having a pension scheme.

    What the check is worth is the number in `delta`, which is why that is
    asserted rather than the status alone.
    """
    broken = _replace_value(clean_filing, Concept.OCI_FOREIGN_CURRENCY, fy2024, "90")
    statuses = _statuses(run_checks(broken), "ci.components")
    assert statuses == {CheckStatus.SKIPPED}

    result = _result(run_checks(broken), "ci.components")[0]
    assert result.delta == Decimal("50") * 10**6
    assert "unaccounted for" in result.message


def test_a_missing_oci_category_is_not_a_break(clean_filing, fy2024):
    """OCI categories are signed, unlike assets or expenses.

    Dropping a negative one makes the rest sum *higher* than the total, which
    a subtotal check reading overshoot-as-contradiction would report as an
    accounting break. It is incomplete extraction, and must read as one.
    """
    without = FactSet(
        [
            f
            for f in clean_filing
            if not (f.concept is Concept.OCI_DERIVATIVES and f.period.key == fy2024.key)
        ]
    )
    statuses = _statuses(run_checks(without), "ci.components")
    assert CheckStatus.FAILED not in statuses

    result = _result(run_checks(without), "ci.components")[0]
    assert "OtherComprehensiveIncomeLossCashFlowHedgeGainLoss" in " ".join(result.missing)


def test_the_equity_rollforward_closes(two_year_filing):
    """5,400 + 1,600 + 50 + 200 + 150 - 900 - 400 - 100 = 6,000.

    The widest identity in the system: two balance sheets, the income
    statement and the comprehensive income statement, all at once.
    """
    assert _statuses(run_checks(two_year_filing), "eq.rollforward") == {CheckStatus.PASSED}


def test_the_rollforward_catches_an_error_in_any_of_its_inputs(two_year_filing, fy2024):
    """Its reach is the point. A wrong number anywhere it touches breaks it,
    including in periods and statements the other checks never compare."""
    for concept, wrong in [
        (Concept.NET_INCOME, "1900"),
        (Concept.OTHER_COMPREHENSIVE_INCOME, "400"),
        (Concept.STOCK_REPURCHASED, "1500"),
        (Concept.DIVIDENDS_DECLARED, "50"),
        (Concept.STOCK_ISSUED, "900"),
    ]:
        broken = _replace_value(two_year_filing, concept, fy2024, wrong)
        assert CheckStatus.FAILED in _statuses(run_checks(broken), "eq.rollforward"), (
            f"a wrong {concept.value} did not break the roll-forward"
        )


def test_a_wrong_closing_equity_breaks_the_rollforward(two_year_filing, fy2024_instant):
    broken = _replace_value(
        two_year_filing, Concept.TOTAL_STOCKHOLDERS_EQUITY, fy2024_instant, "6500"
    )
    assert CheckStatus.FAILED in _statuses(run_checks(broken), "eq.rollforward")


def test_a_movement_we_do_not_model_is_reported_as_unexplained(two_year_filing, fy2024):
    """Filers move equity in ways this does not model -- conversions,
    spin-offs, adopting a new standard. Those are events, not errors, so a
    difference alongside a missing movement is not asserted as a break."""
    without = FactSet(
        [
            f
            for f in two_year_filing
            if not (f.concept is Concept.DIVIDENDS_DECLARED and f.period.key == fy2024.key)
        ]
    )
    statuses = _statuses(run_checks(without), "eq.rollforward")
    assert CheckStatus.FAILED not in statuses


def test_the_rollforward_will_not_run_on_net_income_alone(clean_filing, fy2023_instant):
    """Equity did not change by earnings: every dividend-paying company would
    report a break. Without a second movement the check declines to run."""
    thin = FactSet(
        [
            f
            for f in clean_filing
            if f.concept
            not in {
                Concept.STOCK_ISSUED,
                Concept.STOCK_REPURCHASED,
                Concept.SHARE_BASED_COMP_EQUITY,
                Concept.DIVIDENDS_DECLARED,
                Concept.TAX_WITHHOLDING_SHARE_BASED,
                Concept.OTHER_COMPREHENSIVE_INCOME,
            }
        ]
        + [make_fact(Concept.TOTAL_STOCKHOLDERS_EQUITY, fy2023_instant, Decimal("5400"))]
    )
    assert _statuses(run_checks(thin), "eq.rollforward") == {CheckStatus.SKIPPED}


def test_the_rollforward_is_a_warning_not_a_critical(two_year_filing):
    """A break means "something moved equity we did not account for", which is
    a weaker claim than "these numbers contradict each other"."""
    result = _result(run_checks(two_year_filing), "eq.rollforward")[0]
    assert result.severity is Severity.WARNING
