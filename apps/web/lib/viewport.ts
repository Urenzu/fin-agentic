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
  maxZoom = 1,
): Viewport | null {
  const bounds = boundsOf(boxes);
  if (bounds === null) return null;

  const availableWidth = Math.max(width - EDGE * 2, 1);
  const availableHeight = Math.max(height - HUD_INSET - EDGE, 1);

  const zoom = Math.min(
    bounds.width > 0 ? availableWidth / bounds.width : maxZoom,
    bounds.height > 0 ? availableHeight / bounds.height : maxZoom,
    maxZoom,
  );

  return {
    x: EDGE + (availableWidth - bounds.width * zoom) / 2 - bounds.x * zoom,
    y: HUD_INSET + (availableHeight - bounds.height * zoom) / 2 - bounds.y * zoom,
    zoom,
  };
}
