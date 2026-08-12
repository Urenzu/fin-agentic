"""Runs the identity checks and assigns each fact a verification status.

The promotion rule is deliberately conservative:

    A fact becomes VERIFIED only if it participated in at least one *passed*
    check and in no *failed* check.

A fact no check could reach stays UNVERIFIED. That is the honest outcome -- the
system has no corroborating evidence for it -- and the UI shows it as
unverified rather than pretending otherwise. This is what stops a plausible
hallucinated number from reaching the user: to be shown, a number must be
arithmetically consistent with other numbers in the filing, and a fabricated
value will not satisfy the balance sheet.
"""

from __future__ import annotations

from finagentic.domain.facts import FactStatus, FinancialFact
from finagentic.domain.ledger import FactSet
from finagentic.validation.identities import ALL_CHECKS, Check
from finagentic.validation.results import CheckResult, ValidationReport


def run_checks(facts: FactSet, checks: tuple[Check, ...] = ALL_CHECKS) -> ValidationReport:
    """Evaluate every applicable check across every period in `facts`."""
    results: list[CheckResult] = []
    for period in facts.periods():
        for check in checks:
            result = check(facts, period)
            if result is not None:
                results.append(result)
    return ValidationReport(results=tuple(results))


def apply_statuses(facts: FactSet, report: ValidationReport) -> FactSet:
    """Return a new FactSet with each fact's status set from `report`."""
    failing = report.failing_fact_ids()
    passing = report.passing_fact_ids()

    updated: list[FinancialFact] = []
    for fact in facts:
        if fact.status in (FactStatus.REJECTED, FactStatus.CONFLICTED):
            # Already adjudicated upstream by the reconciler; validation does
            # not resurrect a fact that was ruled out.
            continue
        if fact.id in failing:
            status = FactStatus.INCONSISTENT
        elif fact.id in passing:
            status = FactStatus.VERIFIED
        else:
            status = FactStatus.UNVERIFIED
        if status is not fact.status:
            updated.append(fact.with_status(status))

    return facts.replace(updated)


def validate(facts: FactSet) -> tuple[FactSet, ValidationReport]:
    """Run validation and return the status-annotated ledger with its report."""
    report = run_checks(facts)
    return apply_statuses(facts, report), report
