"""Result types for the validation layer.

A check never raises and never silently passes. It returns a `CheckResult`
carrying the expected value, the actual value, the tolerance applied and the
ids of every fact involved. That record is what the UI renders in the
reconciliation panel and what the chat agent cites when asked "how do you know
this is right?".
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CheckStatus(StrEnum):
    #: Identity held within tolerance.
    PASSED = "passed"
    #: Identity did not hold. The facts involved are marked INCONSISTENT.
    FAILED = "failed"
    #: A required input was absent, so the identity could not be evaluated.
    #: Distinct from FAILED: absence of evidence is not evidence of a break.
    SKIPPED = "skipped"


class Severity(StrEnum):
    #: A break means the extraction is wrong. Balance sheet must balance.
    CRITICAL = "critical"
    #: A break usually means the extraction is wrong, but legitimate
    #: presentation differences exist.
    WARNING = "warning"
    #: Informational cross-check; breaks are common and often benign.
    INFO = "info"


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    check_id: str
    #: Human-readable statement of the identity, e.g. "Assets = Liabilities + Equity".
    identity: str
    status: CheckStatus
    severity: Severity
    period_label: str

    expected: Decimal | None = None
    actual: Decimal | None = None
    #: actual - expected. Signed, so the direction of a break is visible.
    delta: Decimal | None = None
    tolerance: Decimal | None = None

    #: Facts that fed the check. On failure these are the candidates for review.
    fact_ids: tuple[UUID, ...] = ()
    #: Concepts that were required but absent, populated when status is SKIPPED.
    missing: tuple[str, ...] = ()
    message: str = ""

    @property
    def is_blocking(self) -> bool:
        return self.status is CheckStatus.FAILED and self.severity is Severity.CRITICAL


class ValidationReport(BaseModel):
    """The full outcome of validating one entity's facts."""

    model_config = ConfigDict(frozen=True)

    results: tuple[CheckResult, ...] = ()

    @property
    def passed(self) -> tuple[CheckResult, ...]:
        return tuple(r for r in self.results if r.status is CheckStatus.PASSED)

    @property
    def failed(self) -> tuple[CheckResult, ...]:
        return tuple(r for r in self.results if r.status is CheckStatus.FAILED)

    @property
    def skipped(self) -> tuple[CheckResult, ...]:
        return tuple(r for r in self.results if r.status is CheckStatus.SKIPPED)

    @property
    def blocking(self) -> tuple[CheckResult, ...]:
        return tuple(r for r in self.results if r.is_blocking)

    @property
    def is_clean(self) -> bool:
        """True when nothing critical broke. Skips do not make a report dirty."""
        return not self.blocking

    def failing_fact_ids(self) -> frozenset[UUID]:
        """Every fact implicated in at least one failed check."""
        return frozenset(fid for r in self.failed for fid in r.fact_ids)

    def passing_fact_ids(self) -> frozenset[UUID]:
        """Every fact implicated in at least one passed check."""
        return frozenset(fid for r in self.passed for fid in r.fact_ids)

    def summary(self) -> str:
        return (
            f"{len(self.passed)} passed, {len(self.failed)} failed, "
            f"{len(self.skipped)} skipped"
        )


class ToleranceModel(BaseModel):
    """How much rounding slack an identity is allowed.

    Statements printed "in millions" round every line to the nearest million, so
    a sum of N such lines can legitimately miss by up to N/2 million while every
    input is correctly extracted. Tolerance therefore scales with both the
    reporting scale and the number of terms, with a relative floor for very
    large magnitudes where accumulated rounding is proportionally larger.
    """

    model_config = ConfigDict(frozen=True)

    #: Half-unit rounding error per term, at the statement's reporting scale.
    scale: Decimal = Field(default=Decimal(1))
    #: Number of independently-rounded terms in the identity.
    terms: int = Field(default=2, ge=1)
    #: Additional slack as a fraction of the expected magnitude. Kept at one
    #: basis point: the per-term rounding allowance above is the principled
    #: bound, and this only guards against unusual scales. Loosening it would
    #: let a genuine reconciliation break hide inside the tolerance.
    relative: Decimal = Field(default=Decimal("0.0001"))

    def for_magnitude(self, magnitude: Decimal) -> Decimal:
        absolute = self.scale * Decimal(self.terms) / 2
        return max(absolute, abs(magnitude) * self.relative)
