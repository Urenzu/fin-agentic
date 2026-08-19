/**
 * How a filing is described in the picker.
 *
 * Deliberately factual. It is tempting to label a 10-K "FY2025" and a 10-Q
 * "Q3", but neither follows from the filing: a retailer whose year ends in
 * January calls that year FY2026 while the period ends in 2026, and quarter
 * numbering depends on where the fiscal year starts, which the filing index
 * does not carry. Printing the period the filer actually reported is always
 * right, and is what the statement columns show anyway.
 */

import type { FilingIndex } from "./types";

export function formatFilingDate(iso: string): string {
  // Parsed as parts rather than by Date so a bare "2025-09-27" is not shifted
  // into the previous day by the browser's timezone.
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) return iso;
  const [, year, month, day] = match;
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/** "Year ended Sep 27, 2025" — the period the filing reports on. */
export function filingPeriodLabel(filing: FilingIndex): string {
  if (filing.period_end === null) return filing.form;
  const span = filing.form.startsWith("10-K") ? "Year ended" : "Quarter ended";
  return `${span} ${formatFilingDate(filing.period_end)}`;
}

/** "filed Oct 31, 2025" — when it reached EDGAR, which is not the same thing. */
export function filingFiledLabel(filing: FilingIndex): string {
  return `filed ${formatFilingDate(filing.filed)}`;
}

export const FORMS = ["10-K", "10-Q"] as const;
export type FilingForm = (typeof FORMS)[number];
