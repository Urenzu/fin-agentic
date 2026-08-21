"""HTTP surface.

Deliberately thin: the domain objects already carry the invariants, so these
handlers mostly resolve an entity, call something that already exists, and
reshape the result for transport.

One rule is enforced here rather than left to the client. Every entity and
statement response carries `advisories` and a `shape` with an explicit
`supported` flag. A truncated history and an unsupported statement structure
both produce output that looks entirely reasonable while resting on the wrong
data, so the client is given no shape of response in which those facts are
absent.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from finagentic.api import schemas as s
from finagentic.api.service import (
    AsFiledService,
    EntityRecord,
    EntityService,
    UnknownTickerError,
)
from finagentic.compare.metrics import LABELS, Metric, is_instant, unit
from finagentic.config import settings
from finagentic.domain.concepts import Statement, meta
from finagentic.domain.facts import XbrlProvenance
from finagentic.domain.ledger import FactSet
from finagentic.ingest.edgar import EdgarError, Registrant
from finagentic.presentation.statements import annual_periods, build_statement

app = FastAPI(
    title="fin-agentic",
    version="0.1.0",
    summary="Verified financial statement analysis from SEC filings",
)

# Statement responses are highly repetitive JSON -- the same keys per row, the
# same date strings per column -- and compress by roughly 5x. The threshold
# keeps small responses, like a ticker search, from paying for a compressor
# that would not save a packet.
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#: Comparing more than a handful at once is a screening query, which this
#: endpoint is not, and each company costs a filing fetch.
MAX_COMPARISON = 6

_service = EntityService()
_as_filed_service = AsFiledService(_service._client)


def get_service() -> EntityService:
    return _service


def get_as_filed_service() -> AsFiledService:
    return _as_filed_service


# ---------------------------------------------------------------------------
# conversion
# ---------------------------------------------------------------------------


def _registrant_out(r: Registrant) -> s.RegistrantOut:
    return s.RegistrantOut(cik=r.cik, ticker=r.ticker, name=r.name)


def _shape_out(record: EntityRecord) -> s.ShapeOut | None:
    if record.shape is None:
        return None
    return s.ShapeOut(
        shape=record.shape.shape,
        supported=record.shape.is_supported,
        message=record.shape.message,
        evidence=record.shape.evidence,
    )


def _coverage_out(record: EntityRecord) -> s.CoverageOut | None:
    report = record.adaptation
    if report is None:
        return None
    return s.CoverageOut(
        earliest=report.earliest.isoformat() if report.earliest else None,
        latest=report.latest.isoformat() if report.latest else None,
        history_years=round(report.history_years, 1),
        annual_reports=report.annual_reports,
        looks_truncated=report.looks_truncated,
        fact_count=len(record.facts),
        verified_count=len(record.facts.usable()),
        checks_passed=len(record.validation.passed),
        checks_failed=len(record.validation.failed),
        checks_skipped=len(record.validation.skipped),
    )


def _entity_out(record: EntityRecord) -> s.EntityOut:
    return s.EntityOut(
        registrant=_registrant_out(record.registrant),
        state=record.state,  # type: ignore[arg-type]
        shape=_shape_out(record),
        coverage=_coverage_out(record),
        error=record.error,
        advisories=record.advisories,
    )


def _fact_out(fact: object) -> s.FactOut:
    provenance = fact.provenance  # type: ignore[attr-defined]
    return s.FactOut(
        id=str(fact.id),  # type: ignore[attr-defined]
        concept=fact.concept.value,  # type: ignore[attr-defined]
        label=meta(fact.concept).label,  # type: ignore[attr-defined]
        period_label=fact.period.label,  # type: ignore[attr-defined]
        period_end=fact.period.end_date.isoformat(),  # type: ignore[attr-defined]
        value=format(fact.value, "f"),  # type: ignore[attr-defined]
        unit=fact.unit,  # type: ignore[attr-defined]
        status=fact.status,  # type: ignore[attr-defined]
        source=provenance.source,
        source_url=getattr(provenance, "filing_url", None),
        source_label=(
            provenance.tag
            if isinstance(provenance, XbrlProvenance)
            else getattr(provenance, "row_label", None)
        ),
    )


def _decimal_out(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _require_ready(service: EntityService, cik: int) -> EntityRecord:
    record = service.get(cik)
    if record is None:
        raise HTTPException(404, f"CIK {cik} has not been requested. POST /entities/resolve first.")
    if record.state == "error":
        raise HTTPException(502, record.error or "Ingestion failed.")
    if record.state != "ready":
        # 409 rather than 202: the client asked for a resource that is not yet
        # in a state to be represented, and should poll GET /entities/{cik}.
        raise HTTPException(409, "Still ingesting. Poll GET /entities/{cik} until state is ready.")
    return record


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/entities/search", response_model=s.SearchResultOut)
def search(
    q: str = Query(min_length=1, description="Ticker or company name fragment"),
    limit: int = Query(10, ge=1, le=50),
    service: EntityService = Depends(get_service),
) -> s.SearchResultOut:
    try:
        found = service.search(q, limit=limit)
    except EdgarError as exc:
        raise HTTPException(502, str(exc)) from exc
    return s.SearchResultOut(results=tuple(_registrant_out(r) for r in found))


@app.post("/entities/resolve", response_model=s.EntityOut)
async def resolve(
    ticker: str = Query(min_length=1),
    service: EntityService = Depends(get_service),
) -> s.EntityOut:
    """Resolve a ticker and begin ingestion.

    Returns immediately with `state: ingesting`; poll GET /entities/{cik}.
    Ingestion on a cold cache is several MB of download plus adaptation of tens
    of thousands of observations, which is far too slow to hold a request open.
    """
    try:
        registrant = service.resolve(ticker)
    except UnknownTickerError as exc:
        raise HTTPException(404, str(exc)) from exc
    except EdgarError as exc:
        raise HTTPException(502, str(exc)) from exc

    record = await service.request_ingest(registrant)
    return _entity_out(record)


@app.post("/entities/resolve-cik", response_model=s.EntityOut)
async def resolve_cik(
    cik: int = Query(ge=1),
    ticker: str = Query(""),
    service: EntityService = Depends(get_service),
) -> s.EntityOut:
    """Begin ingestion for a CIK directly.

    Needed to reach entities that no longer hold a ticker -- predecessors of a
    reorganisation, and companies since acquired or delisted, whose filing
    history is often the history the user actually wants.
    """
    try:
        registrant = service.registrant_for_cik(cik, ticker)
    except EdgarError as exc:
        raise HTTPException(502, str(exc)) from exc

    record = await service.request_ingest(registrant)
    return _entity_out(record)


@app.get("/entities/{cik}", response_model=s.EntityOut)
def get_entity(cik: int, service: EntityService = Depends(get_service)) -> s.EntityOut:
    record = service.get(cik)
    if record is None:
        raise HTTPException(404, f"CIK {cik} has not been requested.")
    return _entity_out(record)


@app.get("/entities/{cik}/statements/{statement}", response_model=s.StatementOut)
def get_statement(
    cik: int,
    statement: Statement,
    periods: int = Query(settings.default_periods, ge=1, le=20),
    include_unverified: bool = Query(True),
    service: EntityService = Depends(get_service),
) -> s.StatementOut:
    record = _require_ready(service, cik)

    selected = annual_periods(record.facts, statement, limit=periods)
    view = build_statement(
        record.facts, statement, selected, include_unverified=include_unverified
    )

    shape = _shape_out(record)
    assert shape is not None  # a ready record always carries a shape

    return s.StatementOut(
        statement=view.statement,
        period_labels=view.period_labels,
        lines=tuple(
            s.LineOut(
                concept=line.concept.value,
                label=line.label,
                indent=line.indent,
                is_subtotal=line.is_subtotal,
                unit=line.unit,
                cells={
                    period: s.CellOut(
                        value=format(cell.value, "f"),
                        status=cell.status,
                        verified=cell.is_verified,
                        fact_id=str(cell.fact_id),
                        source_url=cell.source_url,
                        source_label=cell.source_label,
                    )
                    for period, cell in line.cells.items()
                },
            )
            for line in view.lines
        ),
        verified_ratio=round(view.verified_ratio, 4),
        shape=shape,
        advisories=record.advisories,
    )


@app.get("/entities/{cik}/validation", response_model=s.ValidationOut)
def get_validation(
    cik: int,
    status: str | None = Query(None, description="Filter: passed, failed or skipped"),
    service: EntityService = Depends(get_service),
) -> s.ValidationOut:
    record = _require_ready(service, cik)
    report = record.validation
    if report is None:
        raise HTTPException(500, "Entity is ready but carries no validation report.")

    results = report.results
    if status is not None:
        results = tuple(r for r in results if r.status.value == status)

    return s.ValidationOut(
        passed=len(report.passed),
        failed=len(report.failed),
        skipped=len(report.skipped),
        is_clean=report.is_clean,
        results=tuple(
            s.CheckOut(
                check_id=r.check_id,
                identity=r.identity,
                status=r.status,
                severity=r.severity,
                period_label=r.period_label,
                expected=_decimal_out(r.expected),
                actual=_decimal_out(r.actual),
                delta=_decimal_out(r.delta),
                tolerance=_decimal_out(r.tolerance),
                missing=r.missing,
                message=r.message,
            )
            for r in results
        ),
    )


@app.get("/entities/{cik}/facts", response_model=s.FactsOut)
def get_facts(
    cik: int,
    concept: str | None = Query(None),
    period: str | None = Query(None, description="Period label, e.g. FY2024"),
    verified_only: bool = Query(False),
    limit: int = Query(500, ge=1, le=5000),
    service: EntityService = Depends(get_service),
) -> s.FactsOut:
    record = _require_ready(service, cik)

    facts: FactSet = record.facts.usable() if verified_only else record.facts
    selected = [
        f
        for f in facts
        if (concept is None or f.concept.value == concept)
        and (period is None or f.period.label == period)
    ]
    selected.sort(key=lambda f: (f.period.end_date, f.concept.value))

    return s.FactsOut(
        facts=tuple(_fact_out(f) for f in selected[:limit]),
        total=len(selected),
    )


# ---------------------------------------------------------------------------
# as-filed statements
# ---------------------------------------------------------------------------
#
# The canonical statements above impose one shape on every company, which is
# what charts and cross-company comparison need. These render a filing exactly
# as its filer laid it out, which is what a reader recognises -- and it sidesteps
# the coverage problem entirely. Apple's balance sheet carries a $33bn "Vendor
# non-trade receivables" line that no canonical vocabulary would include, and
# every filer has a few such lines. As filed, they simply appear.


def _resolve_registrant(service: EntityService, cik: int) -> Registrant:
    record = service.get(cik)
    if record is not None:
        return record.registrant
    try:
        return service.registrant_for_cik(cik)
    except EdgarError as exc:
        raise HTTPException(502, str(exc)) from exc


def _latest_filing(as_filed: AsFiledService, registrant: Registrant, form: str, accession: str | None):
    if accession is not None:
        for filing in as_filed.filings(registrant, form=form, limit=40):
            if filing.accession == accession:
                return filing
        raise HTTPException(404, f"No {form} with accession {accession} for this filer.")

    filing = as_filed.latest_filing(registrant, form=form)
    if filing is None:
        raise HTTPException(404, f"This filer has no {form} on EDGAR.")
    return filing


@app.get("/entities/{cik}/filings", response_model=tuple[s.AsFiledIndexOut, ...])
def list_filings(
    cik: int,
    form: str = Query("10-K"),
    limit: int = Query(5, ge=1, le=40),
    service: EntityService = Depends(get_service),
    as_filed: AsFiledService = Depends(get_as_filed_service),
) -> tuple[s.AsFiledIndexOut, ...]:
    """Recent filings and the statements each contains."""
    registrant = _resolve_registrant(service, cik)
    try:
        filings = as_filed.filings(registrant, form=form, limit=limit)
        return tuple(
            s.AsFiledIndexOut(
                accession=f.accession,
                form=f.form,
                filed=f.filed.isoformat(),
                period_end=f.period_end.isoformat() if f.period_end else None,
                source_url=f.index_url,
                statements=tuple(
                    {"filename": r.filename, "name": r.short_name}
                    for r in as_filed.statement_index(f)
                ),
            )
            for f in filings
        )
    except EdgarError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/compare", response_model=s.ComparisonOut)
def compare(
    tickers: str = Query(description="Comma-separated, e.g. AAPL,MSFT,NVDA"),
    form: str = Query("10-K"),
    service: EntityService = Depends(get_service),
    as_filed: AsFiledService = Depends(get_as_filed_service),
) -> s.ComparisonOut:
    """Headline figures for several companies, from each one's latest filing.

    The only place in this system that decides two companies' lines correspond.
    Everything else is per filing and needs no such judgement; comparison
    cannot avoid it, so it is confined here and kept to twelve metrics whose
    aliases are few and whose errors are visible.
    """
    wanted = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not wanted:
        raise HTTPException(400, "Give at least one ticker.")
    if len(wanted) > MAX_COMPARISON:
        raise HTTPException(
            400, f"At most {MAX_COMPARISON} companies at once; asked for {len(wanted)}."
        )

    companies: list[s.CompanyMetricsOut] = []
    for ticker in wanted:
        try:
            registrant = service.resolve(ticker)
            filing = as_filed.latest_filing(registrant, form)
            if filing is None:
                raise HTTPException(404, f"{ticker} has no {form} on EDGAR.")
            found = as_filed.metrics(filing)
        except UnknownTickerError as exc:
            raise HTTPException(404, str(exc)) from exc
        except EdgarError as exc:
            raise HTTPException(502, str(exc)) from exc

        companies.append(
            s.CompanyMetricsOut(
                registrant=_registrant_out(registrant),
                accession=filing.accession,
                form=filing.form,
                filed=filing.filed.isoformat(),
                period_end=filing.period_end.isoformat() if filing.period_end else None,
                metrics={
                    metric.value: tuple(
                        s.MetricValueOut(
                            metric=p.metric.value,
                            label=LABELS[p.metric],
                            value=format(p.value, "f"),
                            element=p.element,
                            period_label=p.label,
                            period_end=p.end_date.isoformat() if p.end_date else None,
                            duration=p.duration,
                        )
                        for p in periods
                    )
                    for metric, periods in found.periods.items()
                },
                absent=tuple(m.value for m in Metric if m not in found.periods),
            )
        )

    return s.ComparisonOut(
        companies=tuple(companies),
        metrics=tuple(
            s.MetricDescriptorOut(
                metric=m.value,
                label=LABELS[m],
                kind="instant" if is_instant(m) else "duration",
                unit=unit(m),
            )
            for m in Metric
        ),
    )


@app.get("/entities/{cik}/reconciliation", response_model=s.ReconciliationOut)
def get_reconciliation(
    cik: int,
    form: str = Query("10-K"),
    accession: str | None = Query(None, description="Defaults to the most recent filing"),
    service: EntityService = Depends(get_service),
    as_filed: AsFiledService = Depends(get_as_filed_service),
) -> s.ReconciliationOut:
    """Check one filing against the arithmetic its own filer published.

    Self-contained: no concept vocabulary, no comparison across companies or
    periods. Whether a filing agrees with itself is a question the filing can
    answer on its own, and the calculation linkbase is the filer saying how.
    """
    registrant = _resolve_registrant(service, cik)
    try:
        filing = _latest_filing(as_filed, registrant, form, accession)
        result = as_filed.reconciliation(registrant, filing)
    except EdgarError as exc:
        raise HTTPException(502, str(exc)) from exc

    return s.ReconciliationOut(
        accession=filing.accession,
        form=filing.form,
        held=result.held,
        evaluated=result.evaluated,
        unevaluated=len(result.unevaluated),
        no_linkbase=result.no_linkbase,
        facts_pending=result.facts_pending,
        is_clean=result.is_clean,
        summary=result.summary,
        broken=tuple(
            s.BrokenRelationshipOut(
                total=r.total_element,
                period_end=r.period_end.isoformat(),
                period_start=r.period_start.isoformat() if r.period_start else None,
                expected=format(r.expected, "f"),
                actual=format(r.actual, "f"),
                delta=format(r.delta, "f"),
                components=r.components,
            )
            for r in result.broken
        ),
    )


@app.get("/entities/{cik}/as-filed", response_model=tuple[s.AsFiledStatementOut, ...])
def get_as_filed(
    cik: int,
    form: str = Query("10-K"),
    accession: str | None = Query(None, description="Defaults to the most recent filing"),
    service: EntityService = Depends(get_service),
    as_filed: AsFiledService = Depends(get_as_filed_service),
) -> tuple[s.AsFiledStatementOut, ...]:
    """Every primary statement in a filing, exactly as the filer presented it."""
    registrant = _resolve_registrant(service, cik)
    try:
        filing = _latest_filing(as_filed, registrant, form, accession)
        reports = as_filed.statement_index(filing)
        statements = as_filed.statements(filing, reports)
        return tuple(
            _as_filed_out(statement, report, filing)
            for statement, report in zip(statements, reports, strict=True)
        )
    except EdgarError as exc:
        raise HTTPException(502, str(exc)) from exc


def _as_filed_out(statement, report, filing) -> s.AsFiledStatementOut:
    return s.AsFiledStatementOut(
        title=statement.title,
        # The exhibit's own title, not FilingSummary's ShortName, which the
        # SEC's renderer sometimes emits with characters already replaced by
        # question marks.
        short_name=statement.display_name or report.short_name,
        columns=tuple(
            s.AsFiledColumnOut(
                key=column.key,
                label=column.label,
                duration=column.duration,
                date=column.date.isoformat() if column.date else None,
            )
            for column in statement.columns
        ),
        rows=tuple(
            s.AsFiledRowOut(
                label=row.label,
                element=row.element,
                tag=row.tag,
                is_abstract=row.is_abstract,
                is_total=row.is_total,
                indent=row.indent,
                values={col: format(val, "f") for col, val in row.values.items()},
            )
            for row in statement.rows
        ),
        monetary_scale=format(statement.monetary_scale, "f"),
        share_scale=format(statement.share_scale, "f"),
        accession=filing.accession,
        form=filing.form,
        filed=filing.filed.isoformat(),
        source_url=f"{filing.base_url}/{report.filename}",
    )
