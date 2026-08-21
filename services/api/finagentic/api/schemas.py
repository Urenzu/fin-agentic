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

from typing import Literal

from pydantic import BaseModel, Field

from finagentic.ingest.shapes import EntityShape


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
    """How much of the company's filing history EDGAR holds.

    Four figures, taken from the observations' own dates and accessions. There
    was once a fact count and a "corroborated" ratio here, both by-products of
    a canonical ledger that no longer exists -- and the ratio was never what it
    looked like, since it measured how much of the ledger some accounting
    identity happened to touch rather than how much of it was right.
    """

    earliest: str | None = None
    latest: str | None = None
    history_years: float = 0.0
    annual_reports: int = 0
    #: True when the ledger is too thin to be the company the user meant --
    #: typically a ticker that resolved to a post-reorganisation holding company.
    looks_truncated: bool = False
    #: How many figures EDGAR published for this filer. A sense of scale, not a
    #: quality measure.
    observations: int = 0


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


class SearchResultOut(BaseModel):
    results: tuple[RegistrantOut, ...] = Field(default=())


class AsFiledRowOut(BaseModel):
    label: str
    element: str | None = None
    tag: str | None = None
    is_abstract: bool
    is_total: bool
    indent: int
    #: Keyed by `AsFiledColumnOut.key`. A missing key means the cell was blank
    #: on the face of the statement, which the filer uses to mean "not
    #: applicable", not "zero".
    values: dict[str, str]


class AsFiledColumnOut(BaseModel):
    """One period column of a statement."""

    #: Unique within the statement, and what `AsFiledRowOut.values` is keyed
    #: by. `label` is not unique: a 10-Q prints the same period end under both
    #: "3 Months Ended" and "9 Months Ended".
    key: str
    label: str
    #: The spanning heading, e.g. "3 Months Ended". None for an instant.
    duration: str | None = None
    date: str | None = None


class AsFiledStatementOut(BaseModel):
    """A statement exactly as the filer presented it."""

    title: str
    short_name: str
    columns: tuple[AsFiledColumnOut, ...]
    rows: tuple[AsFiledRowOut, ...]
    #: Multipliers already applied to `values`; retained so a client can render
    #: figures back at the scale the filing printed them.
    monetary_scale: str
    share_scale: str
    accession: str
    form: str
    filed: str
    source_url: str


class MetricValueOut(BaseModel):
    """One comparable figure, for one period of one filing."""

    metric: str
    label: str
    value: str
    #: The us-gaap element this came from. Two filers report the same metric
    #: under different names, which is the reason the mapping exists, so which
    #: line was used stays visible rather than being taken on trust.
    element: str
    period_label: str
    period_end: str | None = None
    duration: str | None = None


class CompanyMetricsOut(BaseModel):
    """One company's figures from one filing."""

    registrant: RegistrantOut
    accession: str
    form: str
    filed: str
    period_end: str | None = None
    #: Keyed by metric, newest period first.
    metrics: dict[str, tuple[MetricValueOut, ...]]
    #: Metrics this filer does not report. Costco prints no gross profit and
    #: Coca-Cola no total liabilities; both are the filer's choice, and naming
    #: them is more use than an empty cell the reader has to interpret.
    absent: tuple[str, ...] = ()


class MetricDescriptorOut(BaseModel):
    """What a metric is, independent of any company reporting it."""

    metric: str
    label: str
    #: "instant" for a balance, "duration" for a flow.
    kind: str
    #: "USD", "shares" or "USD/share". Sent so a client formats by what a
    #: figure is rather than guessing from its size.
    unit: str


class ComparisonOut(BaseModel):
    """Several companies' headline figures, side by side."""

    companies: tuple[CompanyMetricsOut, ...]
    #: Every metric in the vocabulary, in display order, so a client renders
    #: the same rows whether or not a given filer reports them.
    metrics: tuple[MetricDescriptorOut, ...]


class BrokenRelationshipOut(BaseModel):
    """A relationship the filer published that does not hold."""

    total: str
    period_end: str
    period_start: str | None = None
    expected: str
    actual: str
    delta: str
    components: int


class ReconciliationOut(BaseModel):
    """A filing checked against the arithmetic its own filer published.

    The denominator belongs to the filer: `evaluated` counts the relationships
    they stated in this filing's calculation linkbase, not a share of anything
    we defined. Counts rather than a percentage -- all 12 relationships holding
    is not the assurance that all 213 is, and a percentage hides that.
    """

    accession: str
    form: str
    held: int
    evaluated: int
    #: Relationships whose terms this filing does not report as consolidated
    #: figures, typically note disclosures carrying dimensional breakdowns.
    unevaluated: int
    #: The filer published no calculation linkbase. Nothing was checked, which
    #: is not the same as everything checking out.
    no_linkbase: bool
    #: EDGAR has not published this filing's XBRL facts yet. The statements
    #: render regardless; the arithmetic cannot be checked until they appear.
    facts_pending: bool
    is_clean: bool
    summary: str
    broken: tuple[BrokenRelationshipOut, ...] = ()


class AsFiledIndexOut(BaseModel):
    """Which statements a filing contains."""

    accession: str
    form: str
    filed: str
    period_end: str | None
    source_url: str
    statements: tuple[dict[str, str], ...]
