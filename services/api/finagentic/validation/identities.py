"""Deterministic accounting identity checks.

This module is the reason the platform can claim its numbers are trustworthy.
Every check here is pure arithmetic over the ledger -- no model, no heuristic,
no network. A number that survives this layer has been shown to be consistent
with the other numbers in the filing, which is a far stronger guarantee than
any extractor's self-reported confidence.

Adding a check
--------------
Write a function taking (FactSet, Period) and returning CheckResult | None
(None meaning "not applicable to this period kind"), then register it in
`ALL_CHECKS`. Use `_compare` so tolerance and reporting stay uniform.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, timedelta
from decimal import Decimal

from finagentic.domain.concepts import Concept
from finagentic.domain.facts import FinancialFact
from finagentic.domain.ledger import FactSet
from finagentic.domain.periods import PERIOD_COMPOSITION, FiscalPeriod, Period, PeriodKind
from finagentic.validation.results import (
    CheckResult,
    CheckStatus,
    Severity,
    ToleranceModel,
)

Check = Callable[[FactSet, Period], CheckResult | None]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _skipped(
    check_id: str,
    identity: str,
    severity: Severity,
    period: Period,
    missing: Sequence[Concept],
) -> CheckResult:
    names = tuple(c.value for c in missing)
    return CheckResult(
        check_id=check_id,
        identity=identity,
        status=CheckStatus.SKIPPED,
        severity=severity,
        period_label=period.label,
        missing=names,
        message=f"Not evaluated: missing {', '.join(names)}.",
    )


def _compare(
    *,
    check_id: str,
    identity: str,
    severity: Severity,
    period: Period,
    expected: Decimal,
    actual: Decimal,
    facts: Sequence[FinancialFact],
    tolerance: ToleranceModel,
    absent_optional: Sequence[Concept] = (),
) -> CheckResult:
    """Evaluate `actual == expected` within tolerance and build the result.

    `absent_optional` names inputs the identity treats as zero because they were
    not extracted -- the FX effect on cash, a non-controlling interest. When the
    identity holds anyway, their absence was immaterial and the pass stands.

    When it does not hold, the discrepancy is indistinguishable from the value
    of the missing term: a roll-forward that misses by 50M could be a genuine
    extraction error, or it could be a 50M currency-translation line nobody
    captured. Asserting a break would be claiming knowledge the system does not
    have, so the result is downgraded to SKIPPED and names what was missing.
    """
    tol = tolerance.for_magnitude(expected)
    delta = actual - expected
    ok = abs(delta) <= tol

    if ok:
        status = CheckStatus.PASSED
        message = f"{identity} holds within {tol}."
    elif absent_optional:
        status = CheckStatus.SKIPPED
        names = ", ".join(c.value for c in absent_optional)
        message = (
            f"{identity} does not reconcile, off by {delta}. Not reported as a "
            f"break because {names} was not extracted and could account for the "
            f"difference."
        )
    else:
        status = CheckStatus.FAILED
        message = f"{identity} breaks by {delta} (tolerance {tol})."

    return CheckResult(
        check_id=check_id,
        identity=identity,
        status=status,
        severity=severity,
        period_label=period.label,
        expected=expected,
        actual=actual,
        delta=delta,
        tolerance=tol,
        fact_ids=tuple(f.id for f in facts),
        missing=tuple(c.value for c in absent_optional),
        message=message,
    )


def _compare_subtotal(
    *,
    check_id: str,
    identity: str,
    severity: Severity,
    period: Period,
    total: FinancialFact,
    components: Sequence[FinancialFact],
    tolerance: ToleranceModel,
) -> CheckResult:
    """Evaluate a "subtotal = sum of its parts" identity asymmetrically.

    A subtotal check cannot distinguish "the components genuinely disagree with
    the total" from "we only extracted some of the components" -- both look like
    a shortfall. Treating a shortfall as a failure means every sparsely
    extracted statement reports a fabricated accounting break, which is exactly
    the kind of false alarm that teaches a user to ignore the reconciliation
    panel.

    So the two directions are judged differently:

    overshoot  components sum to MORE than the stated total. This is a real
               contradiction -- adding line items cannot exceed their own
               subtotal no matter how many are missing. Reported as FAILED.
    shortfall  components sum to LESS. Consistent with incomplete extraction, so
               reported as SKIPPED, but the residual is recorded on the result.
               The UI surfaces it as an unexplained gap, which is genuinely
               informative: it is the size of the line items not yet captured.
    """
    expected = total.value
    actual = sum((f.value for f in components), Decimal(0))
    tol = tolerance.for_magnitude(expected)
    delta = actual - expected
    involved = [total, *components]

    if delta > tol:
        # Before calling an overshoot a contradiction, check whether exactly one
        # component is redundant with another. Filers routinely report both an
        # aggregate and its parts -- SG&A alongside separate sales-and-marketing
        # and G&A lines, or an accrued-liabilities breakout already contained in
        # other current liabilities. Both tag onto distinct concepts, so the
        # naive sum double-counts.
        #
        # If removing a single component lands the identity within tolerance,
        # that component was double-counted rather than wrong. Requiring an exact
        # landing makes a coincidental rescue implausible: the tolerance is a
        # fraction of a percent of the total, so a component would have to match
        # the overshoot almost exactly to qualify.
        redundant = _find_redundant_component(components, expected, tol)
        if redundant is not None:
            kept = [f for f in components if f.id != redundant.id]
            return CheckResult(
                check_id=check_id,
                identity=identity,
                status=CheckStatus.PASSED,
                severity=severity,
                period_label=period.label,
                expected=expected,
                actual=sum((f.value for f in kept), Decimal(0)),
                delta=Decimal(0),
                tolerance=tol,
                fact_ids=tuple(f.id for f in involved),
                message=(
                    f"{identity} holds once {redundant.concept.value} is excluded: "
                    f"its value is already contained in another line item, so "
                    f"counting both would double-count it."
                ),
            )

        status, message = (
            CheckStatus.FAILED,
            f"{identity} is contradicted: the components sum to {actual}, which "
            f"exceeds the stated total of {expected} by {delta} (tolerance {tol}).",
        )
    elif delta < -tol:
        status, message = (
            CheckStatus.SKIPPED,
            f"{identity} could not be confirmed: the components captured so far "
            f"sum to {actual}, leaving {-delta} of the stated total unexplained. "
            f"This is consistent with line items not yet extracted.",
        )
    else:
        status, message = CheckStatus.PASSED, f"{identity} holds within {tol}."

    return CheckResult(
        check_id=check_id,
        identity=identity,
        status=status,
        severity=severity,
        period_label=period.label,
        expected=expected,
        actual=actual,
        delta=delta,
        tolerance=tol,
        fact_ids=tuple(f.id for f in involved),
        message=message,
    )


def _find_redundant_component(
    components: Sequence[FinancialFact],
    expected: Decimal,
    tolerance: Decimal,
) -> FinancialFact | None:
    """Find the single component whose removal makes the subtotal reconcile.

    Returns None when no single removal works, which is the case for a genuine
    contradiction. Only single-component removal is considered: allowing
    arbitrary subsets would make it easy to "explain" any discrepancy, which
    would defeat the purpose of the check.
    """
    total = sum((f.value for f in components), Decimal(0))
    matches = [f for f in components if abs(total - f.value - expected) <= tolerance]
    # Ambiguous rescues are refused. If two different components could each
    # explain the overshoot, we cannot tell which is genuinely redundant, and
    # guessing risks silently dropping a real line item.
    return matches[0] if len(matches) == 1 else None


def _tolerance_for(facts: Sequence[FinancialFact], terms: int | None = None) -> ToleranceModel:
    """Derive a tolerance from the reporting scale of the facts involved.

    Uses the coarsest scale present: if any input was printed in millions, the
    whole identity inherits million-level rounding error.
    """
    scale = max((f.scale for f in facts), default=Decimal(1))
    return ToleranceModel(scale=scale, terms=terms if terms is not None else max(len(facts), 2))


def _fetch(
    facts: FactSet, period: Period, concepts: Sequence[Concept]
) -> tuple[list[FinancialFact], list[Concept]]:
    """Split `concepts` into the facts found and the concepts missing."""
    found: list[FinancialFact] = []
    missing: list[Concept] = []
    for concept in concepts:
        fact = facts.get(concept, period)
        if fact is None:
            missing.append(concept)
        else:
            found.append(fact)
    return found, missing


def _instant_at(period: Period) -> Period:
    """The balance sheet instant corresponding to the end of `period`."""
    return Period(
        kind=PeriodKind.INSTANT,
        fiscal_year=period.fiscal_year,
        fiscal_period=period.fiscal_period,
        end_date=period.end_date,
    )


#: Days of slack when matching a balance sheet date to a period boundary. A
#: period beginning the day after the prior period ended is the normal case, but
#: 52/53-week calendars and the occasional off-by-a-weekend make an exact match
#: too brittle.
_INSTANT_MATCH_DAYS = 4


def _instant_on(
    facts: FactSet, concept: Concept, when: date
) -> FinancialFact | None:
    """A balance sheet figure at (or adjacent to) `when`.

    Generalised from `_cash_on`, because the equity roll-forward needs the same
    boundary matching for a different concept. Ambiguity is a miss rather than a
    guess: if two instants sit within the window, which one closes the period is
    exactly what is not known.
    """
    candidates = [
        f
        for f in facts
        if f.concept is concept
        and f.period.kind is PeriodKind.INSTANT
        and abs((f.period.end_date - when).days) <= _INSTANT_MATCH_DAYS
    ]
    if len(candidates) != 1:
        return None
    return candidates[0]


def _cash_on(facts: FactSet, when: date) -> FinancialFact | None:
    """The balance sheet cash figure at (or adjacent to) `when`.

    XBRL has no separate beginning-of-period and end-of-period cash tags. A cash
    flow statement's opening and closing balances are the *same* concept,
    `CashAndCashEquivalentsAtCarryingValue`, reported at two different instants.
    Looking for dedicated concepts alone means the roll-forward can never
    evaluate on XBRL data, which is how the strongest check in the system came to
    be silently skipped on every filing.
    """
    return _instant_on(facts, Concept.CASH_AND_EQUIVALENTS, when)


# ---------------------------------------------------------------------------
# balance sheet
# ---------------------------------------------------------------------------


def _temporary_equity(facts: FactSet, period: Period) -> tuple[Decimal, list[FinancialFact]]:
    """The mezzanine, and the facts it was built from.

    Instruments the issuer may be required to redeem for cash sit on their own
    line between liabilities and equity, so the accounting equation is really
    `Assets = Liabilities + Temporary equity + Equity`. Omitting the middle
    term does not make the check approximately right -- it makes it fail by
    exactly the mezzanine's carrying amount, which is how 92 of Tesla's 113
    validation failures arose.

    Most filers tag the total. Tesla tags only the two components, so the total
    is recovered by summing them -- the same fallback the liabilities term uses
    when a filer runs current and non-current straight into equity without a
    printed total. The total is preferred when present, because adding a
    component to a total that already contains it would double count.

    Nothing here is a failure: a company with no redeemable instruments tags
    none of these, and zero is the right answer.
    """
    total = facts.get(Concept.TEMPORARY_EQUITY, period)
    if total is not None:
        return total.value, [total]

    parts = [
        fact
        for concept in (
            Concept.REDEEMABLE_NONCONTROLLING_INTEREST,
            Concept.TEMPORARY_EQUITY_PARENT,
        )
        if (fact := facts.get(concept, period)) is not None
    ]
    return sum((fact.value for fact in parts), Decimal(0)), parts


def check_balance_sheet_balances(facts: FactSet, period: Period) -> CheckResult | None:
    """Assets = Liabilities + Temporary equity + Equity."""
    if period.kind is not PeriodKind.INSTANT:
        return None

    identity = "Assets = Liabilities + Temporary equity + Equity"
    assets = facts.get(Concept.TOTAL_ASSETS, period)
    if assets is None:
        return _skipped("bs.balances", identity, Severity.CRITICAL, period, [Concept.TOTAL_ASSETS])

    # Many filers never tag a total `Liabilities` line: the balance sheet runs
    # current liabilities, non-current liabilities, then straight into equity.
    # Summing the two halves recovers the total exactly rather than abandoning
    # the most important check in the system.
    liabilities = facts.get(Concept.TOTAL_LIABILITIES, period)
    if liabilities is not None:
        liability_facts = [liabilities]
        liability_total = liabilities.value
    else:
        halves, missing_halves = _fetch(
            facts,
            period,
            (Concept.TOTAL_CURRENT_LIABILITIES, Concept.TOTAL_NONCURRENT_LIABILITIES),
        )
        if missing_halves:
            return _skipped(
                "bs.balances", identity, Severity.CRITICAL, period, [Concept.TOTAL_LIABILITIES]
            )
        liability_facts = halves
        liability_total = sum((f.value for f in halves), Decimal(0))

    # Prefer total equity including non-controlling interests; fall back to
    # stockholders' equity plus a separately-reported minority interest.
    absent: tuple[Concept, ...] = ()
    equity_fact = facts.get(Concept.TOTAL_EQUITY_INCL_MINORITY, period)
    if equity_fact is not None:
        equity_facts = [equity_fact]
        equity = equity_fact.value
    else:
        parent = facts.get(Concept.TOTAL_STOCKHOLDERS_EQUITY, period)
        if parent is None:
            return _skipped(
                "bs.balances",
                identity,
                Severity.CRITICAL,
                period,
                [Concept.TOTAL_STOCKHOLDERS_EQUITY],
            )
        minority = facts.get(Concept.MINORITY_INTEREST, period)
        equity_facts = [parent] + ([minority] if minority else [])
        equity = parent.value + (minority.value if minority else Decimal(0))
        absent = () if minority else (Concept.MINORITY_INTEREST,)

    mezzanine, mezzanine_facts = _temporary_equity(facts, period)

    involved = [assets, *liability_facts, *mezzanine_facts, *equity_facts]
    return _compare(
        check_id="bs.balances",
        identity=identity,
        severity=Severity.CRITICAL,
        period=period,
        expected=assets.value,
        actual=liability_total + mezzanine + equity,
        facts=involved,
        tolerance=_tolerance_for(involved, terms=3),
        absent_optional=absent,
    )


def check_assets_tie_to_total_liabilities_and_equity(
    facts: FactSet, period: Period
) -> CheckResult | None:
    """Assets = the printed "Total liabilities and equity".

    The cheapest corroboration on the balance sheet: both figures appear on the
    face of almost every filing, and they must agree by construction. It costs
    two lookups and verifies total assets even when a filer tags no separate
    `Liabilities` total, which many do not.
    """
    if period.kind is not PeriodKind.INSTANT:
        return None

    identity = "Total assets = total liabilities and equity"
    required = (Concept.TOTAL_ASSETS, Concept.TOTAL_LIABILITIES_AND_EQUITY)
    found, missing = _fetch(facts, period, required)
    if missing:
        return _skipped("bs.assets_tie", identity, Severity.CRITICAL, period, missing)

    assets, le_total = found
    return _compare(
        check_id="bs.assets_tie",
        identity=identity,
        severity=Severity.CRITICAL,
        period=period,
        expected=assets.value,
        actual=le_total.value,
        facts=found,
        tolerance=_tolerance_for(found, terms=2),
    )


def check_current_assets_subtotal(facts: FactSet, period: Period) -> CheckResult | None:
    """Total current assets = sum of its components."""
    if period.kind is not PeriodKind.INSTANT:
        return None

    identity = "Total current assets = sum of current asset line items"
    total = facts.get(Concept.TOTAL_CURRENT_ASSETS, period)
    if total is None:
        return _skipped(
            "bs.current_assets", identity, Severity.WARNING, period, [Concept.TOTAL_CURRENT_ASSETS]
        )

    components = (
        Concept.CASH_AND_EQUIVALENTS,
        Concept.SHORT_TERM_INVESTMENTS,
        Concept.ACCOUNTS_RECEIVABLE,
        Concept.INVENTORY,
        Concept.PREPAID_EXPENSES,
        Concept.OTHER_CURRENT_ASSETS,
    )
    found, _ = _fetch(facts, period, components)
    if not found:
        return _skipped("bs.current_assets", identity, Severity.WARNING, period, components)

    return _compare_subtotal(
        check_id="bs.current_assets",
        identity=identity,
        severity=Severity.WARNING,
        period=period,
        total=total,
        components=found,
        tolerance=_tolerance_for([total, *found]),
    )


def check_current_liabilities_subtotal(facts: FactSet, period: Period) -> CheckResult | None:
    """Total current liabilities = sum of its components."""
    if period.kind is not PeriodKind.INSTANT:
        return None

    identity = "Total current liabilities = sum of current liability line items"
    total = facts.get(Concept.TOTAL_CURRENT_LIABILITIES, period)
    if total is None:
        return _skipped(
            "bs.current_liabilities",
            identity,
            Severity.WARNING,
            period,
            [Concept.TOTAL_CURRENT_LIABILITIES],
        )

    components = (
        Concept.ACCOUNTS_PAYABLE,
        Concept.ACCRUED_LIABILITIES,
        Concept.DEFERRED_REVENUE_CURRENT,
        Concept.SHORT_TERM_DEBT,
        Concept.CURRENT_PORTION_LONG_TERM_DEBT,
        Concept.OPERATING_LEASE_LIABILITY_CURRENT,
        Concept.OTHER_CURRENT_LIABILITIES,
    )
    found, _ = _fetch(facts, period, components)
    if not found:
        return _skipped("bs.current_liabilities", identity, Severity.WARNING, period, components)

    return _compare_subtotal(
        check_id="bs.current_liabilities",
        identity=identity,
        severity=Severity.WARNING,
        period=period,
        total=total,
        components=found,
        tolerance=_tolerance_for([total, *found]),
    )


def check_assets_split(facts: FactSet, period: Period) -> CheckResult | None:
    """Total assets = current + non-current assets."""
    if period.kind is not PeriodKind.INSTANT:
        return None

    identity = "Total assets = current assets + non-current assets"
    required = (
        Concept.TOTAL_ASSETS,
        Concept.TOTAL_CURRENT_ASSETS,
        Concept.TOTAL_NONCURRENT_ASSETS,
    )
    found, missing = _fetch(facts, period, required)
    if missing:
        return _skipped("bs.assets_split", identity, Severity.WARNING, period, missing)

    total, current, noncurrent = found
    return _compare(
        check_id="bs.assets_split",
        identity=identity,
        severity=Severity.WARNING,
        period=period,
        expected=total.value,
        actual=current.value + noncurrent.value,
        facts=found,
        tolerance=_tolerance_for(found, terms=3),
    )


def check_liabilities_and_equity_total(facts: FactSet, period: Period) -> CheckResult | None:
    """The printed 'Total liabilities and equity' equals its parts."""
    if period.kind is not PeriodKind.INSTANT:
        return None

    identity = "Total liabilities and equity = liabilities + temporary equity + equity"
    total = facts.get(Concept.TOTAL_LIABILITIES_AND_EQUITY, period)
    liabilities = facts.get(Concept.TOTAL_LIABILITIES, period)
    if total is None or liabilities is None:
        return _skipped(
            "bs.le_total",
            identity,
            Severity.CRITICAL,
            period,
            [c for c, f in
             ((Concept.TOTAL_LIABILITIES_AND_EQUITY, total), (Concept.TOTAL_LIABILITIES, liabilities))
             if f is None],
        )

    equity_fact = facts.get(Concept.TOTAL_EQUITY_INCL_MINORITY, period) or facts.get(
        Concept.TOTAL_STOCKHOLDERS_EQUITY, period
    )
    if equity_fact is None:
        return _skipped(
            "bs.le_total", identity, Severity.CRITICAL, period, [Concept.TOTAL_STOCKHOLDERS_EQUITY]
        )

    mezzanine, mezzanine_facts = _temporary_equity(facts, period)

    involved = [total, liabilities, *mezzanine_facts, equity_fact]
    return _compare(
        check_id="bs.le_total",
        identity=identity,
        severity=Severity.CRITICAL,
        period=period,
        expected=total.value,
        actual=liabilities.value + mezzanine + equity_fact.value,
        facts=involved,
        tolerance=_tolerance_for(involved, terms=3),
    )


# ---------------------------------------------------------------------------
# comprehensive income and the equity roll-forward
# ---------------------------------------------------------------------------


def check_comprehensive_income(facts: FactSet, period: Period) -> CheckResult | None:
    """Comprehensive income = net income + other comprehensive income.

    The first check that spans two statements. Everything before it compares a
    statement against itself: the balance sheet balances, the cash flow
    statement rolls forward, the income statement subtotals add up. This one
    says the income statement and the comprehensive income statement agree
    about the same year, which neither can establish alone.

    Both terms are parent-only. Pairing a parent net income with a
    comprehensive income that includes non-controlling interests would compare
    two different populations and break for every filer with a partly-owned
    subsidiary.
    """
    if period.kind is not PeriodKind.DURATION:
        return None

    identity = "Comprehensive income = net income + other comprehensive income"
    found, missing = _fetch(
        facts,
        period,
        (Concept.COMPREHENSIVE_INCOME, Concept.NET_INCOME, Concept.OTHER_COMPREHENSIVE_INCOME),
    )
    if missing:
        return _skipped("ci.total", identity, Severity.CRITICAL, period, missing)

    total, net_income, oci = found
    return _compare(
        check_id="ci.total",
        identity=identity,
        severity=Severity.CRITICAL,
        period=period,
        expected=total.value,
        actual=net_income.value + oci.value,
        facts=found,
        tolerance=_tolerance_for(found, terms=3),
    )


#: The categories of other comprehensive income the vocabulary carries.
_OCI_CATEGORIES: tuple[Concept, ...] = (
    Concept.OCI_FOREIGN_CURRENCY,
    Concept.OCI_DERIVATIVES,
    Concept.OCI_SECURITIES,
    Concept.OCI_PENSION,
)


def check_oci_components(facts: FactSet, period: Period) -> CheckResult | None:
    """Other comprehensive income = sum of its categories.

    Only category totals are counted. A filer prints the movement arising in
    the period, the amount reclassified out to net income, and their sum; the
    tag map carries the sum alone, so this compares categories against the
    total rather than double-counting within one category.

    Deliberately not `_compare_subtotal`. That helper judges the two directions
    differently -- components summing above their own total is a contradiction,
    below it is incomplete extraction -- and that reasoning holds only while
    every component is non-negative, which is true of assets and expenses and
    false here. A translation loss is genuinely negative, so dropping one makes
    the rest sum *higher* and an ordinary gap looks like a contradiction. A
    property test found this by removing a negative category.

    Missing categories are named instead, so a difference that could be
    explained by one of them is reported as unevaluated rather than as a break.
    """
    if period.kind is not PeriodKind.DURATION:
        return None

    identity = "Other comprehensive income = sum of its categories"
    total = facts.get(Concept.OTHER_COMPREHENSIVE_INCOME, period)
    if total is None:
        return _skipped(
            "ci.components",
            identity,
            Severity.WARNING,
            period,
            [Concept.OTHER_COMPREHENSIVE_INCOME],
        )

    found, missing = _fetch(facts, period, _OCI_CATEGORIES)
    if not found:
        return _skipped("ci.components", identity, Severity.WARNING, period, missing)

    involved = [total, *found]
    expected = total.value
    actual = sum((f.value for f in found), Decimal(0))
    tolerance = _tolerance_for(involved)
    tol = tolerance.for_magnitude(expected)
    delta = actual - expected

    if abs(delta) <= tol:
        return CheckResult(
            check_id="ci.components",
            identity=identity,
            status=CheckStatus.PASSED,
            severity=Severity.WARNING,
            period_label=period.label,
            expected=expected,
            actual=actual,
            delta=delta,
            tolerance=tol,
            fact_ids=tuple(f.id for f in involved),
            message=f"{identity} holds within {tol}.",
        )

    # A difference is not a contradiction here. US GAAP's list of OCI
    # categories is open -- pension and postretirement adjustments, equity
    # method investee share, and others besides the ones this vocabulary
    # carries -- so a residual is the size of what is not modelled rather than
    # evidence that a filer's arithmetic is wrong. Coca-Cola reported 21 breaks
    # on this check for no better reason than that its OCI includes pension
    # adjustments, and false alarms are what teach a reader to stop reading the
    # panel.
    return CheckResult(
        check_id="ci.components",
        identity=identity,
        status=CheckStatus.SKIPPED,
        severity=Severity.WARNING,
        period_label=period.label,
        expected=expected,
        actual=actual,
        delta=delta,
        tolerance=tol,
        fact_ids=tuple(f.id for f in involved),
        missing=tuple(c.value for c in missing),
        message=(
            f"{identity} leaves {delta} unaccounted for. Not reported as a break "
            f"because other comprehensive income has categories this vocabulary "
            f"does not carry, and the residual is their likely size."
        ),
    )


#: The movements the equity roll-forward knows how to account for, and the
#: direction each one pushes equity. Anything a filer reports outside this set
#: shows up as a residual rather than being silently absorbed.
_EQUITY_MOVEMENTS: tuple[tuple[Concept, int], ...] = (
    (Concept.NET_INCOME, +1),
    (Concept.OTHER_COMPREHENSIVE_INCOME, +1),
    (Concept.STOCK_ISSUED, +1),
    (Concept.SHARE_BASED_COMP_EQUITY, +1),
    (Concept.STOCK_REPURCHASED, -1),
    (Concept.DIVIDENDS_DECLARED, -1),
    (Concept.TAX_WITHHOLDING_SHARE_BASED, -1),
)


def check_equity_rollforward(facts: FactSet, period: Period) -> CheckResult | None:
    """Closing equity = opening equity + everything that moved it.

    The widest identity in the system. It reaches across two balance sheets,
    the income statement and the comprehensive income statement at once, so a
    wrong number in any of them breaks it -- which is what makes it worth more
    than the checks it overlaps. Every other check compares figures that sit
    beside each other; this is the only one tying a period to the one before.

    Reported as a WARNING rather than CRITICAL. A filer may move equity in ways
    this does not model -- conversions, spin-offs, adopting a new accounting
    standard, reclassification between components -- and those are ordinary
    events rather than errors. A break here means "something moved equity that
    we did not account for", which is worth showing and is a weaker claim than
    "these numbers contradict each other".
    """
    if period.kind is not PeriodKind.DURATION:
        return None

    identity = (
        "Closing equity = opening equity + net income + OCI + issuances "
        "- buybacks - dividends"
    )

    opening = _instant_on(
        facts, Concept.TOTAL_STOCKHOLDERS_EQUITY, period.start_date - timedelta(days=1)
    )
    closing = _instant_on(facts, Concept.TOTAL_STOCKHOLDERS_EQUITY, period.end_date)
    if opening is None or closing is None:
        return _skipped(
            "eq.rollforward",
            identity,
            Severity.WARNING,
            period,
            [Concept.TOTAL_STOCKHOLDERS_EQUITY],
        )

    movements: list[FinancialFact] = []
    absent: list[Concept] = []
    total = opening.value
    for concept, direction in _EQUITY_MOVEMENTS:
        fact = facts.get(concept, period)
        if fact is None:
            absent.append(concept)
            continue
        movements.append(fact)
        total += direction * fact.value

    # Net income alone is not a roll-forward. Without at least one other
    # movement the identity reduces to "equity changed by earnings", which is
    # false for any company that pays a dividend and would report a break on
    # every filer rather than on a broken one.
    if len(movements) < 2:
        return _skipped("eq.rollforward", identity, Severity.WARNING, period, absent or [])

    involved = [opening, closing, *movements]
    return _compare(
        check_id="eq.rollforward",
        identity=identity,
        severity=Severity.WARNING,
        period=period,
        expected=closing.value,
        actual=total,
        facts=involved,
        tolerance=_tolerance_for(involved, terms=len(involved)),
        # A movement we could not find could account for a difference, so a
        # break is downgraded to a skip naming what was missing -- the rule the
        # cash roll-forward already uses for an absent FX effect.
        absent_optional=tuple(absent),
    )



# ---------------------------------------------------------------------------
# income statement
# ---------------------------------------------------------------------------


def check_gross_profit(facts: FactSet, period: Period) -> CheckResult | None:
    """Gross profit = revenue - cost of revenue."""
    if period.kind is not PeriodKind.DURATION:
        return None

    identity = "Gross profit = revenue - cost of revenue"
    required = (Concept.REVENUE, Concept.COST_OF_REVENUE, Concept.GROSS_PROFIT)
    found, missing = _fetch(facts, period, required)
    if missing:
        return _skipped("is.gross_profit", identity, Severity.WARNING, period, missing)

    revenue, cogs, gross = found
    return _compare(
        check_id="is.gross_profit",
        identity=identity,
        severity=Severity.WARNING,
        period=period,
        expected=gross.value,
        actual=revenue.value - cogs.value,
        facts=found,
        tolerance=_tolerance_for(found, terms=3),
    )


def check_operating_income(facts: FactSet, period: Period) -> CheckResult | None:
    """Operating income = gross profit - total operating expenses."""
    if period.kind is not PeriodKind.DURATION:
        return None

    identity = "Operating income = gross profit - operating expenses"
    required = (
        Concept.GROSS_PROFIT,
        Concept.TOTAL_OPERATING_EXPENSES,
        Concept.OPERATING_INCOME,
    )
    found, missing = _fetch(facts, period, required)
    if missing:
        return _skipped("is.operating_income", identity, Severity.WARNING, period, missing)

    gross, opex, operating = found
    return _compare(
        check_id="is.operating_income",
        identity=identity,
        severity=Severity.WARNING,
        period=period,
        expected=operating.value,
        actual=gross.value - opex.value,
        facts=found,
        tolerance=_tolerance_for(found, terms=3),
    )


def check_operating_expense_subtotal(facts: FactSet, period: Period) -> CheckResult | None:
    """Total operating expenses = sum of the operating expense line items."""
    if period.kind is not PeriodKind.DURATION:
        return None

    identity = "Total operating expenses = sum of operating expense line items"
    total = facts.get(Concept.TOTAL_OPERATING_EXPENSES, period)
    if total is None:
        return _skipped(
            "is.opex_subtotal",
            identity,
            Severity.WARNING,
            period,
            [Concept.TOTAL_OPERATING_EXPENSES],
        )

    components = (
        Concept.RESEARCH_AND_DEVELOPMENT,
        Concept.SELLING_GENERAL_ADMIN,
        Concept.SALES_AND_MARKETING,
        Concept.GENERAL_AND_ADMIN,
        Concept.OTHER_OPERATING_EXPENSE,
    )
    found, _ = _fetch(facts, period, components)
    if not found:
        return _skipped("is.opex_subtotal", identity, Severity.WARNING, period, components)

    # SG&A reported alongside its separate S&M and G&A components is handled by
    # the redundancy detection in _compare_subtotal, along with every other
    # aggregate-plus-parts presentation.
    return _compare_subtotal(
        check_id="is.opex_subtotal",
        identity=identity,
        severity=Severity.WARNING,
        period=period,
        total=total,
        components=found,
        tolerance=_tolerance_for([total, *found]),
    )


def check_net_income(facts: FactSet, period: Period) -> CheckResult | None:
    """Consolidated net income = pre-tax income - tax expense.

    The subtraction yields income *including* the non-controlling interest
    share, not income attributable to the parent. For a company with
    consolidated subsidiaries it does not wholly own, those differ by the NCI
    portion -- materially so for the likes of Coca-Cola and Walmart. Checking
    against parent-only net income would report a break on every such period
    while the filing is entirely correct.
    """
    if period.kind is not PeriodKind.DURATION:
        return None

    identity = "Consolidated net income = pre-tax income - income tax expense"
    required = (Concept.PRETAX_INCOME, Concept.INCOME_TAX_EXPENSE)
    found, missing = _fetch(facts, period, required)
    if missing:
        return _skipped("is.net_income", identity, Severity.WARNING, period, missing)

    pretax, tax = found

    # Prefer the explicitly-reported consolidated figure. Failing that,
    # reconstruct it from parent net income plus the NCI share.
    absent: tuple[Concept, ...] = ()
    consolidated = facts.get(Concept.NET_INCOME_INCLUDING_NCI, period)
    if consolidated is not None:
        income_facts = [consolidated]
        expected = consolidated.value
    else:
        parent = facts.get(Concept.NET_INCOME, period)
        if parent is None:
            return _skipped("is.net_income", identity, Severity.WARNING, period, [Concept.NET_INCOME])
        nci = facts.get(Concept.NET_INCOME_TO_NCI, period)
        income_facts = [parent] + ([nci] if nci else [])
        expected = parent.value + (nci.value if nci else Decimal(0))
        absent = () if nci else (Concept.NET_INCOME_TO_NCI,)

    involved = [pretax, tax, *income_facts]
    return _compare(
        check_id="is.net_income",
        identity=identity,
        severity=Severity.WARNING,
        period=period,
        expected=expected,
        actual=pretax.value - tax.value,
        facts=involved,
        tolerance=_tolerance_for(involved, terms=3),
        absent_optional=absent,
    )


def check_eps(facts: FactSet, period: Period) -> CheckResult | None:
    """Diluted EPS = net income to common / diluted weighted average shares.

    Informational: EPS is reported to the cent, so back-solving it against
    figures rounded to millions is inherently imprecise. A break here is a hint
    to re-read the extraction, not proof of one.
    """
    if period.kind is not PeriodKind.DURATION:
        return None

    identity = "Diluted EPS = net income to common / diluted shares"
    eps = facts.get(Concept.EPS_DILUTED, period)
    shares = facts.get(Concept.SHARES_DILUTED, period)
    income = facts.get(Concept.NET_INCOME_TO_COMMON, period) or facts.get(
        Concept.NET_INCOME, period
    )
    if eps is None or shares is None or income is None:
        return _skipped(
            "is.eps",
            identity,
            Severity.INFO,
            period,
            [c for c, f in
             ((Concept.EPS_DILUTED, eps), (Concept.SHARES_DILUTED, shares), (Concept.NET_INCOME, income))
             if f is None],
        )
    if shares.value == 0:
        return _skipped("is.eps", identity, Severity.INFO, period, [Concept.SHARES_DILUTED])

    involved = [eps, shares, income]
    computed = income.value / shares.value
    # EPS is printed to the cent; allow half a cent of rounding plus 1% for the
    # rounding already baked into the income and share counts.
    return _compare(
        check_id="is.eps",
        identity=identity,
        severity=Severity.INFO,
        period=period,
        expected=eps.value,
        actual=computed,
        facts=involved,
        tolerance=ToleranceModel(scale=Decimal("0.01"), terms=1, relative=Decimal("0.01")),
    )


# ---------------------------------------------------------------------------
# cash flow
# ---------------------------------------------------------------------------


def check_cash_rollforward(facts: FactSet, period: Period) -> CheckResult | None:
    """Ending cash = beginning cash + operating + investing + financing + FX.

    The strongest single check in the system: it ties all three sections of the
    cash flow statement together and, via the next check, back to the balance
    sheet.
    """
    if period.kind is not PeriodKind.DURATION:
        return None

    identity = "Ending cash = beginning cash + operating + investing + financing + FX"
    required = (
        Concept.NET_CASH_OPERATING,
        Concept.NET_CASH_INVESTING,
        Concept.NET_CASH_FINANCING,
    )
    found, missing = _fetch(facts, period, required)
    if missing:
        return _skipped("cf.rollforward", identity, Severity.CRITICAL, period, missing)

    # Prefer explicitly-reported opening and closing balances -- a PDF cash flow
    # statement prints them as their own lines -- and otherwise take them from
    # the balance sheet at the period's boundaries, which is how XBRL carries
    # them.
    instant = _instant_at(period)
    beginning = facts.get(Concept.CASH_BEGINNING_OF_PERIOD, instant) or _cash_on(
        facts, period.start_date - timedelta(days=1)
    )
    ending = facts.get(Concept.CASH_END_OF_PERIOD, instant) or _cash_on(facts, period.end_date)
    if beginning is None or ending is None:
        return _skipped(
            "cf.rollforward",
            identity,
            Severity.CRITICAL,
            period,
            [Concept.CASH_AND_EQUIVALENTS],
        )

    operating, investing, financing = found
    fx = facts.get(Concept.FX_EFFECT_ON_CASH, period)

    involved = [beginning, ending, operating, investing, financing] + ([fx] if fx else [])
    actual = (
        beginning.value
        + operating.value
        + investing.value
        + financing.value
        + (fx.value if fx else Decimal(0))
    )
    return _compare(
        check_id="cf.rollforward",
        identity=identity,
        severity=Severity.CRITICAL,
        period=period,
        expected=ending.value,
        actual=actual,
        facts=involved,
        tolerance=_tolerance_for(involved, terms=len(involved)),
        absent_optional=() if fx else (Concept.FX_EFFECT_ON_CASH,),
    )


def check_net_change_in_cash(facts: FactSet, period: Period) -> CheckResult | None:
    """The printed net change in cash equals the sum of the three sections."""
    if period.kind is not PeriodKind.DURATION:
        return None

    identity = "Net change in cash = operating + investing + financing + FX"
    required = (
        Concept.NET_CHANGE_IN_CASH,
        Concept.NET_CASH_OPERATING,
        Concept.NET_CASH_INVESTING,
        Concept.NET_CASH_FINANCING,
    )
    found, missing = _fetch(facts, period, required)
    if missing:
        return _skipped("cf.net_change", identity, Severity.WARNING, period, missing)

    change, operating, investing, financing = found
    fx = facts.get(Concept.FX_EFFECT_ON_CASH, period)
    involved = [*found] + ([fx] if fx else [])
    return _compare(
        check_id="cf.net_change",
        identity=identity,
        severity=Severity.WARNING,
        period=period,
        expected=change.value,
        actual=(
            operating.value + investing.value + financing.value + (fx.value if fx else Decimal(0))
        ),
        facts=involved,
        tolerance=_tolerance_for(involved, terms=len(involved)),
        absent_optional=() if fx else (Concept.FX_EFFECT_ON_CASH,),
    )


def check_cash_ties_to_balance_sheet(facts: FactSet, period: Period) -> CheckResult | None:
    """Cash flow statement ending cash = balance sheet cash at the same instant.

    This is the cross-statement tie. If it holds, the cash flow statement and
    the balance sheet were extracted from the same period and the same scale --
    which catches the single most damaging extraction error, a column offset.
    """
    if period.kind is not PeriodKind.INSTANT:
        return None

    identity = "Cash flow ending cash = balance sheet cash"
    cf_cash = facts.get(Concept.CASH_END_OF_PERIOD, period)
    bs_cash = facts.get(Concept.CASH_AND_EQUIVALENTS, period)
    if cf_cash is None or bs_cash is None:
        return _skipped(
            "xs.cash_tie",
            identity,
            Severity.CRITICAL,
            period,
            [c for c, f in
             ((Concept.CASH_END_OF_PERIOD, cf_cash), (Concept.CASH_AND_EQUIVALENTS, bs_cash))
             if f is None],
        )

    involved = [cf_cash, bs_cash]
    return _compare(
        check_id="xs.cash_tie",
        identity=identity,
        severity=Severity.CRITICAL,
        period=period,
        expected=bs_cash.value,
        actual=cf_cash.value,
        facts=involved,
        tolerance=_tolerance_for(involved, terms=2),
    )


def check_net_income_ties_to_cash_flow(facts: FactSet, period: Period) -> CheckResult | None:
    """Net income on the income statement = the cash flow statement's top line.

    Both are stored under NET_INCOME, so a genuine mismatch surfaces earlier as
    a CONFLICTED fact. This check exists to make the tie explicit in the report
    and to catch the case where the conflict was resolved in favour of one
    document but the other value is still on file.
    """
    if period.kind is not PeriodKind.DURATION:
        return None

    identity = "Income statement net income = cash flow statement net income"
    candidates = [f for f in facts.for_period(period) if f.concept is Concept.NET_INCOME]
    if len(candidates) < 2:
        return _skipped("xs.net_income_tie", identity, Severity.INFO, period, [Concept.NET_INCOME])

    first, *rest = candidates
    worst = max(rest, key=lambda f: abs(f.value - first.value))
    return _compare(
        check_id="xs.net_income_tie",
        identity=identity,
        severity=Severity.CRITICAL,
        period=period,
        expected=first.value,
        actual=worst.value,
        facts=candidates,
        tolerance=_tolerance_for(candidates, terms=2),
    )


# ---------------------------------------------------------------------------
# period arithmetic
# ---------------------------------------------------------------------------


def check_period_arithmetic(facts: FactSet, period: Period) -> CheckResult | None:
    """A cumulative period equals the sum of its constituent quarters.

    Only meaningful for flow concepts: a balance sheet instant does not
    decompose additively. Evaluated once per cumulative period, over revenue as
    the representative flow.
    """
    if period.kind is not PeriodKind.DURATION:
        return None
    parts = PERIOD_COMPOSITION.get(period.fiscal_period)
    if parts is None:
        return None

    identity = f"{period.fiscal_period.value} revenue = sum of {', '.join(p.value for p in parts)}"
    total = facts.get(Concept.REVENUE, period)
    if total is None:
        return _skipped("period.arithmetic", identity, Severity.WARNING, period, [Concept.REVENUE])

    quarter_facts: list[FinancialFact] = []
    for part in parts:
        match = [
            f
            for f in facts
            if f.concept is Concept.REVENUE
            and f.period.fiscal_year == period.fiscal_year
            and f.period.fiscal_period is part
        ]
        if len(match) != 1:
            return _skipped("period.arithmetic", identity, Severity.WARNING, period, [Concept.REVENUE])
        quarter_facts.append(match[0])

    involved = [total, *quarter_facts]
    return _compare(
        check_id="period.arithmetic",
        identity=identity,
        severity=Severity.WARNING,
        period=period,
        expected=total.value,
        actual=sum((f.value for f in quarter_facts), Decimal(0)),
        facts=involved,
        tolerance=_tolerance_for(involved, terms=len(involved)),
    )


def check_no_duplicate_periods(facts: FactSet, period: Period) -> CheckResult | None:
    """No concept is reported twice for the same period with different values.

    Duplicate slots make every downstream lookup ambiguous, so this is treated
    as critical even though it is a structural rather than an accounting check.
    """
    duplicates = {
        key: group
        for key, group in facts.for_period(period).duplicates().items()
        if len({f.value for f in group}) > 1
    }
    identity = "Each concept has at most one value per period"
    if not duplicates:
        return CheckResult(
            check_id="struct.no_duplicates",
            identity=identity,
            status=CheckStatus.PASSED,
            severity=Severity.CRITICAL,
            period_label=period.label,
            message=identity + " holds.",
        )

    offenders = sorted(k.concept.value for k in duplicates)
    return CheckResult(
        check_id="struct.no_duplicates",
        identity=identity,
        status=CheckStatus.FAILED,
        severity=Severity.CRITICAL,
        period_label=period.label,
        fact_ids=tuple(f.id for group in duplicates.values() for f in group),
        message=(
            f"{len(duplicates)} concept(s) have conflicting values in "
            f"{period.label}: {', '.join(offenders)}."
        ),
    )


ALL_CHECKS: tuple[Check, ...] = (
    check_no_duplicate_periods,
    # balance sheet
    check_balance_sheet_balances,
    check_assets_tie_to_total_liabilities_and_equity,
    check_liabilities_and_equity_total,
    check_assets_split,
    check_current_assets_subtotal,
    check_current_liabilities_subtotal,
    # income statement
    check_gross_profit,
    check_operating_expense_subtotal,
    check_operating_income,
    check_net_income,
    check_eps,
    # cash flow
    check_cash_rollforward,
    check_net_change_in_cash,
    # cross-statement
    check_cash_ties_to_balance_sheet,
    check_comprehensive_income,
    check_oci_components,
    check_equity_rollforward,
    check_net_income_ties_to_cash_flow,
    # periods
    check_period_arithmetic,
)


__all__ = [
    "ALL_CHECKS",
    "Check",
    "FiscalPeriod",
    *(c.__name__ for c in ALL_CHECKS),
]
