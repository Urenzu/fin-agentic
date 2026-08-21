/**
 * Boards a reader keeps, and the list of them in the sidebar.
 *
 * A canvas is a saved arrangement: which companies are on the board, which
 * filings are open, where everything sits. It stores *references* rather than
 * figures -- a company's CIK, a filing's accession, a position -- because the
 * figures are already exact on EDGAR and re-reading them is cheap, while
 * keeping a copy would be a second version of numbers whose whole value is
 * that they match the filing.
 */

export type CanvasNode =
  | {
      kind: "entity";
      cik: number;
      ticker: string;
      name: string;
      x: number;
      y: number;
      width?: number;
      height?: number;
    }
  | {
      kind: "statement";
      cik: number;
      accession: string;
      form: string;
      /** Which statement of the filing, so a row rebuilds in the same order. */
      shortName: string;
      x: number;
      y: number;
      width?: number;
      height?: number;
    }
  | {
      kind: "comparison";
      companies: { cik: number; ticker: string }[];
      form: string;
      x: number;
      y: number;
      width?: number;
      height?: number;
    };

export type Canvas = {
  id: string;
  name: string;
  /** Pinned canvases sort to the top, whatever their age. */
  pinned: boolean;
  /** Epoch milliseconds. Ordering within the unpinned group. */
  updatedAt: number;
  nodes: CanvasNode[];
};

export const DEFAULT_NAME = "Untitled canvas";

/** A name not already taken, so a list of canvases can be told apart. */
export function uniqueName(existing: readonly Canvas[], base = DEFAULT_NAME): string {
  const taken = new Set(existing.map((canvas) => canvas.name));
  if (!taken.has(base)) return base;
  for (let n = 2; ; n += 1) {
    const candidate = `${base} ${n}`;
    if (!taken.has(candidate)) return candidate;
  }
}

export function createCanvas(existing: readonly Canvas[], now = Date.now()): Canvas {
  return {
    // `crypto.randomUUID` is unavailable over plain http on some browsers, and
    // an id that fails to generate would silently collide with the last one.
    id: `canvas-${now.toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    name: uniqueName(existing),
    pinned: false,
    updatedAt: now,
    nodes: [],
  };
}

/**
 * A canvas's tickers, so searching for a company finds the boards it is on.
 *
 * The reader remembers "the one with Apple and Costco" far more often than
 * whatever they called it, and matching only the name would make the search
 * useless for exactly the canvases worth finding.
 */
export function tickersOf(canvas: Canvas): string[] {
  const found = new Set<string>();
  for (const node of canvas.nodes) {
    if (node.kind === "entity") found.add(node.ticker);
    if (node.kind === "comparison") {
      for (const company of node.companies) found.add(company.ticker);
    }
  }
  return [...found].filter((ticker) => ticker !== "");
}

export function matches(canvas: Canvas, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (needle === "") return true;
  if (canvas.name.toLowerCase().includes(needle)) return true;
  return tickersOf(canvas).some((ticker) => ticker.toLowerCase().includes(needle));
}

/**
 * The sidebar's order: pinned first, then most recently touched.
 *
 * Pinning is what a reader does to the two or three boards they return to, so
 * it outranks recency entirely -- a pinned canvas untouched for a month still
 * belongs above one opened this morning, or pinning would not mean anything.
 */
export function ordered(canvases: readonly Canvas[], query = ""): Canvas[] {
  return canvases
    .filter((canvas) => matches(canvas, query))
    .slice()
    .sort((a, b) => {
      if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
      if (b.updatedAt !== a.updatedAt) return b.updatedAt - a.updatedAt;
      // A stable last resort, so two canvases saved in the same millisecond do
      // not swap places between renders.
      return a.id < b.id ? -1 : 1;
    });
}

/** Apply a change to one canvas, marking it touched. */
export function update(
  canvases: readonly Canvas[],
  id: string,
  change: Partial<Omit<Canvas, "id">>,
  now = Date.now(),
): Canvas[] {
  return canvases.map((canvas) =>
    canvas.id === id ? { ...canvas, ...change, updatedAt: now } : canvas,
  );
}

/**
 * Rename, refusing a name that is only whitespace.
 *
 * An empty name leaves a row in the sidebar with nothing to click on and no
 * way to tell it from its neighbours, so the previous name stands.
 */
export function rename(
  canvases: readonly Canvas[],
  id: string,
  name: string,
  now = Date.now(),
): Canvas[] {
  const trimmed = name.trim();
  if (trimmed === "") return canvases.slice();
  return update(canvases, id, { name: trimmed }, now);
}

/**
 * Pin or unpin.
 *
 * Takes no clock, unlike every other change here, and that is the point:
 * pinning is not editing. Touching `updatedAt` would reorder the recency the
 * pinned group sits above, so pinning a canvas would quietly demote whatever
 * you pinned it beside.
 */
export function togglePin(canvases: readonly Canvas[], id: string): Canvas[] {
  return canvases.map((c) => (c.id === id ? { ...c, pinned: !c.pinned } : c));
}

/**
 * Remove a canvas, and say which one to open instead.
 *
 * Never leaves the reader with nothing: deleting the last canvas creates a
 * fresh one, because a board with no canvas has nowhere to put anything.
 */
export function remove(
  canvases: readonly Canvas[],
  id: string,
  now = Date.now(),
): { canvases: Canvas[]; selected: string } {
  const kept = canvases.filter((canvas) => canvas.id !== id);
  if (kept.length === 0) {
    const fresh = createCanvas([], now);
    return { canvases: [fresh], selected: fresh.id };
  }
  const next = ordered(kept)[0];
  return { canvases: kept, selected: next?.id ?? kept[0]!.id };
}
