/**
 * Framing the board.
 *
 * React Flow's own `fitView` has to wait for every node to be measured by a
 * ResizeObserver, which makes the result depend on when it happens to be
 * called -- it silently no-ops before measurement and, under StrictMode's
 * double mount, that window is unpredictable. Every dimension here is known up
 * front, so the viewport is computed directly instead. That also makes it
 * ordinary arithmetic, and testable without a browser.
 */

export type Box = {
  position: { x: number; y: number };
  width?: number;
  height?: number;
};

export type Viewport = { x: number; y: number; zoom: number };

/** Room left for the floating search bar, so it never covers a node header. */
export const HUD_INSET = 104;
const EDGE = 48;

export function boundsOf(boxes: readonly Box[]): {
  x: number;
  y: number;
  width: number;
  height: number;
} | null {
  if (boxes.length === 0) return null;

  const left = Math.min(...boxes.map((b) => b.position.x));
  const top = Math.min(...boxes.map((b) => b.position.y));
  const right = Math.max(...boxes.map((b) => b.position.x + (b.width ?? 0)));
  const bottom = Math.max(...boxes.map((b) => b.position.y + (b.height ?? 0)));

  return { x: left, y: top, width: right - left, height: bottom - top };
}

export type FrameOptions = {
  /** Never zoom past this. */
  maxZoom?: number;
  /**
   * Never zoom below this, even if the boxes then overflow the pane.
   *
   * Fitting everything is the wrong goal when the reader has just asked to
   * read something: the box spanning a company card and a filing row two bands
   * down fits only at a zoom that collapses the statements into headline
   * figures, which is precisely what opening them was meant to avoid.
   */
  minZoom?: number;
  /** What to centre on when the floor wins and the boxes no longer fit. */
  anchor?: Box;
};

/**
 * The viewport that centres `boxes` inside a `width` x `height` pane.
 *
 * Never zooms past 1: a single narrow statement blown up to fill a wide screen
 * looks broken, and the figures gain nothing from being larger.
 */
export function frame(
  boxes: readonly Box[],
  width: number,
  height: number,
  { maxZoom = 1, minZoom = 0, anchor }: FrameOptions = {},
): Viewport | null {
  const bounds = boundsOf(boxes);
  if (bounds === null) return null;

  const availableWidth = Math.max(width - EDGE * 2, 1);
  const availableHeight = Math.max(height - HUD_INSET - EDGE, 1);

  const fitted = Math.min(
    bounds.width > 0 ? availableWidth / bounds.width : maxZoom,
    bounds.height > 0 ? availableHeight / bounds.height : maxZoom,
    maxZoom,
  );

  const zoom = Math.max(fitted, Math.min(minZoom, maxZoom));

  // Once the floor has overruled the fit, the bounds are wider or taller than
  // the pane, and centring them would push the thing the reader asked for off
  // one edge while showing empty canvas at the other. Centre the anchor.
  const focus = (zoom > fitted ? boundsOf(anchor ? [anchor] : []) : null) ?? bounds;

  return {
    x: EDGE + (availableWidth - focus.width * zoom) / 2 - focus.x * zoom,
    y: HUD_INSET + (availableHeight - focus.height * zoom) / 2 - focus.y * zoom,
    zoom,
  };
}
