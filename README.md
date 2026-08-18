# fin-agentic

Financial statement analysis on an infinite canvas. Search a ticker, get its
statements straight from SEC EDGAR — rendered exactly as the filer laid them
out, with a link to the exhibit every number came from.

Two layers, with different jobs:

- **As-filed** is the display path. Each filing's statements are parsed from the
  SEC's own rendered exhibits, so the line order, labels and hierarchy are the
  filer's. This is also the provenance click-through: the same exhibit the
  number came from.
- **The canonical ledger** is the analytics path. One consistent shape across
  every company, which charts, time series and cross-company comparison need and
  as-filed rows cannot provide. Every fact carries typed provenance and is
  checked against the accounting identities of its filing.

See [docs/architecture.md](docs/architecture.md) for how that is enforced.

## Layout

```
services/api/       Python engine
  finagentic/
    domain/         concepts, periods, facts, ledger
    validation/     accounting identity checks
    ingest/         EDGAR client, XBRL adapter, as-filed exhibit parser
    presentation/   canonical statement views
    api/            FastAPI surface
  tests/            unit, property, integration
apps/web/           Next.js canvas UI
  app/ components/  the board, nodes, search
  lib/              API client, exact decimal formatting, viewport framing
docs/
```

## Getting started

Requires Python 3.12+, Node 22+.

```bash
# Python engine
cd services/api
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev]"   # Windows
# source .venv/bin/activate && pip install -e ".[dev]"  # macOS / Linux

pytest -q
ruff check finagentic tests

./.venv/Scripts/python.exe -m uvicorn finagentic.api.app:app --reload
```

```bash
# Canvas UI, in a second shell
cd apps/web
npm install
npm run dev          # http://localhost:3000
npm test             # exact-decimal and viewport arithmetic
npm run typecheck && npm run lint
```

No API key is needed. EDGAR asks only that requests identify themselves and
that they stay under ten a second, which the client throttles to. Set your own
contact address before fetching -- the SEC blocks clients that do not name one:

```bash
export FINAGENTIC_SEC_USER_AGENT="fin-agentic (contact: you@example.com)"
```

> Do not run `next build` while `next dev` is running — they share `.next/`, and
> the build leaves the dev server serving chunks that no longer exist, so the
> page loads but never hydrates.

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
| Concept registry (85 US-GAAP concepts) | done |
| Fact model with enforced provenance | done |
| Period modelling (52/53-week calendars) | done |
| Accounting identity checks (17) | done |
| EDGAR ingestion + XBRL adaptation (122 tags mapped) | done |
| As-filed statement rendering | done |
| FastAPI surface | done |
| Canvas UI: ticker search, statement nodes | done |
| Analytics engine | next |
| Postgres persistence | next |
| PDF ingestion and extraction | later |
| Chat agent | later |

176 Python tests and 23 TypeScript tests passing.
