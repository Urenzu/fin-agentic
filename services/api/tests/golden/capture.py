"""Capture real EDGAR documents as test fixtures.

Run by hand, never by the test suite:

    FINAGENTIC_SEC_USER_AGENT="you <you@example.com>" \\
        python -m tests.golden.capture

Why fixtures rather than fetching in the test
---------------------------------------------
A golden test exists to fail when *our* code changes, and a test that talks to
sec.gov also fails when the network is slow, when EDGAR is down, and when a
filer amends a filing. Those failures teach people to ignore the suite. The
documents are captured once and committed, so the suite is offline,
deterministic, and fails for exactly one reason.

Gzipped because they are captured, not authored: 420KB of rendered exhibit
becomes 27KB, and nobody reviews an SEC exhibit line by line. The numbers that
*are* reviewed live as literals in the test files, transcribed by hand from the
SEC's own rendered page, so the assertions are independent of the parser that
has to reproduce them.

Refresh only when adding a filing. Re-capturing an existing one and finding a
figure has changed means EDGAR restated it, which is worth reading about before
updating the expectation.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from finagentic.api.service import AsFiledService, EntityService
from finagentic.ingest.linkbase import calculation_filename

FIXTURES = Path(__file__).parent / "fixtures"

#: (name, ticker, form). The set is chosen for the ways filings differ, not for
#: how well known the companies are:
#:
#:   aapl_10k   the ordinary case -- an annual filing, three period columns
#:   aapl_10q   a quarter beside its year to date, which prints the same two
#:              period end dates twice and once collapsed onto itself
#:   tsla_10k   a filer carrying mezzanine equity, where the accounting
#:              equation needs its middle term
CAPTURES = [
    ("aapl_10k", "AAPL", "10-K"),
    ("aapl_10q", "AAPL", "10-Q"),
    ("tsla_10k", "TSLA", "10-K"),
]

#: Fact fixtures, for checking a filing against the arithmetic its filer
#: published. Kept whole rather than trimmed to a list of tags: a calculation
#: linkbase names whichever elements the filer chose, so trimming to a
#: vocabulary of ours would drop exactly the terms a relationship needs -- and
#: would go stale the moment that vocabulary changed, which it did.
FACT_CAPTURES = [("aapl", "AAPL"), ("tsla", "TSLA")]


def _linkbase(service: EntityService, filing) -> str | None:
    """The raw calculation linkbase, if the filing publishes one."""
    summary = service._client._get_text(
        f"{filing.base_url}/FilingSummary.xml",
        cache_key=f"filingsummary_{filing.accession_nodash}",
    )
    name = calculation_filename(summary)
    if name is None:
        return None
    return service._client._get_text(
        f"{filing.base_url}/{name}",
        cache_key=f"calculation_{filing.accession_nodash}",
    )


def _write(name: str, payload: object) -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    path = FIXTURES / f"{name}.json.gz"
    raw = json.dumps(payload, indent=1, sort_keys=True).encode("utf-8")
    path.write_bytes(gzip.compress(raw, 9))
    print(f"  {path.name:28} {len(raw):>9,} -> {path.stat().st_size:>8,}")


def capture_filings(service: EntityService, as_filed: AsFiledService) -> None:
    for name, ticker, form in CAPTURES:
        registrant = service.resolve(ticker)
        filing = as_filed.latest_filing(registrant, form)
        if filing is None:
            raise SystemExit(f"{ticker} has no {form} on EDGAR")
        reports = as_filed.statement_index(filing)
        _write(
            name,
            {
                "registrant": {
                    "cik": registrant.cik,
                    "ticker": registrant.ticker,
                    "name": registrant.name,
                },
                "filing": {
                    "accession": filing.accession,
                    "form": filing.form,
                    "filed": filing.filed.isoformat(),
                    "period_end": filing.period_end.isoformat() if filing.period_end else None,
                    "base_url": filing.base_url,
                },
                "reports": [
                    {"filename": r.filename, "short_name": r.short_name} for r in reports
                ],
                "exhibits": {
                    r.filename: service._client.fetch_report(filing, r) for r in reports
                },
                # The filer's own arithmetic, captured beside the figures it is
                # about. Not every filing has one -- Microsoft's ships none at
                # all -- so its absence is recorded rather than assumed away.
                "calculation_linkbase": _linkbase(service, filing),
            },
        )


def capture_facts(service: EntityService) -> None:
    for name, ticker in FACT_CAPTURES:
        registrant = service.resolve(ticker)
        payload = service._client.company_facts(registrant)
        gaap = payload.get("facts", {}).get("us-gaap", {})
        _write(
            f"{name}_facts",
            {
                "registrant": {
                    "cik": registrant.cik,
                    "ticker": registrant.ticker,
                    "name": registrant.name,
                },
                "facts": {"us-gaap": gaap},
            },
        )


def main() -> None:
    service = EntityService()
    as_filed = AsFiledService(service._client)
    print("capturing filings")
    capture_filings(service, as_filed)
    print("capturing company facts")
    capture_facts(service)


if __name__ == "__main__":
    main()
