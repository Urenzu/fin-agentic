import { abbreviate, formatValue } from "./decimal";
import type { Comparison, MetricDescriptor, MetricValue } from "./types";

/**
 * Formatting a comparison cell by what the figure *is*.
 *
 * The unit comes from the API rather than being guessed here. Apple's
 * 15,004,730,000 diluted shares and a $15bn balance are indistinguishable by
 * magnitude, and abbreviating a diluted EPS of 7.46 to "7B" would be absurd --
 * so the server says which is which and this formats accordingly.
 */
export function formatMetric(value: string, unit: string): string {
  if (unit === "USD/share") return formatValue(value, 0, { dp: 2, parens: true });
  // Share counts read better abbreviated than as eleven digits, and nobody
  // needs the exact count of a weighted average.
  return abbreviate(value);
}

/** What a cell shows when the filer does not report the line at all. */
export const ABSENT = "—";

export type Cell = {
  /** The formatted figure, or `ABSENT`. */
  text: string;
  /** Present only when the filer reports the line. */
  value?: MetricValue;
  negative: boolean;
};

/**
 * One row of the comparison: a metric and one cell per company.
 *
 * Every metric gets a row whether or not anyone reports it, so the table has
 * the same shape for any set of companies and a missing figure reads as a gap
 * in that column rather than as a shorter table.
 */
export type Row = {
  descriptor: MetricDescriptor;
  cells: Cell[];
  /** True when no company in the comparison reports this line. */
  empty: boolean;
};

export function buildRows(comparison: Comparison): Row[] {
  return comparison.metrics.map((descriptor) => {
    const cells = comparison.companies.map((company): Cell => {
      const periods = company.metrics[descriptor.metric];
      const newest = periods?.[0];
      if (newest === undefined) return { text: ABSENT, negative: false };
      return {
        text: formatMetric(newest.value, descriptor.unit),
        value: newest,
        negative: newest.value.startsWith("-"),
      };
    });

    return { descriptor, cells, empty: cells.every((c) => c.value === undefined) };
  });
}

/**
 * A line of provenance for one cell.
 *
 * Two filers reporting the same metric under different element names is the
 * entire reason the mapping exists, so which line was used has to be
 * inspectable rather than taken on trust.
 */
export function cellProvenance(company: string, cell: Cell): string | undefined {
  if (cell.value === undefined) return undefined;
  const { element, period_label, duration } = cell.value;
  const period = duration ? `${duration.toLowerCase()} to ${period_label}` : period_label;
  return `${company}: ${element.replace(/^us-gaap_/, "")}, ${period}`;
}

/**
 * The column header's second line: which period this company's figures cover.
 *
 * Only the date. The form is stated once in the panel's own meta line, and
 * repeating it per column wrapped the caption inside a 108px column for no
 * information -- every column of a comparison is the same form by construction.
 *
 * It matters because two companies rarely share a year end: Apple's runs to
 * late September and NVIDIA's to late January, so the columns are not the same
 * twelve months and the reader has to be able to see that.
 */
export function periodCaption(periodEnd: string | null): string {
  return periodEnd ?? "period unknown";
}

/**
 * What the board's compare control should say, or nothing at all.
 *
 * A comparison already showing exactly the companies on the board leaves the
 * control with nothing to do, so it goes away -- "Compare 2 companies" sitting
 * above the comparison of those two companies reads as though the click never
 * landed. Adding or removing a company brings it back as an update, because
 * the panel is now out of date with the board it summarises.
 */
export function compareLabel(
  board: readonly string[],
  compared: readonly string[] | null,
): string | null {
  if (board.length < 2) return null;
  if (compared === null) return `Compare ${board.length} companies`;

  const same =
    compared.length === board.length && new Set([...board, ...compared]).size === board.length;
  return same ? null : "Update comparison";
}
