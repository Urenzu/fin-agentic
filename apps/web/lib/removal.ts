/**
 * Taking a panel off the board, and everything that follows from it.
 *
 * Removal is not just dropping a node. A company card is the thing its
 * statements were opened from and the thing a comparison draws on, so deleting
 * one leaves work behind that has to be cleaned up in the same step -- and the
 * filing picker has to stop claiming a filing is open once its statements are
 * gone, or the reader is left with a row they cannot re-open because the board
 * thinks it already did.
 *
 * Kept apart from the board component because it is the only part of removal
 * with any judgement in it, and judgement is worth testing.
 */

/** The shape of a board node this needs, whatever else it carries. */
export type RemovableNode =
  | { id: string; type: "entity"; data: { entity: { registrant: { cik: number } } } }
  | { id: string; type: "statement"; data: { cik: number; statement: { accession: string } } }
  | { id: string; type: "comparison"; data: { companies: { cik: number; ticker: string }[] } };

export type Removal<T> = {
  nodes: T[];
  /**
   * Filings with no statements left on the board. The picker marks a filing as
   * open, and a filing whose panels have all been closed is not open -- leaving
   * it marked means a row that looks active and does nothing when clicked.
   */
  closedAccessions: string[];
};

/** The companies a comparison would still be drawn from without `cik`. */
function withoutCompany<T extends RemovableNode>(node: T, cik: number) {
  return node.type === "comparison"
    ? node.data.companies.filter((company) => company.cik !== cik)
    : [];
}

/**
 * Remove `id` and whatever depended on it.
 *
 * Deleting a company takes its statements with it. The alternative is a row of
 * panels still on the board whose card is gone -- unreachable from the picker
 * that opened them, and connected to nothing. A comparison loses that company
 * as a column, and goes entirely if fewer than two are left, because a
 * comparison of one company is a list.
 */
export function removeFromBoard<T extends RemovableNode>(nodes: T[], id: string): Removal<T> {
  const target = nodes.find((node) => node.id === id);
  if (target === undefined) return { nodes, closedAccessions: [] };

  const cik = target.type === "entity" ? target.data.entity.registrant.cik : null;

  const kept = nodes.filter((node) => {
    if (node.id === id) return false;
    if (cik !== null && node.type === "statement" && node.data.cik === cik) return false;
    // A comparison of one company is a list, so it goes rather than shrinking
    // to a single column.
    if (cik !== null && node.type === "comparison") return withoutCompany(node, cik).length >= 2;
    return true;
  });

  const survivors = kept.map((node) =>
    cik !== null && node.type === "comparison"
      ? ({ ...node, data: { ...node.data, companies: withoutCompany(node, cik) } } as T)
      : node,
  );

  const remaining = new Set(
    survivors.flatMap((node) => (node.type === "statement" ? [node.data.statement.accession] : [])),
  );
  const removed = new Set(
    nodes.flatMap((node) =>
      node.type === "statement" && !survivors.some((kept) => kept.id === node.id)
        ? [node.data.statement.accession]
        : [],
    ),
  );

  return {
    nodes: survivors,
    closedAccessions: [...removed].filter((accession) => !remaining.has(accession)),
  };
}
