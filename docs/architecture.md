# Architecture

## The core claim

The platform's differentiator is that **the numbers it shows are provably
consistent with the source document**. Not "the model was confident", not "we
used a good prompt" -- arithmetically checked against the other numbers in the
filing.

Everything below follows from taking that seriously.

## The pipeline

```
PDF
 │
 ▼
[ingest]        page text + layout, with coordinates
 │
 ▼
[extract]       LLM produces candidate facts, each quoting its source
 │              ── the ONLY place a model touches a number ──
 ▼
[normalise]     scale + sign applied from the concept registry
 │
 ▼
[reconcile]     duplicate slots collapsed; genuine disagreements CONFLICTED
 │
 ▼
[validate]      deterministic accounting identities; facts promoted to VERIFIED
 │
 ▼
[ledger]        Postgres. The system's memory.
 │
 ├──▶ [analytics]  ratios computed in Python from VERIFIED facts only
 │
 └──▶ [chat]       LLM writes prose over retrieved facts; every number it
                   emits is checked back against the ledger before display
```

### Where the model is, and is not

A language model appears in exactly two places:

1. **Extraction** — reading a statement and proposing `(concept, period, value)`
   triples with a quotation from the page. Its output is a *proposal*, not a
   fact. It is then normalised and validated by code.
2. **Narration** — writing prose about facts that have already been verified.
   It is given the numbers; it does not produce them.

A model never computes a ratio, never sums a column, never decides whether a
statement balances. Those are `Decimal` arithmetic in tested Python.

## Why the ledger is the memory system

"Memory" here is not a vector store of document chunks. It is a typed table of
financial facts with provenance and verification status. This matters because:

- A chunk-retrieval system answers "what does the document say about revenue?"
  The ledger answers "what *was* revenue in FY2023, and how do we know?"
- Chunk retrieval degrades silently when it retrieves the wrong period's column.
  The ledger cannot: period is part of a fact's identity, and a column offset
  breaks the cash tie (see below).
- Ratios computed from a ledger are reproducible and auditable. Ratios a model
  reads off retrieved text are neither.

Narrative text (MD&A, footnotes, risk factors) *is* embedded and retrieved --
that is genuinely unstructured and there is no identity to check it against. But
narrative retrieval never supplies a number; it supplies context around numbers
the ledger already verified.

## Key design decisions

### Decimal, never float

Money is `Decimal` end to end. `0.1 + 0.2 != 0.3` in binary floating point, and
an accounting identity evaluated in floats accumulates error indistinguishable
from a real reconciliation break. `test_scaling_is_exact` pins this.

### Sign conventions live in the registry, not in the extractor

Each concept declares `MAGNITUDE` (costs, capex, dividends — stored positive
regardless of how the filing printed them) or `AS_REPORTED` (net income, cash
flow subtotals, retained earnings — the sign is real information). This means an
identity can be written the natural way (`GrossProfit = Revenue - CostOfRevenue`)
without every formula re-deriving whether its inputs are negative.

`sign_flipped` records whenever normalisation changed a sign, so the
transformation from printed to stored is always reconstructable.

### Verification is earned, not assumed

A fact is `VERIFIED` only if it participated in at least one *passed* identity
check and no *failed* one. A fact no check can reach stays `UNVERIFIED` and the
UI shows it as such.

This is the anti-hallucination mechanism, and it is structural rather than
probabilistic: a fabricated number will not satisfy the balance sheet. Extractor
confidence scores are recorded but never gate trust — a confidently wrong
extraction is exactly the failure mode being defended against.

### Absence of evidence is not evidence of a break

Three distinct outcomes, deliberately kept separate:

| Outcome | Meaning |
| --- | --- |
| `PASSED` | The identity held. |
| `FAILED` | The identity was contradicted. Something is wrong. |
| `SKIPPED` | Not enough was extracted to evaluate it. |

Two refinements exist because collapsing them produces false alarms, and a
reconciliation panel that cries wolf is one users learn to ignore:

- **Subtotal checks are asymmetric.** Components summing to *more* than their
  stated total is a genuine contradiction (`FAILED`). Summing to *less* is
  consistent with line items not yet extracted (`SKIPPED`, with the residual
  recorded — that residual is itself informative).
- **Missing optional terms downgrade a break to a skip.** A cash roll-forward
  that misses by 50M when the FX-translation line was never extracted might be
  an error, or might be that line. Asserting a break would claim knowledge the
  system lacks, and would wrongly mark correctly-extracted facts inconsistent.

Both rules were forced by property tests, not designed up front — see
`test_dropping_facts_never_manufactures_a_failure`.

### The cross-statement cash tie

`CashFlow.EndingCash == BalanceSheet.Cash` at the same instant is the highest-value
single check in the system. It ties two independently-extracted statements
together, which catches the most damaging and least visible extraction error:
reading the wrong fiscal year's column. A column offset produces numbers that
are individually plausible and internally consistent within one statement — only
the cross-tie catches it.

## Testing strategy

| Layer | What it protects |
| --- | --- |
| Unit | Each check catches its specific error and stays quiet on clean input. Both directions are tested — a check that never fires is as bad as one that always does. |
| Property (Hypothesis) | Invariants over generated input: scaling is exact, signs normalise correctly, dropping facts never manufactures a failure, tampering with any total is always detected. |
| Golden | Real filings with hand-verified ground truth. Measures extraction accuracy. *(pending)* |
| Integration | Full pipeline, PDF to ledger. *(pending)* |

The synthetic `clean_filing` fixture is fully internally consistent, so tests
perturb exactly one value and assert the responsible check fires. That is a much
sharper signal than testing against a real filing, where a failure could be
blamed on extraction rather than on the check.

Run the deep property suite with `HYPOTHESIS_PROFILE=deep pytest tests/property`.

## Status

Built and tested:

- `domain/` — concept registry, periods, facts, ledger
- `validation/` — 16 identity checks, verification engine
- 75 tests passing, lint clean

Not yet built:

- `ingest/` — PDF parsing
- extraction — LLM structured output with provenance
- `analytics/` — ratio engine
- `store/` — Postgres persistence
- `agent/` — chat with grounding check
- `apps/web` — canvas UI
