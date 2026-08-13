"""API response models.

Thin by construction: the domain objects are already Pydantic and already carry
the invariants, so these mostly reshape them for transport rather than
redefining them. Anywhere a field here duplicates a domain field, the domain is
the source of truth.

Money crosses the wire as a decimal string, never a JSON number. A JSON number
is parsed as an IEEE double by every JavaScript client, and 391035000000 is
fine while 0.1 is not -- so the rule is applied uniformly rather than only where
it currently happens to matter.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from finagentic.domain.concepts import Statement, Unit
from finagentic.domain.facts import FactStatus
from finagentic.ingest.shapes import EntityShape
from finagentic.validation.results import CheckStatus, Severity


def _decimal_str(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


class RegistrantOut(BaseModel):
    cik: int
    ticker: str
    name: str


class ShapeOut(BaseModel):
    """What kind of filer this is, and whether we can analyse it properly."""

    shape: EntityShape
    supported: bool
    message: str
    evidence: tuple[str, ...] = ()


class CoverageOut(BaseModel):
    """How much of the company's history we hold, and how much of it reconciles."""

    earliest: str | None = None
    latest: str | None = None
    history_years: float = 0.0
    annual_reports: int = 0
    #: True when the ledger is too thin to be the company the user meant --
    #: typically a ticker that resolved to a post-reorganisation holding company.
    looks_truncated: bool = False
    fact_count: int = 0
    verified_count: int = 0


IngestState = Literal["ingesting", "ready", "error"]


class EntityOut(BaseModel):
    """Everything the client needs before deciding what to render."""

    registrant: RegistrantOut
    state: IngestState
    #: Populated once ingestion completes.
    shape: ShapeOut | None = None
    coverage: CoverageOut | None = None
    error: str | None = None

    #: Reasons the client must show the user rather than rendering silently.
    #: Kept as a required field so it cannot be forgotten: a truncated history or
    #: an unsupported statement structure has to reach the screen.
    advisories: tuple[str, ...] = ()


class CellOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    value: str
    status: FactStatus
    verified: bool
    fact_id: str
    source_url: str | None = None
    source_label: str | None = None


class LineOut(BaseModel):
    concept: str
    label: str
    indent: int
    is_subtotal: bool
    unit: Unit
    #: Keyed by period label. A missing key means the company did not report the
    #: line, which is different from reporting zero.
    cells: dict[str, CellOut]


class StatementOut(BaseModel):
    statement: Statement
    period_labels: tuple[str, ...]
    lines: tuple[LineOut, ...]
    #: Share of rendered values corroborated by an accounting identity.
    verified_ratio: float
    shape: ShapeOut
    advisories: tuple[str, ...] = ()


class CheckOut(BaseModel):
    check_id: str
    identity: str
    status: CheckStatus
    severity: Severity
    period_label: str
    expected: str | None = None
    actual: str | None = None
    delta: str | None = None
    tolerance: str | None = None
    missing: tuple[str, ...] = ()
    message: str


class ValidationOut(BaseModel):
    passed: int
    failed: int
    skipped: int
    is_clean: bool
    results: tuple[CheckOut, ...]


class FactOut(BaseModel):
    id: str
    concept: str
    label: str
    period_label: str
    period_end: str
    value: str
    unit: Unit
    status: FactStatus
    source: str
    source_url: str | None = None
    source_label: str | None = None


class FactsOut(BaseModel):
    facts: tuple[FactOut, ...]
    total: int


class SearchResultOut(BaseModel):
    results: tuple[RegistrantOut, ...] = Field(default=())
