import assert from "node:assert/strict";
import { test } from "node:test";

import { assuranceHint, assuranceOf, holdsLabel, percent } from "./assurance";
import type { Coverage } from "./types";

function coverage(partial: Partial<Coverage> = {}): Coverage {
  return {
    earliest: "2006-09-30",
    latest: "2026-06-27",
    history_years: 19.7,
    annual_reports: 17,
    looks_truncated: false,
    fact_count: 3867,
    verified_count: 1860,
    checks_passed: 910,
    checks_failed: 3,
    checks_skipped: 706,
    ...partial,
  };
}

test("the two questions are reported apart", () => {
  // Apple: almost everything that could be checked holds, and about half of
  // the identities could be checked. One number cannot say both.
  const a = assuranceOf(coverage());
  assert.equal(a.evaluated, 913);
  assert.equal(a.total, 1619);
  assert.equal(percent(a.holds), "100%");
  assert.equal(percent(a.coverage), "56%");
});

test("a ledger where nothing could be checked does not score well", () => {
  // The failure the old ratio hid: no identity ran, so there is nothing to
  // trust and nothing to report as trustworthy.
  const a = assuranceOf(coverage({ checks_passed: 0, checks_failed: 0, checks_skipped: 400 }));
  assert.equal(a.holds, null);
  assert.equal(percent(a.holds), "—");
  assert.equal(percent(a.coverage), "0%");
});

test("a break shows up in the trust number, not the coverage number", () => {
  const a = assuranceOf(coverage({ checks_passed: 50, checks_failed: 50, checks_skipped: 0 }));
  assert.equal(percent(a.holds), "50%");
  assert.equal(percent(a.coverage), "100%");
});

test("full coverage and full agreement is the only way to score 100 on both", () => {
  const a = assuranceOf(coverage({ checks_passed: 120, checks_failed: 0, checks_skipped: 0 }));
  assert.equal(percent(a.holds), "100%");
  assert.equal(percent(a.coverage), "100%");
});

test("an empty ledger claims nothing either way", () => {
  const a = assuranceOf(coverage({ checks_passed: 0, checks_failed: 0, checks_skipped: 0 }));
  assert.equal(a.holds, null);
  assert.equal(a.coverage, null);
  assert.equal(percent(a.coverage), "—");
});

test("the hint says which part is our limitation", () => {
  const hint = assuranceHint(assuranceOf(coverage()));
  assert.match(hint, /910 of 913/);
  assert.match(hint, /706 more could not run/);
  assert.match(hint, /missing a concept/);
});

test("the hint does not invent a shortfall when there is none", () => {
  const hint = assuranceHint(
    assuranceOf(coverage({ checks_passed: 10, checks_failed: 0, checks_skipped: 0 })),
  );
  assert.match(hint, /every identity had the data to run/);
});

test("the hint is honest about an empty ledger", () => {
  const hint = assuranceHint(
    assuranceOf(coverage({ checks_passed: 0, checks_failed: 0, checks_skipped: 0 })),
  );
  assert.match(hint, /No accounting identities were evaluated/);
});

test("a rounded percentage would show a clean score over real breaks", () => {
  // Apple: 3 breaks in 913. 910/913 is 99.67%, which rounds to "100%" -- a
  // clean score printed over three broken things. Rounding down is no better:
  // a filer with no breaks at all would read as 99%.
  const a = assuranceOf(coverage());
  assert.equal(percent(a.holds), "100%");
  assert.equal(holdsLabel(a), "910 / 913");
  assert.notEqual(a.failed, 0);
});

test("a filer with nothing broken reads as complete", () => {
  const a = assuranceOf(coverage({ checks_passed: 913, checks_failed: 0 }));
  assert.equal(holdsLabel(a), "913 / 913");
});

test("nothing evaluated has no ratio to show", () => {
  const a = assuranceOf(coverage({ checks_passed: 0, checks_failed: 0, checks_skipped: 40 }));
  assert.equal(holdsLabel(a), "—");
});

test("the hint carries the ledger size, which no longer has a tile", () => {
  assert.match(assuranceHint(assuranceOf(coverage()), 3867), /3,867 facts/);
  assert.doesNotMatch(assuranceHint(assuranceOf(coverage())), /facts/);
});
