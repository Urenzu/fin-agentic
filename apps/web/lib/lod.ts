/**
 * Level of detail for canvas nodes.
 *
 * A statement rendered at 11px is unreadable once the board is zoomed out to
 * fit four companies, and shrinking further just turns each node into a grey
 * rectangle -- you can see there is something there but not what. Rather than
 * render the same thing smaller, nodes render *less* as they get further away,
 * and what survives is drawn at a size that does not change on screen.
 */

import type { AsFiledRow, AsFiledStatement } from "./types";

/**
 * Below this zoom the statement table is replaced by a summary.
 *
 * Picked from the row height: body rows are 23px, so at 0.55 they land near
 * 12.6 screen px, which is about where a dense table stops being legible and
 * starts being texture.
 */
export const SUMMARY_BELOW = 0.55;

/** Below this, even the summary's figures go and only the identity remains. */
export const IDENTITY_BELOW = 0.28;

/**
 * The multiplier that holds a label at a constant size on screen.
 *
 * At zoom 0.4 a 12px label renders at 4.8px; multiplying by 1/zoom restores it
 * to 12px. Only applied when zoomed out -- past 1:1 text should grow with
 * everything else, or zooming in would leave labels stuck at their minimum.
 *
 * Capped because the correction is unbounded as zoom approaches 0: without a
 * cap, a title at zoom 0.05 would be set at 240px and overflow the node it
 * belongs to.
 */
export function counterScale(zoom: number, cap = 3.2): number {
  if (!Number.isFinite(zoom) || zoom <= 0) return cap;
  return Math.min(Math.max(1 / zoom, 1), cap);
}

/**
 * The lines worth keeping when a statement is too far away to read.
 *
 * Totals are the filer's own summary of the statement -- "Total net sales",
 * "Total assets", "Net income" -- so they carry the most meaning per pixel.
 * Rows without a value in the newest column are skipped: a headline figure
 * showing an em dash tells the reader nothing.
 */
export function headlineRows(statement: AsFiledStatement, limit = 3): AsFiledRow[] {
  const newest = statement.columns[0];
  if (newest === undefined) return [];

  const usable = statement.rows.filter(
    (row) => !row.is_abstract && row.values[newest] !== undefined,
  );

  const totals = usable.filter((row) => row.is_total);
  // A cash flow statement can carry a dozen subtotals while a comprehensive
  // income statement carries none, so fall back rather than render an empty
  // card for the statements that happen not to mark totals.
  const chosen = totals.length > 0 ? totals : usable;

  return chosen.slice(0, limit);
}

/**
 * `counterScale`, bounded by what the node can actually hold.
 *
 * The correction is applied to the header's padding and type together, so a
 * header that occupies 66px at 1:1 wants 211px at the cap. An entity card is
 * only ~154px tall, and the magnified header pushed its own contents out of
 * the panel -- the ticker it exists to show ended up clipped in half.
 *
 * Limiting the header to `share` of the node keeps the correction as large as
 * the geometry permits and no larger.
 */
export function fitScale(zoom: number, nodeHeight: number, share = 0.5, headerHeight = 66): number {
  const affordable = (nodeHeight * share) / headerHeight;
  return Math.max(Math.min(counterScale(zoom), affordable), 1);
}

/** A headline block: its caption, its figure, and the gap beneath it. */
const HEADLINE_BLOCK = 44;

/**
 * How many headline rows fit once the magnified header has taken its share.
 *
 * Both the header and the figures are scaled by the same correction, so the
 * number that fits falls as the board is zoomed out. Rendering a fixed three
 * clipped the last figure in half, which reads as a broken panel rather than
 * as an omission -- and a half-visible number is worse than no number.
 */
export function headlineCapacity(nodeHeight: number, scale: number, headerHeight = 66): number {
  const available = nodeHeight - (headerHeight + 16) * scale;
  return Math.max(Math.floor(available / (HEADLINE_BLOCK * scale)), 0);
}
