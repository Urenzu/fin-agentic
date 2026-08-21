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
from finagentic.ingest.tag_map import TAG_TO_CONCEPT

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

#: Ledger fixtures. Trimmed to the tags the concept vocabulary carries, which
#: takes 4.2MB of companyfacts down to 115KB gzipped without changing any
#: number the ledger would have seen.
FACT_CAPTURES = [("aapl", "AAPL"), ("tsla", "TSLA")]


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
                # Only mapped tags. An unmapped tag cannot reach the ledger, so
                # keeping it would inflate the fixture without changing a
                # single assertion. The coverage test reads exhibits, not this.
                "facts": {"us-gaap": {t: b for t, b in gaap.items() if t in TAG_TO_CONCEPT}},
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
