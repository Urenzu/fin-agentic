"""Pipeline orchestration and the in-process entity store.

Ingesting a company means fetching several MB from EDGAR, adapting ~25,000
observations and running the validation layer -- seconds on a cold cache. Doing
that inside a request would make the first load for any ticker feel broken, so
`request_ingest` starts the work and returns immediately; the client polls until
the entity reports `ready`.

The store is in-process for now. Postgres persistence is on the roadmap, and the
interface here is deliberately narrow so swapping the backing store does not
reach into the API layer.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from finagentic.compare.extract import FilingMetrics, metrics_for
from finagentic.config import settings
from finagentic.domain.ledger import FactSet
from finagentic.ingest.edgar import (
    EdgarClient,
    EdgarError,
    Filing,
    Registrant,
    ReportRef,
    UnknownTickerError,
)
from finagentic.ingest.rfiles import AsFiledStatement, parse_statement
from finagentic.ingest.shapes import ShapeAssessment, detect_shape
from finagentic.ingest.xbrl_adapter import AdaptationReport, to_facts
from finagentic.validation.asfiled import FilingReconciliation, reconcile
from finagentic.validation.engine import validate
from finagentic.validation.results import ValidationReport

logger = logging.getLogger(__name__)


@dataclass
class EntityRecord:
    """One company's ingested state."""

    registrant: Registrant
    state: str = "ingesting"
    facts: FactSet = field(default_factory=FactSet)
    shape: ShapeAssessment | None = None
    adaptation: AdaptationReport | None = None
    validation: ValidationReport | None = None
    error: str | None = None

    @property
    def advisories(self) -> tuple[str, ...]:
        """Things the user must be told before trusting what they see.

        Returned with every entity response rather than logged, because both
        conditions here produce output that looks perfectly reasonable while
        being built on the wrong data.
        """
        notes: list[str] = []
        if self.adaptation is not None and self.adaptation.looks_truncated:
            notes.append(
                f"Only {self.adaptation.history_years:.1f} years of filings were "
                f"found for this entity, with {self.adaptation.annual_reports} "
                f"annual reports. A ticker resolves to whichever CIK currently "
                f"holds it, so after a corporate reorganisation it points at the "
                f"new holding company rather than the operating history. The "
                f"longer history may sit under a predecessor CIK."
            )
        if self.shape is not None and not self.shape.is_supported:
            notes.append(self.shape.message)
        return tuple(notes)


class EntityService:
    """Resolves tickers and holds ingested ledgers."""

    def __init__(self, client: EdgarClient | None = None) -> None:
        self._client = client or EdgarClient(
            user_agent=settings.sec_user_agent,
            cache_dir=settings.cache_dir,
        )
        self._records: dict[int, EntityRecord] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        # asyncio holds only a weak reference to a running task, so a task not
        # referenced elsewhere can be garbage-collected mid-flight -- abandoning
        # an ingestion with no error and leaving the entity stuck reporting
        # "ingesting" forever. Keeping strong references until completion is the
        # documented way to prevent that.
        self._in_flight: set[asyncio.Task[None]] = set()

    # ---- lookup -----------------------------------------------------------

    def resolve(self, ticker: str) -> Registrant:
        """Resolve a ticker, raising UnknownTickerError if it is not a filer."""
        return self._client.lookup(ticker)

    def registrant_for_cik(self, cik: int, ticker: str = "") -> Registrant:
        return self._client.registrant_for_cik(cik, ticker)

    def search(self, query: str, limit: int = 10) -> list[Registrant]:
        return self._client.search(query, limit=limit)

    def get(self, cik: int) -> EntityRecord | None:
        return self._records.get(cik)

    # ---- ingestion --------------------------------------------------------

    async def request_ingest(self, registrant: Registrant) -> EntityRecord:
        """Ensure `registrant` is ingested, starting the work if needed.

        Returns immediately. A record already ready or already in flight is
        returned as-is rather than re-fetched.
        """
        existing = self._records.get(registrant.cik)
        if existing is not None and existing.state in ("ready", "ingesting"):
            return existing

        record = EntityRecord(registrant=registrant)
        self._records[registrant.cik] = record

        task = asyncio.create_task(self._ingest(record))
        self._in_flight.add(task)
        task.add_done_callback(self._in_flight.discard)
        return record

    async def ingest_now(self, registrant: Registrant) -> EntityRecord:
        """Ingest synchronously. Used by tests and by CLI tooling."""
        record = self._records.get(registrant.cik)
        if record is not None and record.state == "ready":
            return record
        record = EntityRecord(registrant=registrant)
        self._records[registrant.cik] = record
        await self._ingest(record)
        return record

    async def _ingest(self, record: EntityRecord) -> None:
        lock = self._locks.setdefault(record.registrant.cik, asyncio.Lock())
        async with lock:
            try:
                # The EDGAR client is synchronous and the work is a multi-MB
                # download followed by CPU-bound adaptation, so it runs off the
                # event loop rather than blocking every other request.
                await asyncio.to_thread(_run_pipeline, self._client, record)
                record.state = "ready"
            except EdgarError as exc:
                logger.warning("ingest failed for %s: %s", record.registrant.ticker, exc)
                record.state = "error"
                record.error = str(exc)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("unexpected ingest failure for %s", record.registrant.ticker)
                record.state = "error"
                record.error = f"Unexpected failure during ingestion: {exc}"


def _run_pipeline(client: EdgarClient, record: EntityRecord) -> None:
    """Fetch, adapt and validate. Runs in a worker thread."""
    observations = client.observations(record.registrant)

    # Shape is detected from the raw tag set, before adaptation drops everything
    # the commercial map does not know -- which is exactly the evidence that
    # identifies a non-commercial filer.
    record.shape = detect_shape({o.tag for o in observations})

    facts, adaptation = to_facts(observations, record.registrant)
    verified, validation = validate(facts)

    record.facts = verified
    record.adaptation = adaptation
    record.validation = validation




class AsFiledService:
    """Fetches and parses the SEC's rendered statement exhibits.

    Separate from EntityService because the two answer different questions and
    have different costs. `EntityService` builds a canonical ledger spanning a
    company's whole history, for charts and comparison. This fetches one
    filing's statements as the filer laid them out, for display.
    """

    def __init__(self, client: EdgarClient) -> None:
        self._client = client

    def latest_filing(self, registrant: Registrant, form: str = "10-K") -> Filing | None:
        filings = self._client.recent_filings(
            registrant, forms=frozenset({form}), limit=1
        )
        return filings[0] if filings else None

    def filings(self, registrant: Registrant, form: str = "10-K", limit: int = 10) -> list[Filing]:
        return self._client.recent_filings(registrant, forms=frozenset({form}), limit=limit)

    def statement_index(self, filing: Filing) -> list[ReportRef]:
        """The primary statements in a filing, excluding parentheticals.

        Parenthetical exhibits restate par values and share counts already shown
        on the face, so including them would render the same numbers twice.
        """
        return [
            r
            for r in self._client.filing_reports(filing)
            if r.is_statement and not r.is_parenthetical
        ]

    def statement(self, filing: Filing, report: ReportRef) -> AsFiledStatement:
        return parse_statement(self._client.fetch_report(filing, report))

    def reconciliation(self, registrant: Registrant, filing: Filing) -> FilingReconciliation:
        """Check a filing against the arithmetic its own filer published.

        Per filing and self-contained: no concept vocabulary, no matching
        across companies or periods. The denominator belongs to the filer.
        """
        return reconcile(
            self._client.observations(registrant),
            self._client.calculation_linkbase(filing),
            filing.accession,
        )

    def metrics(self, filing: Filing) -> FilingMetrics:
        """The twelve comparable figures this filing reports.

        Read from the rendered statements, so a filing whose XBRL facts EDGAR
        has not published yet still compares.
        """
        reports = self.statement_index(filing)
        return metrics_for(self.statements(filing, reports), filing.accession, filing.form)

    def statements(self, filing: Filing, reports: list[ReportRef]) -> list[AsFiledStatement]:
        """Every requested exhibit, fetched together.

        The exhibits behind one filing are always wanted as a set, and each was
        costing a round trip of its own. Fetching them concurrently is what
        turns opening a filing from seconds into a moment; parsing stays serial
        because it is microseconds and holds the GIL anyway.
        """
        return [parse_statement(html) for html in self._client.fetch_reports(filing, reports)]


__all__ = ["AsFiledService", "EntityRecord", "EntityService", "UnknownTickerError"]
