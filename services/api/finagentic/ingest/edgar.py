"""SEC EDGAR client.

Talks to the public XBRL APIs at data.sec.gov. No API key exists or is needed;
the SEC requires only a descriptive User-Agent identifying who is calling, and
asks that clients stay under 10 requests/second.

Endpoints used
--------------
company_tickers.json    ticker -> CIK mapping for every registrant
companyfacts/CIK…json   every us-gaap fact the filer has ever tagged

`companyfacts` is the workhorse. It returns a filer's complete tagged history in
one request -- typically 3-4MB and 400-600 distinct concepts covering 2009 to
the present. Responses are cached on disk because they change only when the
company files, which is quarterly at most.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

SEC_BASE = "https://www.sec.gov"
SEC_DATA_BASE = "https://data.sec.gov"

#: The SEC blocks clients that do not identify themselves. This must name a real
#: contact -- see https://www.sec.gov/os/webmaster-faq#developers
DEFAULT_USER_AGENT = "fin-agentic (contact: levirankin1@gmail.com)"

#: SEC asks for no more than 10 requests/second. We stay well under.
MIN_REQUEST_INTERVAL_SECONDS = 0.15


class EdgarError(RuntimeError):
    """Raised when EDGAR cannot satisfy a request."""


class UnknownTickerError(EdgarError):
    def __init__(self, ticker: str) -> None:
        super().__init__(
            f"{ticker!r} is not a registrant in SEC EDGAR. Only companies that "
            f"file with the SEC are covered; private and most foreign issuers "
            f"are not."
        )
        self.ticker = ticker


@dataclass(frozen=True, slots=True)
class Registrant:
    """A company as EDGAR knows it."""

    cik: int
    ticker: str
    name: str

    @property
    def cik10(self) -> str:
        """Zero-padded CIK, the form the API paths require."""
        return f"CIK{self.cik:010d}"


@dataclass(frozen=True, slots=True)
class XbrlObservation:
    """One reported value, exactly as EDGAR returned it.

    Deliberately a faithful mirror of the source JSON rather than a domain
    object: mapping onto a canonical `Concept`, deciding periods and resolving
    restatements all happen downstream in the adapter, where the decisions can
    be tested independently of the network.
    """

    tag: str
    unit: str
    value: Decimal
    #: End of the reported period, or the measurement date for an instant.
    end: date
    #: Start of the period. Absent for instants (balance sheet items).
    start: date | None
    #: Fiscal year and period the filing assigned. May be None on older filings.
    fiscal_year: int | None
    fiscal_period: str | None
    form: str
    accession: str
    filed: date
    #: Present only when the value pertains to a segment or other dimensional
    #: breakout rather than the consolidated total.
    frame: str | None

    @property
    def is_instant(self) -> bool:
        return self.start is None


class EdgarClient:
    """Cached, rate-limited access to the EDGAR XBRL APIs."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        cache_dir: Path | None = None,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
        self._cache_dir = cache_dir
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout, headers=self._headers)
        self._last_request_at = 0.0
        self._tickers: dict[str, Registrant] | None = None

        if self._cache_dir is not None:
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    def __enter__(self) -> EdgarClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # ---- HTTP ------------------------------------------------------------

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
            time.sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)
        self._last_request_at = time.monotonic()

    def _get_json(self, url: str, *, cache_key: str | None = None) -> dict[str, Any]:
        cache_path = (
            self._cache_dir / f"{cache_key}.json"
            if self._cache_dir is not None and cache_key
            else None
        )
        if cache_path is not None and cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))

        self._throttle()
        try:
            response = self._client.get(url, headers=self._headers)
        except httpx.HTTPError as exc:
            raise EdgarError(f"request to {url} failed: {exc}") from exc

        if response.status_code == 404:
            raise EdgarError(f"EDGAR has no data at {url}")
        if response.status_code == 403:
            raise EdgarError(
                "EDGAR rejected the request (403). This is almost always a "
                "missing or non-descriptive User-Agent header."
            )
        if response.status_code != 200:
            raise EdgarError(f"EDGAR returned {response.status_code} for {url}")

        payload: dict[str, Any] = response.json()
        if cache_path is not None:
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload

    # ---- registrants ------------------------------------------------------

    def _load_tickers(self) -> dict[str, Registrant]:
        if self._tickers is not None:
            return self._tickers

        payload = self._get_json(
            f"{SEC_BASE}/files/company_tickers.json", cache_key="company_tickers"
        )
        # The payload is a dict keyed by row index, not a list.
        registrants: dict[str, Registrant] = {}
        for row in payload.values():
            ticker = str(row["ticker"]).upper()
            registrants[ticker] = Registrant(
                cik=int(row["cik_str"]),
                ticker=ticker,
                name=str(row["title"]),
            )
        self._tickers = registrants
        return registrants

    def lookup(self, ticker: str) -> Registrant:
        """Resolve a ticker to its registrant, or raise UnknownTickerError."""
        registrants = self._load_tickers()
        try:
            return registrants[ticker.strip().upper()]
        except KeyError:
            raise UnknownTickerError(ticker) from None

    def search(self, query: str, limit: int = 10) -> list[Registrant]:
        """Find registrants whose ticker or name matches `query`."""
        q = query.strip().upper()
        if not q:
            return []
        registrants = self._load_tickers()

        exact = [r for r in registrants.values() if r.ticker == q]
        prefix = [r for r in registrants.values() if r.ticker.startswith(q) and r.ticker != q]
        by_name = [
            r
            for r in registrants.values()
            if q in r.name.upper() and r not in exact and r not in prefix
        ]
        return [*exact, *prefix, *by_name][:limit]

    # ---- facts ------------------------------------------------------------

    def company_facts(self, registrant: Registrant) -> dict[str, Any]:
        """Fetch the raw companyfacts payload for a registrant."""
        return self._get_json(
            f"{SEC_DATA_BASE}/api/xbrl/companyfacts/{registrant.cik10}.json",
            cache_key=f"companyfacts_{registrant.cik10}",
        )

    def observations(self, registrant: Registrant) -> list[XbrlObservation]:
        """Fetch and flatten every us-gaap observation for a registrant.

        Only the `us-gaap` taxonomy is read. Filers may also submit `dei`
        (entity metadata) and company-specific extension taxonomies; extensions
        are by definition non-standard and cannot be mapped onto a shared
        concept vocabulary, so they are skipped rather than guessed at.
        """
        payload = self.company_facts(registrant)
        gaap = payload.get("facts", {}).get("us-gaap", {})

        observations: list[XbrlObservation] = []
        for tag, body in gaap.items():
            for unit, rows in body.get("units", {}).items():
                for row in rows:
                    parsed = _parse_observation(tag, unit, row)
                    if parsed is not None:
                        observations.append(parsed)
        return observations


def _parse_observation(tag: str, unit: str, row: dict[str, Any]) -> XbrlObservation | None:
    """Convert one raw JSON row into an observation, or None if unusable.

    Rows missing an end date, a value or an accession cannot be placed in the
    ledger and are dropped here rather than failing further downstream where the
    cause would be harder to see.
    """
    try:
        end = date.fromisoformat(row["end"])
        raw_value = row["val"]
        accession = row["accn"]
        filed = date.fromisoformat(row["filed"])
    except (KeyError, TypeError, ValueError):
        return None

    if raw_value is None:
        return None

    start_raw = row.get("start")
    try:
        start = date.fromisoformat(start_raw) if start_raw else None
    except (TypeError, ValueError):
        start = None

    # str() first: passing a float to Decimal would bake in binary rounding
    # error at the very boundary the ledger exists to keep exact.
    try:
        value = Decimal(str(raw_value))
    except (TypeError, ArithmeticError):
        return None

    return XbrlObservation(
        tag=tag,
        unit=unit,
        value=value,
        end=end,
        start=start,
        fiscal_year=row.get("fy"),
        fiscal_period=row.get("fp"),
        form=str(row.get("form", "")),
        accession=str(accession),
        filed=filed,
        frame=row.get("frame"),
    )
