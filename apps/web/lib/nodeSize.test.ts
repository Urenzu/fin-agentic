import assert from "node:assert/strict";
import { test } from "node:test";

import {
  clampSize,
  DEFAULT_STATEMENT_HEIGHT,
  MIN_STATEMENT_HEIGHT,
  MIN_STATEMENT_WIDTH,
  overflowsDefault,
  statementContentHeight,
  statementNodeHeight,
  statementNodeWidth,
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
    columns,
    column_dates: columns.map(() => null),
    rows: Array.from({ length: rowCount }, (_, i) => row({ label: `Line ${i}` })),
    monetary_scale: "1000000",
    share_scale: "1000",
    accession: "0000320193-25-000123",
    form: "10-K",
    filed: "2025-10-30",
    source_url: "https://www.sec.gov/",
  };
}

test("a short statement opens fully expanded and offers no fit control", () => {
  const small = statement(6);
  assert.equal(statementNodeHeight(small), statementContentHeight(small));
  assert.equal(overflowsDefault(small), false);
});

test("a long statement opens capped, with content taller than the panel", () => {
  const long = statement(90);
  assert.equal(statementNodeHeight(long), DEFAULT_STATEMENT_HEIGHT);
  assert.ok(statementContentHeight(long) > DEFAULT_STATEMENT_HEIGHT);
  assert.equal(overflowsDefault(long), true);
});

test("expanding to the content height is always a growth, never a shrink", () => {
  // The control's whole promise is "stop scrolling". If content height could
  // come out under the default, pressing it would hide rows instead.
  for (const count of [1, 5, 20, 24, 25, 40, 200]) {
    const s = statement(count);
    if (overflowsDefault(s)) {
      assert.ok(statementContentHeight(s) > statementNodeHeight(s), `${count} rows`);
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

test("width grows with the number of periods shown", () => {
  const one = statementNodeWidth(statement(5, ["2025"]));
  const three = statementNodeWidth(statement(5, ["2025", "2024", "2023"]));
  assert.ok(three > one);
  assert.ok(one >= MIN_STATEMENT_WIDTH);
});

test("a statement with no columns still gets a usable width", () => {
  // Defensive: a filing whose exhibit parsed to zero periods must not collapse
  // the node to the label column alone.
  assert.ok(statementNodeWidth(statement(5, [])) >= MIN_STATEMENT_WIDTH);
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
