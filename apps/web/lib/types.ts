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
  /**
   * Facts taking part in at least one satisfied accounting identity.
   *
   * Not a quality score, and deliberately not shown as a share of
   * `fact_count`. A fact counts as verified only when some identity happens to
   * touch it, so a correct figure no check covers stays unverified forever --
   * the ratio can never reach 100% and its distance from 100% says nothing
   * about whether anything is wrong.
   */
  verified_count: number;
  /**
   * How the accounting identities fared over this ledger.
   *
   * Carried on the entity summary so a caller can size up a ledger without
   * fetching the validation endpoint, which returns every individual result --
   * about 1,600 of them for a filer with twenty years of history.
   */
  checks_passed: number;
  checks_failed: number;
  checks_skipped: number;
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

export type MetricValue = {
  metric: string;
  label: string;
  /** Full scale, as a decimal string. Never a JSON number. */
  value: string;
  /**
   * The us-gaap element this came from. Two filers reporting the same metric
   * under different names is why the mapping exists, so which line was used
   * stays inspectable.
   */
  element: string;
  period_label: string;
  period_end: string | null;
  duration: string | null;
};

export type MetricDescriptor = {
  metric: string;
  label: string;
  /** "instant" for a balance, "duration" for a flow. */
  kind: string;
  /** "USD", "shares" or "USD/share". */
  unit: string;
};

export type CompanyMetrics = {
  registrant: Registrant;
  accession: string;
  form: string;
  filed: string;
  period_end: string | null;
  /** Keyed by metric, newest period first. */
  metrics: Record<string, MetricValue[] | undefined>;
  /** Metrics this filer does not report. The filer's choice, not a gap. */
  absent: string[];
};

export type Comparison = {
  companies: CompanyMetrics[];
  /** Every metric in display order, so the table keeps its shape. */
  metrics: MetricDescriptor[];
};
