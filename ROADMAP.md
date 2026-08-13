# Roadmap

Running list of what we want to build. See
[docs/architecture.md](docs/architecture.md) for how the built parts work and
why.

Status key: **next** = actively queued · **planned** = agreed, not started ·
**idea** = worth considering, not committed · **dropped** = decided against,
with the reason kept

---

## Statement rendering

- **done** — **As-filed statement view.** Each filing's statements rendered
  exactly as the filer laid them out, parsed from the SEC's own exhibits
  (`FilingSummary.xml` → `R*.htm`). Correct line order, the filer's own labels,
  section headings, hierarchy, and only statement-face items.
  - This is the primary display path. It also *is* the provenance
    click-through: the same exhibit the number came from.
- **done** — **Canonical statement view.** Three layouts rendered from the
  ledger with our own ordering, indentation and subtotals, identical across
  every company.
  - Repositioned: no longer a display surface. It exists to feed charts, time
    series and cross-company comparison, all of which need one consistent shape
    that as-filed rendering cannot provide.

## Coverage: industries and tags

- **planned** — **Widen the tag map, retargeted.** The goal is no longer "cover
  every statement line", which is unbounded — every filer has an idiosyncratic
  line or two. Display comes from as-filed rendering, so the canonical map only
  needs the concepts the **metrics** consume: revenue, COGS, gross profit, opex,
  operating income, net income, EPS, shares, cash, receivables, inventory,
  payables, debt, equity, total assets, operating cash flow, capex. Roughly
  40–50 concepts, most already mapped. Finishable, unlike the previous target.
- **planned** — **Bank analytics (Reg S-X Article 9).** No longer needed for
  *display*: JPMorgan renders correctly as filed, with its own lines — deposits,
  securities borrowed, held-to-maturity securities, beneficial interests issued
  by consolidated VIEs — and no bank-specific vocabulary at all.
  - Still needed for **analytics**, where one consistent shape is required: net
    interest margin, efficiency ratio, capital ratios. Shape detection already
    gates this, so banks are disclosed rather than given commercial ratios.
- **planned** — **REIT analytics.** FFO/AFFO as the headline measure rather than
  EPS, because GAAP depreciation on real estate understates the economics.
- **idea** — **Insurer analytics (Article 7).** Combined ratio, reserve
  adequacy, float.
- **dropped** — **DERA Financial Statement Data Sets.** `pre.txt` exists to say
  which tags belong on which statement, in what order. The R-files answer
  exactly that, per filing, from a source already being fetched — so the bulk
  research dataset earns nothing.
  - The coverage problem it was meant to solve also dissolved: as filed, a line
    like Apple's $33bn "Vendor non-trade receivables" simply appears rather than
    needing to be mapped. That single line was the whole shortfall in Apple's
    current-assets subtotal.

## Known data problems

- **next** — **Redeemable / temporary equity.** Mezzanine equity sits between
  liabilities and equity and belongs to neither, so `Assets = L + E` genuinely
  does not hold as modelled. Causes ~92 of Tesla's validation failures.
- **next** — **Stock split adjustment.** Splits retroactively restate per-share
  figures, so EPS from a post-split filing does not reconcile against a share
  count from a pre-split one. Apple's 2020 4-for-1 split: 4.77B shares reported
  in the Q1 10-Q vs 19.07B restated. Affects EPS and all share counts.
- **planned** — **Predecessor entity discovery.** A ticker resolves to whichever
  CIK currently holds it; after a reorganisation that is the new holding
  company. `XOM` → "ExxonMobil Holdings Corp" (1.5y of history) rather than CIK
  34088 (19.2y). Detected today via `looks_truncated` and worked around with
  `registrant_for_cik`; should suggest the predecessor automatically.

## Validation, repositioned

Validation guards **our transformations**, not the filers' books. On the XBRL
path the values are filer-tagged in an audited submission, so there is no
extraction step and no hallucination surface. Every bug these checks have caught
so far was ours: `ProfitLoss` vs `NetIncomeLoss`, `CostsAndExpenses` including
COGS, fiscal-year labelling, and a period-key collision.

- **planned** — Stop reporting `verified_ratio` on as-filed statements. It is
  meaningless there: the exhibit *is* the filing.
- **planned** — Report corroboration on **derived metrics** instead, where
  splicing a series across three tags or mis-mapping COGS is a real risk that
  belongs to us.
- Becomes load-bearing again for the PDF path and for chat grounding, where a
  model produces numbers and can genuinely get them wrong.

## Persistence

- **planned** — **Two-layer storage.**
  1. Raw `companyfacts` payloads and R-files cached verbatim (`JSONB` or on
     disk). Lets every fact be re-derived after a mapping fix without
     re-fetching — which is how each mapping bug so far was iterated on.
  2. Derived facts in a normalised table, indexed on
     `(entity_id, concept, period)`, for analytics and charts.
  - **Money columns must be `NUMERIC`, never `float`/`double precision`.** A
    float column would reintroduce the precision loss the ledger design exists
    to prevent, silently and after validation has already passed.

## Analytics

- **planned** — **Deterministic metric engine.** Margins, growth, DuPont,
  liquidity, leverage, working capital, FCF and conversion, accrual quality,
  Altman/Piotroski. Every metric declares its required concepts and returns an
  explicit "unavailable, because X is missing" rather than a number computed
  from an implicit zero.
- **idea** — Common-size statements and period-over-period bridges.

## Canvas and UI

- **next** — Infinite pan/zoom canvas (`@xyflow/react`), black/glass aesthetic,
  statements and charts as draggable nodes.
- **next** — Ticker search that seeds a starter board.
- **planned** — Statement node rendering as-filed, with a link to the SEC
  exhibit the numbers came from.
- **planned** — Reconciliation panel: which identities passed, failed or could
  not be evaluated, and the unexplained residual where a subtotal fell short.
- **idea** — Toggle between as-filed and canonical views, for comparing two
  companies side by side.

## Later

- **idea** — PDF drag-and-drop for private, foreign and pre-2009 companies:
  ingest → page classification → extraction with provenance → same validation
  layer. Measured against XBRL as ground truth.
- **idea** — OCR path for scanned documents, emitting the same `text + bbox`
  interface as native PDFs.
- **idea** — LangGraph chat over the ledger, with a grounding check that rejects
  any number not traceable to a verified fact.
- **idea** — Research agents pulling industry context during analysis.
- **idea** — MCP connectors for brokerage order submission.
