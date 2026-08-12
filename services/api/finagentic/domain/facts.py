"""The atomic unit of the ledger: a single financial fact with provenance.

Design rules enforced here, at construction time, rather than by convention:

1. A fact cannot exist without provenance. There is no code path that produces a
   number the system cannot trace back to a page and a span of source text.
2. Money is `Decimal`, never `float`. Binary floats cannot represent 0.1, and an
   accounting identity checked in float arithmetic accumulates error that is
   indistinguishable from a real reconciliation break.
3. The stored `value` is normalised (scaled and sign-corrected); `raw_value` and
   `scale` retain what the document literally printed. Both are kept so a
   reviewer can always reconstruct the transformation.
4. A fact's period kind must match its concept's period kind, which catches
   duration/instant confusion at the boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from finagentic.domain.concepts import Concept, SignConvention, Unit, meta
from finagentic.domain.periods import Period

#: Multipliers a statement header may declare, e.g. "(in thousands)".
Scale = Decimal
SCALE_UNITS = Decimal(1)
SCALE_THOUSANDS = Decimal(1_000)
SCALE_MILLIONS = Decimal(1_000_000)
SCALE_BILLIONS = Decimal(1_000_000_000)

VALID_SCALES: frozenset[Decimal] = frozenset(
    {SCALE_UNITS, SCALE_THOUSANDS, SCALE_MILLIONS, SCALE_BILLIONS}
)

SCALE_LABELS: dict[Decimal, str] = {
    SCALE_UNITS: "units",
    SCALE_THOUSANDS: "thousands",
    SCALE_MILLIONS: "millions",
    SCALE_BILLIONS: "billions",
}


class FactStatus(StrEnum):
    """Where a fact stands with respect to verification.

    Only VERIFIED facts are eligible to back a number shown to the user or
    quoted by the chat agent. Everything else is visible in the UI as an
    explicit gap rather than being silently dropped or silently used.
    """

    #: Extracted, not yet run through the validation layer.
    UNVERIFIED = "unverified"
    #: Participates in at least one satisfied accounting identity.
    VERIFIED = "verified"
    #: Participates in a failing identity; the break is recorded on the check.
    INCONSISTENT = "inconsistent"
    #: Two extractions disagree on the value for this concept and period.
    CONFLICTED = "conflicted"
    #: Structurally invalid or superseded; retained for audit, never used.
    REJECTED = "rejected"


class BoundingBox(BaseModel):
    """Position of the source text on the page, in PDF points, origin top-left."""

    model_config = ConfigDict(frozen=True)

    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="after")
    def _check_ordering(self) -> Self:
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError(f"degenerate bounding box: {self}")
        return self


class Provenance(BaseModel):
    """Where a fact came from, precisely enough to highlight it in the source."""

    model_config = ConfigDict(frozen=True)

    document_id: UUID
    #: 1-indexed page number as a reader would count it.
    page: int = Field(ge=1)
    #: Exact substring of the page text the value was read from. Verified to be
    #: present in the page during ingestion -- an extractor that paraphrases
    #: instead of quoting is rejected.
    raw_text: str = Field(min_length=1)
    #: The line item label exactly as printed in the statement.
    row_label: str = Field(min_length=1)
    #: The column header the value sat under, as printed.
    column_header: str | None = None
    bbox: BoundingBox | None = None
    #: Identifier of the extractor that produced this fact, e.g. "llm:claude-opus-5"
    #: or "xbrl:us-gaap". Lets a bad extractor version be found and revoked.
    extractor: str = Field(min_length=1)
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FinancialFact(BaseModel):
    """One number, from one document, for one concept and one period."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    document_id: UUID
    entity_id: UUID
    concept: Concept
    period: Period

    #: Normalised value: raw_value * scale, sign-corrected per the concept's
    #: SignConvention. This is the only value analytics ever reads.
    value: Decimal
    unit: Unit

    #: Exactly what the document printed, before scaling and sign correction.
    raw_value: Decimal
    scale: Decimal = SCALE_UNITS
    #: True when normalisation flipped a printed negative to a stored positive
    #: (or vice versa) to satisfy the concept's sign convention.
    sign_flipped: bool = False

    provenance: Provenance
    status: FactStatus = FactStatus.UNVERIFIED
    #: Extractor's self-reported confidence. Advisory only -- it never gates
    #: whether a fact is trusted; the validation layer does that.
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        cm = meta(self.concept)

        if self.period.kind is not cm.period_kind:
            raise ValueError(
                f"{self.concept} is a {cm.period_kind} concept but was given a "
                f"{self.period.kind} period ({self.period.label})"
            )

        if self.unit is not cm.unit:
            raise ValueError(
                f"{self.concept} is denominated in {cm.unit} but was given {self.unit}"
            )

        if self.scale not in VALID_SCALES:
            raise ValueError(
                f"scale {self.scale} is not one of {sorted(SCALE_LABELS.values())}"
            )

        # Per-share amounts are always printed at full precision -- a statement
        # header saying "in millions" never applies to the EPS line. Scaling one
        # produces a value off by six orders of magnitude, which is otherwise
        # hard to spot because the resulting number is still "plausible".
        if cm.unit is Unit.USD_PER_SHARE and self.scale != SCALE_UNITS:
            raise ValueError(
                f"{self.concept} is a per-share amount and cannot carry a "
                f"{SCALE_LABELS[self.scale]} scale"
            )

        if cm.sign is SignConvention.MAGNITUDE and self.value < 0:
            raise ValueError(
                f"{self.concept} uses the MAGNITUDE sign convention and must be "
                f"stored non-negative, got {self.value}"
            )

        expected = (abs(self.raw_value) if cm.sign is SignConvention.MAGNITUDE
                    else self.raw_value) * self.scale
        if self.value != expected:
            raise ValueError(
                f"value {self.value} does not equal raw_value {self.raw_value} "
                f"scaled by {self.scale} under the {cm.sign} convention "
                f"(expected {expected})"
            )

        flipped = (self.raw_value < 0) != (self.value < 0)
        if flipped != self.sign_flipped:
            raise ValueError(
                f"sign_flipped={self.sign_flipped} contradicts raw_value "
                f"{self.raw_value} -> value {self.value}"
            )

        return self

    @classmethod
    def from_reported(
        cls,
        *,
        document_id: UUID,
        entity_id: UUID,
        concept: Concept,
        period: Period,
        raw_value: Decimal,
        scale: Decimal,
        provenance: Provenance,
        confidence: float = 1.0,
    ) -> FinancialFact:
        """Build a fact from a value as printed, applying normalisation.

        This is the only constructor extraction code should use: it derives
        `value`, `sign_flipped` and `unit` from the concept registry so the
        normalisation rules live in exactly one place.
        """
        cm = meta(concept)
        magnitude = abs(raw_value) if cm.sign is SignConvention.MAGNITUDE else raw_value
        value = magnitude * scale
        return cls(
            document_id=document_id,
            entity_id=entity_id,
            concept=concept,
            period=period,
            value=value,
            unit=cm.unit,
            raw_value=raw_value,
            scale=scale,
            sign_flipped=(raw_value < 0) != (value < 0),
            provenance=provenance,
            confidence=confidence,
        )

    @property
    def is_usable(self) -> bool:
        """Whether analytics and the chat agent may quote this fact."""
        return self.status is FactStatus.VERIFIED

    def with_status(self, status: FactStatus) -> FinancialFact:
        """Return a copy carrying `status`. Facts are frozen; verification
        produces new instances rather than mutating the extracted record."""
        return self.model_copy(update={"status": status})


class FactKey(BaseModel):
    """Identity of a fact slot: one concept, for one entity, in one period.

    Two facts sharing a key are describing the same thing and must agree. The
    reconciler uses this to detect conflicts across documents -- for example a
    10-K restating a figure a prior 10-Q reported differently.
    """

    model_config = ConfigDict(frozen=True)

    entity_id: UUID
    concept: Concept
    period_key: tuple[int, str, str]

    @classmethod
    def of(cls, fact: FinancialFact) -> FactKey:
        return cls(
            entity_id=fact.entity_id,
            concept=fact.concept,
            period_key=fact.period.key,
        )
