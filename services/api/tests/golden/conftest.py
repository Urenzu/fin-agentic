"""Loading captured EDGAR documents.

The fixtures are real filings, captured by `tests/golden/capture.py`. Nothing
here reaches the network: a golden test must fail for exactly one reason, and
"sec.gov was slow" is not it.
"""

from __future__ import annotations

import gzip
import json
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from finagentic.ingest.edgar import EdgarClient, Filing, Registrant, ReportRef
from finagentic.ingest.rfiles import AsFiledStatement, parse_statement

FIXTURES = Path(__file__).parent / "fixtures"


@cache
def load(name: str) -> dict[str, Any]:
    path = FIXTURES / f"{name}.json.gz"
    if not path.exists():
        raise AssertionError(
            f"missing fixture {path.name}. Regenerate with "
            f"`python -m tests.golden.capture` (needs FINAGENTIC_SEC_USER_AGENT)."
        )
    payload: dict[str, Any] = json.loads(gzip.decompress(path.read_bytes()))
    return payload


class CapturedFiling:
    """One filing's exhibits, parsed on demand."""

    def __init__(self, name: str) -> None:
        self.raw = load(name)
        self.accession: str = self.raw["filing"]["accession"]
        self.form: str = self.raw["filing"]["form"]

    def statement(self, fragment: str) -> AsFiledStatement:
        """The parsed statement whose name contains `fragment`, case-insensitively."""
        matches = [
            report
            for report in self.raw["reports"]
            if fragment.lower() in report["short_name"].lower()
        ]
        if len(matches) != 1:
            names = [r["short_name"] for r in self.raw["reports"]]
            raise AssertionError(f"{fragment!r} matched {len(matches)} of {names}")
        return parse_statement(self.raw["exhibits"][matches[0]["filename"]])


#: Test-side scale constants. Deliberately *not* `statement.monetary_scale`:
#: dividing an expectation by the parser's own multiplier cancels the error out,
#: so a scale read as thousands instead of millions -- a silent factor of a
#: thousand, the worst failure this file can have -- would still pass. Mutating
#: the parser to prove it is how that hole was found.
MILLIONS = Decimal(10) ** 6
THOUSANDS = Decimal(10) ** 3


def figure(
    statement: AsFiledStatement, label: str, column: int, occurrence: int = 0
) -> Decimal:
    """The value stored on `label`'s row in the nth column, at full scale.

    Returned exactly as the ledger holds it, so a test writes its expectation
    as the digits on the page times a scale constant of its own.

    A label can repeat: Apple's income statement prints "Net sales" for the
    total and again under each of Products and Services. `occurrence` picks
    between them in the order the statement prints, so the default is the one a
    reader means -- statements put their totals first.
    """
    rows = [r for r in statement.rows if r.label.strip().lower() == label.strip().lower()]
    if len(rows) <= occurrence:
        found = [r.label for r in statement.rows if not r.is_abstract][:40]
        raise AssertionError(
            f"{label!r} occurrence {occurrence} not found "
            f"({len(rows)} matched); statement has {found}"
        )

    key = statement.columns[column].key
    raw = rows[occurrence].values.get(key)
    if raw is None:
        raise AssertionError(f"{label!r} has no value in column {column}")
    return raw


class CapturedFactsClient(EdgarClient):
    """An EdgarClient whose company facts come from a captured payload.

    Subclassed rather than mocked so everything downstream -- observation
    parsing, adaptation, reconciliation, validation -- runs for real against
    numbers a filer actually submitted.
    """

    def __init__(self, name: str) -> None:
        self._payload = load(name)
        info = self._payload["registrant"]
        self._registrant = Registrant(cik=info["cik"], ticker=info["ticker"], name=info["name"])

    @property
    def registrant(self) -> Registrant:
        return self._registrant

    def lookup(self, ticker: str) -> Registrant:
        return self._registrant

    def registrant_for_cik(self, cik: int, ticker: str = "") -> Registrant:
        return self._registrant

    def company_facts(self, registrant: Registrant) -> dict[str, Any]:
        return self._payload

    def recent_filings(self, *args: object, **kwargs: object) -> list[Filing]:
        return []

    def filing_reports(self, filing: Filing) -> list[ReportRef]:
        return []


@pytest.fixture(scope="session")
def aapl_10k() -> CapturedFiling:
    return CapturedFiling("aapl_10k")


@pytest.fixture(scope="session")
def aapl_10q() -> CapturedFiling:
    return CapturedFiling("aapl_10q")


@pytest.fixture(scope="session")
def tsla_10k() -> CapturedFiling:
    return CapturedFiling("tsla_10k")
