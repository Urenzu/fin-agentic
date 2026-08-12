# fin-agentic

Financial statement analysis on an infinite canvas. Drop in a 10-K, get verified
analytics and a chat you can trust with the numbers.

The design premise: **every number the platform shows has been checked against
the accounting identities of the source filing.** A language model extracts
candidate facts and writes prose about them, but never computes a figure and
never supplies one that arithmetic has not corroborated.

See [docs/architecture.md](docs/architecture.md) for how that is enforced.

## Layout

```
services/api/       Python engine: domain model, validation, extraction, agent
  finagentic/
    domain/         concepts, periods, facts, ledger
    validation/     accounting identity checks
    ingest/         PDF parsing            (pending)
    analytics/      ratio engine           (pending)
    store/          Postgres persistence   (pending)
    agent/          chat + grounding       (pending)
  tests/            unit, property, integration, golden
apps/web/           Next.js canvas UI      (pending)
docs/
```

## Getting started

Requires Python 3.12+, Node 22+, Docker.

```bash
# Python engine
cd services/api
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev]"   # Windows
# source .venv/bin/activate && pip install -e ".[dev]"  # macOS / Linux

pytest -q
ruff check finagentic tests
```

Deep property-test run (1500 examples per property, used in CI):

```bash
HYPOTHESIS_PROFILE=deep pytest tests/property
```

Postgres, once persistence lands:

```bash
docker compose up -d      # exposes 5433 to avoid clashing with a local 5432
```

## Current state

| Component | Status |
| --- | --- |
| Concept registry (82 US-GAAP concepts) | done |
| Fact model with enforced provenance | done |
| Period modelling (52/53-week calendars) | done |
| Accounting identity checks (16) | done |
| Verification engine | done |
| PDF ingestion | next |
| Extraction | next |
| Analytics engine | next |
| Canvas UI | next |
| Chat agent | next |

75 tests passing.
