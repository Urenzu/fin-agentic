import assert from "node:assert/strict";
import { test } from "node:test";

import { ABSENT, buildRows, cellProvenance, formatMetric, periodCaption } from "./comparison";
import type { Comparison, CompanyMetrics, MetricDescriptor, MetricValue } from "./types";

/** The row for a metric, asserting it exists rather than indexing blindly. */
function rowFor(comparison: Comparison, metric: string) {
  const found = buildRows(comparison).find((r) => r.descriptor.metric === metric);
  assert.ok(found, `no row for ${metric}`);
  return found;
}

/** The nth cell of a row, likewise. */
function cellAt(row: { cells: unknown[] }, index: number) {
  const cell = row.cells[index];
  assert.ok(cell, `no cell ${index}`);
  return cell as import("./comparison").Cell;
}

function descriptor(metric: string, unit = "USD", kind = "duration"): MetricDescriptor {
  return { metric, label: metric, kind, unit };
}

function value(metric: string, raw: string, partial: Partial<MetricValue> = {}): MetricValue {
  return {
    metric,
    label: metric,
    value: raw,
    element: `us-gaap_${metric}`,
    period_label: "Sep. 27, 2025",
    period_end: "2025-09-27",
    duration: "12 Months Ended",
    ...partial,
  };
}

function company(ticker: string, metrics: Record<string, MetricValue[]>): CompanyMetrics {
  return {
    registrant: { cik: 1, ticker, name: `${ticker} Inc.` },
    accession: "0000320193-25-000079",
    form: "10-K",
    filed: "2025-10-31",
    period_end: "2025-09-27",
    metrics,
    absent: [],
  };
}

// ---------------------------------------------------------------------------
// formatting
// ---------------------------------------------------------------------------

test("money is abbreviated to the magnitude a reader compares on", () => {
  assert.equal(formatMetric("416161000000", "USD"), "416.2B");
  assert.equal(formatMetric("8100000000", "USD"), "8.1B");
});

test("a share count is a count, not an amount of money", () => {
  // 15,004,730,000 shares and a $15bn balance are indistinguishable by
  // magnitude, which is why the unit comes from the API.
  assert.equal(formatMetric("15004730000", "shares"), "15.0B");
});

test("earnings per share are never abbreviated", () => {
  // A diluted EPS of 7.46 rendered as "7B" would be absurd, and the two differ
  // only by their unit.
  assert.equal(formatMetric("7.46", "USD/share"), "7.46");
  assert.equal(formatMetric("18.21", "USD/share"), "18.21");
});

test("a loss keeps its sign", () => {
  assert.equal(formatMetric("-2300000000", "USD"), "-2.3B");
  assert.equal(formatMetric("-1.25", "USD/share"), "(1.25)");
});

// ---------------------------------------------------------------------------
// rows
// ---------------------------------------------------------------------------

const COMPARISON: Comparison = {
  metrics: [
    descriptor("revenue"),
    descriptor("gross_profit"),
    descriptor("total_assets", "USD", "instant"),
  ],
  companies: [
    company("AAPL", {
      revenue: [value("revenue", "416161000000")],
      gross_profit: [value("gross_profit", "195201000000")],
      total_assets: [value("total_assets", "359241000000", { duration: null })],
    }),
    company("COST", {
      revenue: [value("revenue", "275235000000")],
      total_assets: [value("total_assets", "77100000000", { duration: null })],
    }),
  ],
};

test("every metric gets a row whether or not anyone reports it", () => {
  const rows = buildRows(COMPARISON);
  assert.deepEqual(
    rows.map((r) => r.descriptor.metric),
    ["revenue", "gross_profit", "total_assets"],
  );
  assert.ok(rows.every((r) => r.cells.length === 2));
});

test("a line the filer does not print reads as a gap in that column", () => {
  // Costco reports no gross profit. That is Costco's choice, and the row still
  // exists so the table keeps its shape.
  const grossProfit = rowFor(COMPARISON, "gross_profit");
  assert.equal(cellAt(grossProfit, 0).text, "195.2B");
  assert.equal(cellAt(grossProfit, 1).text, ABSENT);
  assert.equal(cellAt(grossProfit, 1).value, undefined);
  assert.equal(grossProfit.empty, false);
});

test("a row nobody reports is marked, so it can be hidden without guessing", () => {
  const nobody: Comparison = {
    metrics: [descriptor("capex")],
    companies: [company("AAPL", {}), company("COST", {})],
  };
  assert.equal(rowFor(nobody, "capex").empty, true);
});

test("the newest period is the one shown", () => {
  const multi: Comparison = {
    metrics: [descriptor("revenue")],
    companies: [
      company("AAPL", {
        revenue: [
          value("revenue", "416161000000"),
          value("revenue", "391035000000", { period_label: "Sep. 28, 2024" }),
        ],
      }),
    ],
  };
  assert.equal(cellAt(rowFor(multi, "revenue"), 0).text, "416.2B");
});

test("a negative figure is flagged for the renderer", () => {
  const loss: Comparison = {
    metrics: [descriptor("net_income")],
    companies: [company("X", { net_income: [value("net_income", "-2300000000")] })],
  };
  assert.equal(cellAt(rowFor(loss, "net_income"), 0).negative, true);
});

// ---------------------------------------------------------------------------
// provenance
// ---------------------------------------------------------------------------

test("a cell says which line the figure came from", () => {
  // Two filers reporting the same metric under different elements is the whole
  // reason the mapping exists, so it must be inspectable rather than trusted.
  const cell = cellAt(rowFor(COMPARISON, "revenue"), 0);
  const hint = cellProvenance("AAPL", cell);
  assert.match(hint ?? "", /RevenueFromContract|revenue/);
  assert.match(hint ?? "", /12 months ended to Sep\. 27, 2025/);
});

test("an instant is described by its date rather than a span", () => {
  const cell = cellAt(rowFor(COMPARISON, "total_assets"), 0);
  const hint = cellProvenance("AAPL", cell) ?? "";
  assert.match(hint, /Sep\. 27, 2025/);
  assert.doesNotMatch(hint, /ended to/);
});

test("an absent cell has nothing to explain", () => {
  assert.equal(cellProvenance("COST", cellAt(rowFor(COMPARISON, "gross_profit"), 1)), undefined);
});

test("the column caption says which period the column covers", () => {
  // Apple's year ends in late September and NVIDIA's in late January, so the
  // columns are not the same twelve months and the reader must see that.
  assert.equal(periodCaption("2025-09-27"), "2025-09-27");
  assert.equal(periodCaption(null), "period unknown");
});
