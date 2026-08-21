"""HTTP surface, end to end over a fake EDGAR client.

The client is faked rather than mocked at the request level so the whole
pipeline still runs: adaptation, validation and statement building all execute
against realistic observations. Only the network is replaced.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from finagentic.api.app import app, get_service
from finagentic.api.service import EntityService
from finagentic.ingest.edgar import EdgarClient, Registrant, UnknownTickerError, XbrlObservation

APPLE = Registrant(cik=320193, ticker="AAPL", name="Apple Inc.")
BANK = Registrant(cik=19617, ticker="JPM", name="JPMORGAN CHASE & CO")

#: Four fiscal years, so the fixture is not flagged as a truncated history --
#: the same check that catches a ticker resolving to a post-reorganisation
#: holding company would otherwise fire on a two-year test fixture.
FISCAL_YEARS = [
    ("2020-09-27", "2021-09-25"),
    ("2021-09-26", "2022-09-24"),
    ("2022-09-25", "2023-09-30"),
    ("2023-10-01", "2024-09-28"),
]


def _obs(
    tag: str,
    value: str,
    *,
    end: str,
    start: str | None = None,
    unit: str = "USD",
    fy: int = 2024,
    fp: str = "FY",
) -> XbrlObservation:
    return XbrlObservation(
        tag=tag,
        unit=unit,
        value=Decimal(value),
        end=date.fromisoformat(end),
        start=date.fromisoformat(start) if start else None,
        fiscal_year=fy,
        fiscal_period=fp,
        form="10-K",
        accession="0000320193-24-000123",
        filed=date(2024, 11, 1),
        frame="CY2024",
    )


def _commercial_observations() -> list[XbrlObservation]:
    """A small but internally consistent filing: 14,000 = 8,000 + 6,000."""
    out: list[XbrlObservation] = []
    for start, end in FISCAL_YEARS:
        out += [
            _obs("RevenueFromContractWithCustomerExcludingAssessedTax", "10000", start=start, end=end),
            _obs("CostOfGoodsAndServicesSold", "4000", start=start, end=end),
            _obs("GrossProfit", "6000", start=start, end=end),
            _obs("ResearchAndDevelopmentExpense", "1500", start=start, end=end),
            _obs("SellingGeneralAndAdministrativeExpense", "2500", start=start, end=end),
            _obs("OperatingExpenses", "4000", start=start, end=end),
            _obs("OperatingIncomeLoss", "2000", start=start, end=end),
            _obs("IncomeTaxExpenseBenefit", "400", start=start, end=end),
            _obs("NetIncomeLoss", "1600", start=start, end=end),
        ]
    for _, end in FISCAL_YEARS:
        out += [
            _obs("Assets", "14000", end=end),
            _obs("AssetsCurrent", "6400", end=end),
            _obs("CashAndCashEquivalentsAtCarryingValue", "2500", end=end),
            _obs("InventoryNet", "800", end=end),
            _obs("Liabilities", "8000", end=end),
            _obs("LiabilitiesCurrent", "4000", end=end),
            _obs("StockholdersEquity", "6000", end=end),
            _obs("MinorityInterest", "0", end=end),
            _obs("LiabilitiesAndStockholdersEquity", "14000", end=end),
        ]
    return out


def _bank_observations() -> list[XbrlObservation]:
    """No classified balance sheet; the defining bank markers instead."""
    out: list[XbrlObservation] = []
    for _, end in FISCAL_YEARS:
        out += [
            _obs("Assets", "3666000", end=end),
            _obs("Liabilities", "3374000", end=end),
            _obs("StockholdersEquity", "292000", end=end),
            _obs("Deposits", "2401000", end=end),
        ]
    for start, end in FISCAL_YEARS:
        out += [
            _obs("InterestIncomeExpenseNet", "66700", start=start, end=end),
            _obs("NoninterestIncome", "62000", start=start, end=end),
            _obs("NoninterestExpense", "76100", start=start, end=end),
            _obs("ProvisionForLoanLeaseAndOtherLosses", "6400", start=start, end=end),
            _obs("InterestAndFeeIncomeLoansAndLeases", "104000", start=start, end=end),
        ]
    return out


class FakeEdgarClient(EdgarClient):
    """An EdgarClient with the network replaced."""

    def __init__(self) -> None:
        self._registrants = {"AAPL": APPLE, "JPM": BANK}
        self._observations = {
            APPLE.cik: _commercial_observations(),
            BANK.cik: _bank_observations(),
        }

    def lookup(self, ticker: str) -> Registrant:
        try:
            return self._registrants[ticker.strip().upper()]
        except KeyError:
            raise UnknownTickerError(ticker) from None

    def registrant_for_cik(self, cik: int, ticker: str = "") -> Registrant:
        for r in self._registrants.values():
            if r.cik == cik:
                return r
        return Registrant(cik=cik, ticker=ticker, name=f"CIK {cik}")

    def search(self, query: str, limit: int = 10) -> list[Registrant]:
        q = query.upper()
        return [r for r in self._registrants.values() if q in r.ticker or q in r.name.upper()][:limit]

    def observations(self, registrant: Registrant) -> list[XbrlObservation]:
        return self._observations.get(registrant.cik, [])


@pytest.fixture
def client():
    service = EntityService(client=FakeEdgarClient())
    app.dependency_overrides[get_service] = lambda: service
    with TestClient(app) as c:
        c.service = service  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()


def _ingest(client, ticker: str) -> dict:
    """Resolve and wait for ingestion, as a real client would by polling."""
    resolved = client.post("/entities/resolve", params={"ticker": ticker})
    assert resolved.status_code == 200, resolved.text
    cik = resolved.json()["registrant"]["cik"]

    for _ in range(50):
        entity = client.get(f"/entities/{cik}").json()
        if entity["state"] != "ingesting":
            return entity
    raise AssertionError("ingestion did not settle")


# ---------------------------------------------------------------------------
# resolution
# ---------------------------------------------------------------------------


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_resolve_returns_immediately_without_blocking_on_ingestion(client):
    body = client.post("/entities/resolve", params={"ticker": "AAPL"}).json()
    assert body["registrant"]["cik"] == APPLE.cik
    assert body["state"] in ("ingesting", "ready")


def test_an_unknown_ticker_is_a_404_explaining_the_coverage_limit(client):
    response = client.post("/entities/resolve", params={"ticker": "NOTREAL"})
    assert response.status_code == 404
    assert "file with the SEC" in response.json()["detail"]


def test_ingestion_completes_and_reports_ready(client):
    entity = _ingest(client, "AAPL")
    assert entity["state"] == "ready"
    assert entity["coverage"]["fact_count"] > 0


def test_search_finds_by_ticker(client):
    results = client.get("/entities/search", params={"q": "AAPL"}).json()["results"]
    assert results[0]["ticker"] == "AAPL"


def test_a_cik_can_be_addressed_directly(client):
    """Predecessor entities hold filing history but no longer hold a ticker."""
    response = client.post("/entities/resolve-cik", params={"cik": 34088, "ticker": "XOM"})
    assert response.status_code == 200
    assert response.json()["registrant"]["cik"] == 34088


# ---------------------------------------------------------------------------
# statements
# ---------------------------------------------------------------------------


def test_statements_are_unavailable_until_ingestion_finishes(client):
    """A half-ingested ledger must not be rendered as though it were complete."""
    from finagentic.api.service import EntityRecord

    service = client.service  # type: ignore[attr-defined]
    service._records[APPLE.cik] = EntityRecord(registrant=APPLE, state="ingesting")

    response = client.get(f"/entities/{APPLE.cik}/statements/income_statement")
    assert response.status_code == 409
    assert "Poll" in response.json()["detail"]


def test_an_unrequested_entity_is_a_404(client):
    assert client.get("/entities/999999/statements/income_statement").status_code == 404


def test_the_income_statement_renders_in_order(client):
    _ingest(client, "AAPL")
    body = client.get(f"/entities/{APPLE.cik}/statements/income_statement").json()

    concepts = [line["concept"] for line in body["lines"]]
    assert concepts.index("Revenue") < concepts.index("GrossProfit")
    assert concepts.index("GrossProfit") < concepts.index("OperatingIncomeLoss")


def test_statement_values_cross_the_wire_as_strings(client):
    """A JSON number is parsed as an IEEE double by every JavaScript client."""
    _ingest(client, "AAPL")
    body = client.get(f"/entities/{APPLE.cik}/statements/income_statement").json()

    revenue = next(line for line in body["lines"] if line["concept"] == "Revenue")
    cell = next(iter(revenue["cells"].values()))
    assert isinstance(cell["value"], str)
    assert cell["value"] == "10000"


def test_statement_cells_carry_verification_and_source(client):
    _ingest(client, "AAPL")
    body = client.get(f"/entities/{APPLE.cik}/statements/income_statement").json()

    revenue = next(line for line in body["lines"] if line["concept"] == "Revenue")
    cell = next(iter(revenue["cells"].values()))
    assert "verified" in cell
    assert cell["source_label"] == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert cell["source_url"].startswith("https://www.sec.gov/Archives/")


def test_multiple_periods_render_as_columns(client):
    _ingest(client, "AAPL")
    body = client.get(
        f"/entities/{APPLE.cik}/statements/income_statement", params={"periods": 5}
    ).json()
    assert len(body["period_labels"]) == len(FISCAL_YEARS)


def test_the_balance_sheet_uses_instants(client):
    _ingest(client, "AAPL")
    body = client.get(f"/entities/{APPLE.cik}/statements/balance_sheet").json()
    concepts = {line["concept"] for line in body["lines"]}

    assert "Assets" in concepts
    assert "Revenue" not in concepts


def test_unverified_values_can_be_excluded(client):
    _ingest(client, "AAPL")
    full = client.get(f"/entities/{APPLE.cik}/statements/balance_sheet").json()
    trimmed = client.get(
        f"/entities/{APPLE.cik}/statements/balance_sheet",
        params={"include_unverified": False},
    ).json()
    assert len(trimmed["lines"]) <= len(full["lines"])


# ---------------------------------------------------------------------------
# the guarantees the client must not be able to ignore
# ---------------------------------------------------------------------------


def test_a_bank_is_flagged_unsupported_on_the_entity(client):
    entity = _ingest(client, "JPM")
    assert entity["shape"]["shape"] == "bank"
    assert entity["shape"]["supported"] is False


def test_a_bank_advisory_reaches_the_client_and_explains_itself(client):
    entity = _ingest(client, "JPM")
    advisory = " ".join(entity["advisories"])

    assert "bank" in advisory
    assert "operating cycle" in advisory


def test_the_shape_is_repeated_on_every_statement_response(client):
    """The client must have no shape of response in which this is absent."""
    _ingest(client, "JPM")
    body = client.get(f"/entities/{BANK.cik}/statements/balance_sheet").json()

    assert body["shape"]["supported"] is False
    assert body["advisories"]


def test_a_commercial_filer_is_marked_supported(client):
    entity = _ingest(client, "AAPL")
    assert entity["shape"]["shape"] == "commercial"
    assert entity["shape"]["supported"] is True
    assert entity["advisories"] == []


# ---------------------------------------------------------------------------
# validation and facts
# ---------------------------------------------------------------------------


def test_validation_reports_the_identity_checks(client):
    _ingest(client, "AAPL")
    body = client.get(f"/entities/{APPLE.cik}/validation").json()

    assert body["passed"] > 0
    assert body["is_clean"] is True
    assert any(r["check_id"] == "bs.balances" for r in body["results"])


def test_validation_can_be_filtered_by_status(client):
    _ingest(client, "AAPL")
    body = client.get(f"/entities/{APPLE.cik}/validation", params={"status": "failed"}).json()
    assert all(r["status"] == "failed" for r in body["results"])


def test_check_results_expose_the_arithmetic(client):
    """A reconciliation panel needs the numbers, not just a verdict."""
    _ingest(client, "AAPL")
    body = client.get(f"/entities/{APPLE.cik}/validation").json()
    balances = next(r for r in body["results"] if r["check_id"] == "bs.balances")

    assert balances["expected"] == "14000"
    assert balances["identity"] == "Assets = Liabilities + Temporary equity + Equity"


def test_facts_are_listable_and_filterable(client):
    _ingest(client, "AAPL")
    body = client.get(
        f"/entities/{APPLE.cik}/facts", params={"concept": "Revenue"}
    ).json()

    assert body["total"] == len(FISCAL_YEARS)
    assert all(f["concept"] == "Revenue" for f in body["facts"])


def test_facts_carry_provenance(client):
    _ingest(client, "AAPL")
    body = client.get(f"/entities/{APPLE.cik}/facts", params={"concept": "Assets"}).json()
    fact = body["facts"][0]

    assert fact["source"] == "xbrl"
    assert fact["source_url"].startswith("https://www.sec.gov/Archives/")
    assert fact["source_label"] == "Assets"


def test_facts_can_be_restricted_to_verified(client):
    _ingest(client, "AAPL")
    body = client.get(
        f"/entities/{APPLE.cik}/facts", params={"verified_only": True}
    ).json()
    assert all(f["status"] == "verified" for f in body["facts"])
