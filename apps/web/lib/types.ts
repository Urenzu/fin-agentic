/**
 * Mirrors `finagentic.api.schemas`. Money is `string` throughout, matching the
 * API's decision to keep decimals off the JSON number type -- see lib/decimal.
 */

export type IngestState = "ingesting" | "ready" | "error";

export type Registrant = {
  cik: number;
  ticker: string;
  name: string;
};

export type Shape = {
  shape: string;
  supported: boolean;
  message: string;
  evidence: string[];
};

export type Coverage = {
  earliest: string | null;
  latest: string | null;
  history_years: number;
  annual_reports: number;
  looks_truncated: boolean;
  fact_count: number;
  verified_count: number;
};

export type Entity = {
  registrant: Registrant;
  state: IngestState;
  shape: Shape | null;
  coverage: Coverage | null;
  error: string | null;
  advisories: string[];
};

export type AsFiledRow = {
  label: string;
  element: string | null;
  tag: string | null;
  is_abstract: boolean;
  is_total: boolean;
  indent: number;
  /** Keyed by `AsFiledColumn.key`. A missing key is a blank cell, not a zero. */
  values: Record<string, string>;
};

export type AsFiledColumn = {
  /**
   * Unique within the statement, and what `AsFiledRow.values` is keyed by.
   * `label` is not unique: a 10-Q prints the same period end under both
   * "3 Months Ended" and "9 Months Ended".
   */
  key: string;
  label: string;
  /** The spanning heading, e.g. "3 Months Ended". Null for an instant. */
  duration: string | null;
  date: string | null;
};

export type AsFiledStatement = {
  title: string;
  short_name: string;
  columns: AsFiledColumn[];
  rows: AsFiledRow[];
  monetary_scale: string;
  share_scale: string;
  accession: string;
  form: string;
  filed: string;
  source_url: string;
};

export type FilingIndex = {
  accession: string;
  form: string;
  filed: string;
  period_end: string | null;
  source_url: string;
  statements: { filename: string; name: string }[];
};

export type ValidationResult = {
  check_id: string;
  identity: string;
  status: "passed" | "failed" | "skipped";
  severity: string;
  period_label: string;
  expected: string | null;
  actual: string | null;
  delta: string | null;
  tolerance: string | null;
  missing: string[];
  message: string;
};

export type Validation = {
  passed: number;
  failed: number;
  skipped: number;
  is_clean: boolean;
  results: ValidationResult[];
};
