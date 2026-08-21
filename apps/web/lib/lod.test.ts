import assert from "node:assert/strict";
import { test } from "node:test";

import {
  counterScale,
  fitScale,
  headlineCapacity,
  headlineRows,
  IDENTITY_BELOW,
  quantize,
  SCALE_STEPS,
  stepScale,
  SUMMARY_BELOW,
  tierFor,
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
    columns: columns.map((label, index) => ({
      key: String(index),
      label,
      duration: null,
      date: null,
    })),
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
  assert.equal(counterScale(0.2), 3.6); // capped
});

test("counterScale does not shrink text when zoomed in past 1:1", () => {
  assert.equal(counterScale(1), 1);
  assert.equal(counterScale(2), 1);
});

test("counterScale caps the correction so titles cannot overflow their node", () => {
  assert.equal(counterScale(0.01), 3.6);
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
    row({ label: "Net sales", values: { 0: "416161000000" } }),
    row({ label: "Cost of sales", values: { 0: "220980000000" } }),
    row({ label: "Gross margin", is_total: true, values: { 0: "195201000000" } }),
    row({ label: "Net income", is_total: true, values: { 0: "112010000000" } }),
  ]);
  assert.deepEqual(
    headlineRows(s).map((r) => r.label),
    ["Gross margin", "Net income"],
  );
});

test("headlineRows falls back to plain rows when nothing is marked a total", () => {
  const s = statement([
    row({ label: "Net income", values: { 0: "112010000000" } }),
    row({ label: "Other comprehensive income", values: { 0: "1000000" } }),
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
    row({ label: "Total assets", is_total: true, values: { 0: "359241000000" } }),
  ]);
  assert.deepEqual(
    headlineRows(s).map((r) => r.label),
    ["Total assets"],
  );
});

test("headlineRows honours its limit and tolerates a statement with no columns", () => {
  const many = statement(
    Array.from({ length: 9 }, (_, i) =>
      row({ label: `Total ${i}`, is_total: true, values: { 0: "1" } }),
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
  assert.equal(fitScale(0.25, 560), stepScale(0.25));
});

test("fitScale never shrinks a node's header below its natural size", () => {
  // A very short node cannot afford any magnification, but returning < 1 would
  // make the header smaller than at 1:1 and unreadable at every zoom.
  assert.equal(fitScale(0.2, 40), 1);
});

test("headlineCapacity shrinks as the correction grows", () => {
  const tall = 560;
  assert.ok(headlineCapacity(tall, 1) > headlineCapacity(tall, 2.8));
});

test("headlineCapacity never reports room that would clip a figure", () => {
  // Swept at the scales the node actually uses -- fitScale is what decides the
  // correction, and it already refuses one the panel cannot afford.
  for (const height of [180, 300, 420, 560]) {
    for (const zoom of [0.49, 0.4, 0.3, 0.2, 0.1]) {
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

test("quantize snaps to the largest step at or below the value", () => {
  assert.equal(quantize(1.0), 1);
  assert.equal(quantize(1.39), 1);
  assert.equal(quantize(1.4), 1.4);
  assert.equal(quantize(99), 3.6);
});

test("quantize never returns a value above what was asked for", () => {
  // Rounding up would magnify past the cap the geometry allows.
  for (let v = 1; v <= 4; v += 0.05) {
    assert.ok(quantize(v) <= v + 1e-9, `quantize(${v}) = ${quantize(v)}`);
  }
});

test("stepScale only ever returns a declared step", () => {
  for (let zoom = 0.05; zoom <= 2; zoom += 0.005) {
    assert.ok(
      (SCALE_STEPS as readonly number[]).includes(stepScale(zoom)),
      `zoom ${zoom} produced ${stepScale(zoom)}`,
    );
  }
});

test("stepScale holds still across a zoom gesture", () => {
  // The whole point: sweeping the usable zoom range must change the label size
  // a handful of times, not on every frame. Sized off 1/zoom directly this
  // would be ~390 distinct values, and the text crawled.
  const seen = new Set<number>();
  for (let zoom = 0.05; zoom <= 2; zoom += 0.005) seen.add(stepScale(zoom));
  assert.ok(seen.size <= SCALE_STEPS.length, `${seen.size} distinct sizes`);
});

test("stepScale never grows as the board is zoomed in", () => {
  let previous = Number.POSITIVE_INFINITY;
  for (let zoom = 0.05; zoom <= 2; zoom += 0.005) {
    const scale = stepScale(zoom);
    assert.ok(scale <= previous + 1e-9, `scale rose at zoom ${zoom}`);
    previous = scale;
  }
});

test("every tier boundary coincides with a step change", () => {
  // A tier change and a resize happening at slightly different zooms is what
  // made one gesture produce two separate pops.
  const epsilon = 1e-6;
  for (const boundary of [SUMMARY_BELOW, IDENTITY_BELOW]) {
    assert.notEqual(
      stepScale(boundary - epsilon),
      stepScale(boundary + epsilon),
      `no step change at ${boundary}`,
    );
  }
});

test("tierFor sheds detail in one direction and covers the whole range", () => {
  assert.equal(tierFor(1), "detail");
  assert.equal(tierFor(SUMMARY_BELOW), "detail");
  assert.equal(tierFor(SUMMARY_BELOW - 1e-6), "summary");
  assert.equal(tierFor(IDENTITY_BELOW), "summary");
  assert.equal(tierFor(IDENTITY_BELOW - 1e-6), "identity");
});

test("tierFor survives a degenerate zoom", () => {
  for (const bad of [0, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
    assert.ok(["detail", "summary", "identity"].includes(tierFor(bad)));
  }
});
