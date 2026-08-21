/**
 * Where a filing's statements go when they are opened.
 *
 * Derived from the board rather than counted. The board used to keep a tally
 * per company of how many filing rows had been opened, and place the next one
 * that many rows down. Nothing decremented it: closing a filing or deleting
 * its panels left the count where it was, so the next filing opened into an
 * empty band far below everything -- one row further down for every filing the
 * reader had ever opened and closed, which reads as the statements no longer
 * appearing beside the company at all.
 *
 * Asking the board what is actually occupied cannot drift, because there is no
 * second copy of the truth to fall out of step. It also means the card's
 * current position is used rather than the position it was created at, so
 * statements follow a card the reader has dragged.
 */

/** The shape of a board node this needs, whatever else it carries. */
export type PlaceableNode =
  | { id: string; type: "entity"; position: { x: number; y: number } }
  | {
      id: string;
      type: "statement";
      position: { x: number; y: number };
      data: { cik: number };
    }
  | { id: string; type: string; position: { x: number; y: number } };

export type RowLayout = {
  /** Left edge of a filing's row: one gap right of the company column. */
  originX: number;
  /** Vertical distance between one filing's row and the next. */
  rowPitch: number;
};

/**
 * The first free row band beside a company's card.
 *
 * Bands are numbered from the card's own top edge, so the first filing opened
 * sits level with it. A band is free when no statement of that company
 * occupies it, which is what makes reopening a closed filing land back in the
 * gap it left rather than below everything.
 */
export function nextRowOrigin(
  nodes: readonly PlaceableNode[],
  cik: number,
  { originX, rowPitch }: RowLayout,
): { x: number; y: number } {
  const card = nodes.find((node) => node.id === `entity-${cik}`);
  const baseY = card?.position.y ?? 0;

  const occupied = new Set<number>();
  for (const node of nodes) {
    if (node.type !== "statement") continue;
    const statement = node as Extract<PlaceableNode, { type: "statement" }>;
    if (statement.data.cik !== cik) continue;
    // Rounded, because a reader may have nudged a panel a few pixels while
    // dragging and the band it belongs to is still obvious.
    const band = Math.round((statement.position.y - baseY) / rowPitch);
    if (band >= 0) occupied.add(band);
  }

  let band = 0;
  while (occupied.has(band)) band += 1;
  return { x: originX, y: baseY + band * rowPitch };
}

/**
 * Where a new company's card goes: below everything already on the board.
 *
 * Measured from what is there rather than from a running total, so a board
 * that has had companies removed closes up instead of leaving the next arrival
 * stranded past the gap they left.
 */
export function nextCardOrigin(
  nodes: readonly { position: { x: number; y: number }; height?: number | null }[],
  gap: number,
  defaultHeight: number,
): { x: number; y: number } {
  if (nodes.length === 0) return { x: 0, y: 0 };
  const bottom = nodes.reduce(
    (lowest, node) => Math.max(lowest, node.position.y + (node.height ?? defaultHeight)),
    0,
  );
  return { x: 0, y: bottom + gap };
}
