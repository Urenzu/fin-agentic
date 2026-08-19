import assert from "node:assert/strict";
import { test } from "node:test";

import {
  counterScale,
  fitScale,
  headlineCapacity,
  headlineRows,
  IDENTITY_BELOW,
  SUMMARY_BELOW,
} from "./lod";
import type { AsFiledRow, AsFiledStatement } from "./types";

function row(partial: Partial<AsFiledRow> & { label: string }): AsFiledRow {
  return {
    element: null,
    tag: null,
    is_abstract: false,
    is_total: false,
    indent: 0,
    values: {},
    ...partial,
  };
}

function statement(rows: AsFiledRow[], columns = ["SEP. 27, 2025"]): AsFiledStatement {
  return {
    title: "CONSOLIDATED STATEMENTS OF OPERATIONS",
    short_name: "Consolidated Statements of Operations",
    columns,
    column_dates: columns.map(() => null),
    rows,
    monetary_scale: "1000000",
    share_scale: "1000",
    accession: "0000320193-25-000123",
    form: "10-K",
    filed: "2025-10-30",
    source_url: "https://www.sec.gov/",
  };
}

test("counterScale holds a label at constant screen size when zoomed out", () => {
  // A 12px label at zoom 0.5 renders at 6px; doubling it restores 12px.
  assert.equal(counterScale(0.5), 2);
  assert.equal(counterScale(0.25), 3.2); // capped
});

test("counterScale does not shrink text when zoomed in past 1:1", () => {
  assert.equal(counterScale(1), 1);
  assert.equal(counterScale(2), 1);
});

test("counterScale caps the correction so titles cannot overflow their node", () => {
  assert.equal(counterScale(0.01), 3.2);
  assert.equal(counterScale(0.5, 1.5), 1.5);
});

test("counterScale survives a degenerate zoom rather than returning Infinity", () => {
  for (const bad of [0, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
    const scale = counterScale(bad);
    assert.ok(Number.isFinite(scale), `${bad} produced ${scale}`);
    assert.ok(scale > 0);
  }
});

test("the summary threshold sits above the identity threshold", () => {
  // Detail is shed in one direction only; crossing these out of order would
  // drop the figures before the table.
  assert.ok(IDENTITY_BELOW < SUMMARY_BELOW);
});

test("headlineRows prefers the filer's own totals", () => {
  const s = statement([
    row({ label: "Net sales", values: { "SEP. 27, 2025": "416161000000" } }),
    row({ label: "Cost of sales", values: { "SEP. 27, 2025": "220980000000" } }),
    row({ label: "Gross margin", is_total: true, values: { "SEP. 27, 2025": "195201000000" } }),
    row({ label: "Net income", is_total: true, values: { "SEP. 27, 2025": "112010000000" } }),
  ]);
  assert.deepEqual(
    headlineRows(s).map((r) => r.label),
    ["Gross margin", "Net income"],
  );
});

test("headlineRows falls back to plain rows when nothing is marked a total", () => {
  const s = statement([
    row({ label: "Net income", values: { "SEP. 27, 2025": "112010000000" } }),
    row({ label: "Other comprehensive income", values: { "SEP. 27, 2025": "1000000" } }),
  ]);
  assert.deepEqual(
    headlineRows(s).map((r) => r.label),
    ["Net income", "Other comprehensive income"],
  );
});

test("headlineRows skips section headings and blank cells", () => {
  const s = statement([
    row({ label: "OPERATING EXPENSES", is_abstract: true }),
    // Marked a total but absent from the newest column: rendering it would put
    // an em dash where the headline figure should be.
    row({ label: "Discontinued operations", is_total: true, values: {} }),
    row({ label: "Total assets", is_total: true, values: { "SEP. 27, 2025": "359241000000" } }),
  ]);
  assert.deepEqual(
    headlineRows(s).map((r) => r.label),
    ["Total assets"],
  );
});

test("headlineRows honours its limit and tolerates a statement with no columns", () => {
  const many = statement(
    Array.from({ length: 9 }, (_, i) =>
      row({ label: `Total ${i}`, is_total: true, values: { "SEP. 27, 2025": "1" } }),
    ),
  );
  assert.equal(headlineRows(many).length, 3);
  assert.equal(headlineRows(many, 5).length, 5);
  assert.deepEqual(headlineRows(statement([], [])), []);
});

test("fitScale keeps a magnified header inside a short node", () => {
  // The entity card: 154px tall, so its header may not exceed 77px. The
  // uncapped correction at this zoom is 3.2x, which would ask for 211px.
  const scale = fitScale(0.2, 154);
  assert.ok(scale * 66 <= 154 * 0.5 + 0.001, `header would be ${scale * 66}px`);
});

test("fitScale leaves a tall node free to use the full correction", () => {
  assert.equal(fitScale(0.25, 560), counterScale(0.25));
});

test("fitScale never shrinks a node's header below its natural size", () => {
  // A very short node cannot afford any magnification, but returning < 1 would
  // make the header smaller than at 1:1 and unreadable at every zoom.
  assert.equal(fitScale(0.2, 40), 1);
});

test("headlineCapacity shrinks as the correction grows", () => {
  const tall = 560;
  assert.ok(headlineCapacity(tall, 1) > headlineCapacity(tall, 2.86));
});

test("headlineCapacity never reports room that would clip a figure", () => {
  // Swept at the scales the node actually uses -- fitScale is what decides the
  // correction, and it already refuses one the panel cannot afford.
  for (const height of [180, 300, 420, 560]) {
    for (const zoom of [0.5, 0.4, 0.3, 0.2, 0.1]) {
      const scale = fitScale(zoom, height, 0.4);
      const rows = headlineCapacity(height, scale);
      const used = (66 + 16) * scale + rows * 44 * scale;
      assert.ok(used <= height, `${rows} rows at ${scale}x needs ${used}px of ${height}px`);
    }
  }
});

test("headlineCapacity reports zero rather than a negative count", () => {
  assert.equal(headlineCapacity(120, 3.2), 0);
});
