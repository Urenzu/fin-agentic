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
 * The magnifications a label is allowed to take.
 *
 * The correction is quantised rather than applied continuously, and this is
 * what makes zooming feel deliberate instead of noisy. Sized off `1/zoom`
 * directly, every node re-laid its text on every frame of a zoom gesture --
 * font size is not a composited property, so each change reflowed the panel
 * and the text visibly crawled. Snapping to a handful of steps means the type
 * holds still through most of a gesture and moves once, at a known place.
 *
 * It also makes the change collective. Bounded per node, a short card reached
 * its limit at a different zoom than a tall one, so panels changed one after
 * another and the board looked like it was rearranging itself at random.
 */
export const SCALE_STEPS = [1, 1.4, 2, 2.8, 3.6] as const;

/** The largest step at or below `value`. */
export function quantize(value: number, steps: readonly number[] = SCALE_STEPS): number {
  let chosen = steps[0] ?? 1;
  for (const step of steps) {
    if (step <= value) chosen = step;
  }
  return chosen;
}

/**
 * The zoom thresholds are derived from the steps rather than chosen alongside
 * them, so a tier change and a magnification change are the same event. Picked
 * independently they landed a little apart, and one gesture produced two pops.
 */
export const SUMMARY_BELOW = 1 / 2;
export const IDENTITY_BELOW = 1 / 3.6;

export type Tier = "detail" | "summary" | "identity";

/**
 * What a node should render at this zoom.
 *
 * Selecting on this rather than on the raw zoom is what stops a re-render on
 * every frame: it collapses a continuous number to one of three values, so a
 * store subscription only fires when the answer actually changes.
 */
export function tierFor(zoom: number): Tier {
  if (!Number.isFinite(zoom) || zoom <= 0) return "identity";
  if (zoom < IDENTITY_BELOW) return "identity";
  if (zoom < SUMMARY_BELOW) return "summary";
  return "detail";
}

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
export function counterScale(zoom: number, cap = 3.6): number {
  if (!Number.isFinite(zoom) || zoom <= 0) return cap;
  return Math.min(Math.max(1 / zoom, 1), cap);
}

/**
 * The correction a node should actually use: continuous, then snapped.
 *
 * Subscribe to this rather than to zoom. It changes a handful of times across
 * the whole zoom range, so the text it sizes stays put in between.
 */
export function stepScale(zoom: number): number {
  return quantize(counterScale(zoom));
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
  // Bounded against the *stepped* correction, so the result changes only when
  // the step does. Against the continuous one it drifted with every frame.
  return Math.max(Math.min(stepScale(zoom), affordable), 1);
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
