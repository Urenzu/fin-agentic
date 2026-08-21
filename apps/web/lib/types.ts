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
  /**
   * How many figures EDGAR published for this filer. A sense of scale, not a
   * quality measure -- there was once a "corroborated" ratio here, which read
   * as an accuracy score while measuring how much of a canonical ledger some
   * accounting identity happened to touch. Both the ledger and the ratio are
   * gone.
   */
  observations: number;
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
