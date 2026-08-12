# Roadmap

Running list of what we want to build. Newest thinking at the top of each
section. See [docs/architecture.md](docs/architecture.md) for how the built
parts work and why.

Status key: **next** = actively queued · **planned** = agreed, not started ·
**idea** = worth considering, not committed

---

## Statement rendering

- **next** — **Canonical statement view.** Three layouts (income statement,
  balance sheet, cash flow) rendered from the ledger with our own ordering,
  indentation and subtotals. Identical across every company so two filers can be
  compared without adapting to two house styles. Shows verification status
  inline per line.
  - Requires: `display_order` and `indent_level` on `ConceptMeta`.
- **planned** — **"View as filed" toggle.** Render each company's own line
  order, labels and subtotals, matching their actual statement. Source is the
  SEC's own rendered exhibits (`FilingSummary.xml` → `R*.htm`), which we
  confirmed are available per filing.
  - Doubles as the provenance click-through: "show me this number in the
    source". Our view for reading and analysis; theirs for verifying.
  - Note: rendering our own numbers in a document-shaped container is *not*
    provenance. The link to the SEC's exhibit is what makes the claim real.

## Coverage: industries and tags

- **next** — **Widen the tag map for commercial filers.** Driven by
  `scripts/tag_frequency.py` output rather than guesswork.
- **planned** — **Bank template (Reg S-X Article 9).** Banks have no operating
  cycle, so no current/non-current split and no gross profit — an unclassified
  balance sheet is a different template, not a variation. Needs ~30 statement-face
  tags (`Deposits`, `InterestAndFeeIncomeLoansAndLeases`, `NoninterestIncome`,
  `ProvisionForLoanLeaseAndOtherLosses`, …) and its own identity checks, e.g.
  net interest income = interest income − interest expense.
  - Until built, banks must be **detected and disclosed**, never forced into the
    commercial template.
- **planned** — **REIT template.** FFO/AFFO as the headline metric rather than
  EPS; real estate at cost less accumulated depreciation.
- **idea** — **Insurance template (Article 7).** Premiums earned, loss reserves,
  float. Lower priority unless we specifically target the sector.
- **idea** — **DERA Financial Statement Data Sets.** The SEC's quarterly
  research files include `pre.txt`, which marks each fact with the statement it
  appears on (BS/IS/CF/EQ/CI) — the presentation information `companyfacts`
  lacks. Would give an authoritative statement-face tag list instead of hand
  curation.
  - Build-time only: download once, produce a static dict, discard. Never a
    runtime dependency.
  - Only worth doing if hand curation stalls.

## Known data problems

- **next** — **Redeemable / temporary equity.** Mezzanine equity sits between
  liabilities and equity and belongs to neither, so `Assets = L + E` genuinely
  does not hold as modelled. Causes ~92 of Tesla's validation failures.
- **next** — **Stock split adjustment.** Splits retroactively restate per-share
  figures, so EPS from a post-split filing does not reconcile against a share
  count from a pre-split one. Apple's 2020 4-for-1 split: 4.77B shares reported
  in the Q1 10-Q vs 19.07B restated. Affects EPS and all share counts.
- **planned** — **Predecessor entity discovery.** A ticker resolves to whichever
  CIK currently holds it; after a reorganisation that is the new holding company.
  `XOM` → "ExxonMobil Holdings Corp" (1.5y of history) rather than CIK 34088
  (19.2y). Currently detected via `looks_truncated` and worked around with
  `registrant_for_cik`. Should suggest the predecessor automatically.
- **planned** — **Bank/insurer detection.** Identify the filer's statement shape
  from its tag profile so the right template and check set are selected.

## Persistence

- **planned** — **Two-layer storage.**
  1. Raw `companyfacts` payloads cached verbatim (`JSONB` or on disk). Lets us
     re-derive every fact after a tag-mapping fix without re-fetching from SEC —
     which is how the mapping bugs found so far were iterated on.
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

- **planned** — Infinite pan/zoom canvas (`@xyflow/react`), black/glass
  aesthetic, statements and charts as draggable nodes.
- **planned** — Ticker search that seeds a starter board.
- **planned** — Reconciliation panel: which identities passed, failed or could
  not be evaluated, and the unexplained residual where a subtotal fell short.
- **planned** — Click a figure → highlight its line in the statement → open the
  source filing.

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
