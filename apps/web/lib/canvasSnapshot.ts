import type { CanvasNode } from "./canvas";

/**
 * Turning a board into something worth saving, and back.
 *
 * What is stored is references, never figures: a CIK, an accession, a
 * position. The numbers themselves stay on EDGAR, where they are exact and
 * already cached, and keeping a copy would mean a second version of figures
 * whose entire value is that they match the filing -- one that could drift
 * after a restatement and be believed anyway.
 *
 * It is also the difference between a canvas measured in bytes and one
 * measured in megabytes: a filing's five statements come to roughly 420KB of
 * rendered exhibit, and browser storage holds about five.
 */

/** The board node shape this reads, whatever else it carries. */
export type SnapshottableNode = {
  id: string;
  type?: string;
  position: { x: number; y: number };
  width?: number | null;
  height?: number | null;
  data: Record<string, unknown>;
};

function size(node: SnapshottableNode) {
  return {
    ...(typeof node.width === "number" ? { width: node.width } : {}),
    ...(typeof node.height === "number" ? { height: node.height } : {}),
  };
}

export function toSnapshot(nodes: readonly SnapshottableNode[]): CanvasNode[] {
  const saved: CanvasNode[] = [];

  for (const node of nodes) {
    const at = { x: node.position.x, y: node.position.y, ...size(node) };

    if (node.type === "entity") {
      const entity = node.data.entity as
        { registrant?: { cik?: number; ticker?: string; name?: string } } | undefined;
      const registrant = entity?.registrant;
      if (registrant?.cik === undefined) continue;
      saved.push({
        kind: "entity",
        cik: registrant.cik,
        ticker: registrant.ticker ?? "",
        name: registrant.name ?? "",
        ...at,
      });
      continue;
    }

    if (node.type === "statement") {
      const cik = node.data.cik as number | undefined;
      const statement = node.data.statement as
        { accession?: string; form?: string; short_name?: string } | undefined;
      if (cik === undefined || statement?.accession === undefined) continue;
      saved.push({
        kind: "statement",
        cik,
        accession: statement.accession,
        form: statement.form ?? "10-K",
        shortName: statement.short_name ?? "",
        ...at,
      });
      continue;
    }

    if (node.type === "comparison") {
      const companies = node.data.companies as { cik: number; ticker: string }[] | undefined;
      if (companies === undefined || companies.length === 0) continue;
      saved.push({
        kind: "comparison",
        companies,
        form: (node.data.form as string | undefined) ?? "10-K",
        ...at,
      });
    }
  }

  return saved;
}

/**
 * The filings a snapshot needs fetched before it can be drawn.
 *
 * Grouped by filing rather than by panel: one filing's statements arrive
 * together in a single request, so five saved panels of one 10-K are one fetch
 * rather than five.
 */
export function filingsToRestore(
  nodes: readonly CanvasNode[],
): { cik: number; accession: string; form: string }[] {
  const seen = new Map<string, { cik: number; accession: string; form: string }>();
  for (const node of nodes) {
    if (node.kind !== "statement") continue;
    const key = `${node.cik}:${node.accession}`;
    if (!seen.has(key)) {
      seen.set(key, { cik: node.cik, accession: node.accession, form: node.form });
    }
  }
  return [...seen.values()];
}

/** The companies a snapshot needs resolved, in the order they were added. */
export function companiesToRestore(
  nodes: readonly CanvasNode[],
): { cik: number; ticker: string; name: string }[] {
  return nodes.flatMap((node) =>
    node.kind === "entity" ? [{ cik: node.cik, ticker: node.ticker, name: node.name }] : [],
  );
}
