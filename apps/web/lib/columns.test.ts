import test from "node:test";
import assert from "node:assert/strict";

import { columnGroups, needsGroupRow } from "./columns";
import type { AsFiledColumn } from "./types";

function columns(...pairs: [label: string, duration: string | null][]): AsFiledColumn[] {
  return pairs.map(([label, duration], index) => ({
    key: String(index),
    label,
    duration,
    date: null,
  }));
}

const QUARTERLY = columns(
  ["Jun. 27, 2026", "3 Months Ended"],
  ["Jun. 28, 2025", "3 Months Ended"],
  ["Jun. 27, 2026", "9 Months Ended"],
  ["Jun. 28, 2025", "9 Months Ended"],
);

test("a quarterly statement groups into its two blocks", () => {
  assert.deepEqual(columnGroups(QUARTERLY), [
    { duration: "3 Months Ended", span: 2 },
    { duration: "9 Months Ended", span: 2 },
  ]);
});

test("the spans cover every column exactly once", () => {
  const total = columnGroups(QUARTERLY).reduce((sum, group) => sum + group.span, 0);
  assert.equal(total, QUARTERLY.length);
});

test("a balance sheet's instants form one undated group", () => {
  const sheet = columns(["Sep. 27, 2025", null], ["Sep. 28, 2024", null]);
  assert.deepEqual(columnGroups(sheet), [{ duration: null, span: 2 }]);
});

test("no columns means no groups", () => {
  assert.deepEqual(columnGroups([]), []);
});

test("the group row is drawn only when a heading distinguishes the columns", () => {
  // One duration over everything repeats what the statement's title says.
  const annual = columns(
    ["Sep. 27, 2025", "12 Months Ended"],
    ["Sep. 28, 2024", "12 Months Ended"],
  );
  assert.equal(needsGroupRow(annual), false);
  assert.equal(needsGroupRow(columns(["Sep. 27, 2025", null])), false);
  assert.equal(needsGroupRow(QUARTERLY), true);
});

test("a repeated duration that is not consecutive stays two groups", () => {
  // The order the filer chose is part of the statement, so like durations are
  // never gathered together.
  const interleaved = columns(
    ["Jun. 27, 2026", "3 Months Ended"],
    ["Jun. 27, 2026", "9 Months Ended"],
    ["Jun. 28, 2025", "3 Months Ended"],
  );
  assert.deepEqual(
    columnGroups(interleaved).map((group) => group.span),
    [1, 1, 1],
  );
});
