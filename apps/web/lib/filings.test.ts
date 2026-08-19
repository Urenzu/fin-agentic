import assert from "node:assert/strict";
import { test } from "node:test";

import { filingFiledLabel, filingPeriodLabel, formatFilingDate } from "./filings";
import type { FilingIndex } from "./types";

function filing(partial: Partial<FilingIndex> = {}): FilingIndex {
  return {
    accession: "0000320193-25-000079",
    form: "10-K",
    filed: "2025-10-31",
    period_end: "2025-09-27",
    source_url: "https://www.sec.gov/",
    statements: [],
    ...partial,
  };
}

test("a date is not shifted into the previous day by the timezone", () => {
  // `new Date("2025-09-27")` parses as UTC midnight, which is the 26th anywhere
  // west of Greenwich -- a filing would appear to report a day early.
  assert.match(formatFilingDate("2025-09-27"), /27/);
  assert.match(formatFilingDate("2026-01-01"), /2026/);
});

test("a malformed date is passed through rather than rendered as Invalid Date", () => {
  assert.equal(formatFilingDate("not-a-date"), "not-a-date");
  assert.equal(formatFilingDate(""), "");
});

test("an annual filing is labelled by the year it reports on", () => {
  const label = filingPeriodLabel(filing());
  assert.match(label, /^Year ended/);
  assert.match(label, /27/);
});

test("a quarterly filing is labelled as a quarter", () => {
  const label = filingPeriodLabel(filing({ form: "10-Q", period_end: "2026-06-27" }));
  assert.match(label, /^Quarter ended/);
});

test("amended forms keep the span of the form they amend", () => {
  assert.match(filingPeriodLabel(filing({ form: "10-K/A" })), /^Year ended/);
});

test("a filing with no period end falls back to naming its form", () => {
  assert.equal(filingPeriodLabel(filing({ period_end: null, form: "10-Q" })), "10-Q");
});

test("the filed date is reported separately from the period", () => {
  // These differ by weeks and conflating them misdates the statements.
  const f = filing();
  assert.match(filingFiledLabel(f), /^filed/);
  assert.notEqual(filingFiledLabel(f), filingPeriodLabel(f));
});
