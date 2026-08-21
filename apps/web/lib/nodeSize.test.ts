import assert from "node:assert/strict";
import { test } from "node:test";

import {
  clampSize,
  MIN_ENTITY_HEIGHT,
  MIN_ENTITY_WIDTH,
  DEFAULT_STATEMENT_HEIGHT,
  MIN_STATEMENT_HEIGHT,
  MIN_STATEMENT_WIDTH,
  overflowsDefault,
  statementContentHeight,
  ENTITY_NODE_WIDTH,
  ENTITY_NODE_HEIGHT,
  LABEL_COLUMN,
  STATEMENT_WIDTH,
  VALUE_COLUMN,
} from "./nodeSize";
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

function statement(rowCount: number, columns = ["SEP. 27, 2025"]): AsFiledStatement {
  return {
    title: "CONSOLIDATED BALANCE SHEETS",
    short_name: "Consolidated Balance Sheets",
    columns: columns.map((label, index) => ({
      key: String(index),
      label,
      duration: null,
      date: null,
    })),
    rows: Array.from({ length: rowCount }, (_, i) => row({ label: `Line ${i}` })),
    monetary_scale: "1000000",
    share_scale: "1000",
    accession: "0000320193-25-000123",
    form: "10-K",
    filed: "2025-10-30",
    source_url: "https://www.sec.gov/",
  };
}

test("a short statement still opens at the standard height", () => {
  // Panels in a row are one size, so a statement that needs less than the cell
  // gets empty space under its last row rather than a smaller panel.
  const small = statement(6);
  assert.ok(statementContentHeight(small) < DEFAULT_STATEMENT_HEIGHT);
  assert.equal(overflowsDefault(small), false);
});

test("a long statement opens at the same height, with content taller than the panel", () => {
  const long = statement(90);
  assert.ok(statementContentHeight(long) > DEFAULT_STATEMENT_HEIGHT);
  assert.equal(overflowsDefault(long), true);
});

test("expanding to the content height is always a growth, never a shrink", () => {
  // The control's whole promise is "stop scrolling". If content height could
  // come out under the default, pressing it would hide rows instead.
  for (const count of [1, 5, 20, 24, 25, 40, 200]) {
    const s = statement(count);
    if (overflowsDefault(s)) {
      assert.ok(statementContentHeight(s) > DEFAULT_STATEMENT_HEIGHT, `${count} rows`);
    }
  }
});

test("section headings are taller than data rows, so content height accounts for them", () => {
  const plain = statement(10);
  const withSections: AsFiledStatement = {
    ...plain,
    rows: plain.rows.map((r, i) => (i % 5 === 0 ? { ...r, is_abstract: true } : r)),
  };
  assert.ok(statementContentHeight(withSections) > statementContentHeight(plain));
});

test("the standard width holds four periods and stays above the resize floor", () => {
  // Every statement occupies one cell of the board's grid, so a 10-K row and a
  // 10-Q row agree about where each column begins even though the two forms
  // print a different number of periods. The cell is sized for four, which is
  // the widest ordinary case: a 10-Q printing a quarter beside its year to
  // date.
  assert.ok(STATEMENT_WIDTH >= LABEL_COLUMN + 4 * VALUE_COLUMN);
  assert.ok(STATEMENT_WIDTH >= MIN_STATEMENT_WIDTH);
});

test("the resize floor leaves room for the chrome plus real rows", () => {
  // Below this the panel is all header and no statement.
  assert.ok(MIN_STATEMENT_HEIGHT > 66 + 34);
  assert.ok(MIN_STATEMENT_HEIGHT < DEFAULT_STATEMENT_HEIGHT);
});

test("clampSize holds a dimension inside its bounds", () => {
  assert.equal(clampSize(50, 100), 100);
  assert.equal(clampSize(150, 100), 150);
  assert.equal(clampSize(900, 100, 500), 500);
});

test("clampSize prefers the minimum when the bounds contradict each other", () => {
  // A max below the min would otherwise return something under the floor.
  assert.equal(clampSize(300, 400, 200), 400);
});

test("clampSize survives a degenerate dimension", () => {
  for (const bad of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
    const size = clampSize(bad, 120, 800);
    assert.ok(Number.isFinite(size) && size >= 120, `${bad} produced ${size}`);
  }
});

test("the entity card opens at the same height as a statement", () => {
  // A card 30px shorter than the panels beside it reads as a misalignment
  // rather than a decision.
  assert.equal(ENTITY_NODE_HEIGHT, DEFAULT_STATEMENT_HEIGHT);
});

test("the entity card's resize floors stay under the size it opens at", () => {
  // A floor above the opening size would make the card jump on first drag.
  assert.ok(MIN_ENTITY_HEIGHT < ENTITY_NODE_HEIGHT);
  assert.ok(MIN_ENTITY_WIDTH < ENTITY_NODE_WIDTH);
});
