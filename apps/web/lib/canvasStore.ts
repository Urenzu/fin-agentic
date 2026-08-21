import { createCanvas, type Canvas } from "./canvas";

/**
 * Where saved canvases live until there is a server to keep them.
 *
 * `localStorage`, behind a narrow interface, for the same reason the EDGAR
 * cache went behind one: this is the wrong home eventually. Canvases are the
 * reader's own work and belong somewhere that survives a cleared browser and
 * follows them to another machine, which means Postgres and an account. Naming
 * the two operations now means that swap does not reach into the board.
 *
 * Every access is guarded. `localStorage` is not merely empty in a private
 * window -- reading it *throws* when a browser is set to block site data, and
 * an exception here would take the whole board down rather than losing a list
 * of names.
 */

const KEY = "finagentic.canvases.v1";

export type StoredState = {
  canvases: Canvas[];
  selected: string;
};

/** A first-run state: one empty canvas, because the board needs somewhere to put things. */
export function initialState(now = Date.now()): StoredState {
  const first = createCanvas([], now);
  return { canvases: [first], selected: first.id };
}

/**
 * Whether a parsed value is a canvas we can use.
 *
 * Storage is shared with whatever else the origin has ever written and with
 * every earlier version of this code, so what comes back is untrusted input.
 * A half-valid canvas would crash the sidebar on render, which is a worse
 * outcome than starting fresh.
 */
function isCanvas(value: unknown): value is Canvas {
  if (typeof value !== "object" || value === null) return false;
  const canvas = value as Record<string, unknown>;
  return (
    typeof canvas.id === "string" &&
    typeof canvas.name === "string" &&
    typeof canvas.pinned === "boolean" &&
    typeof canvas.updatedAt === "number" &&
    Array.isArray(canvas.nodes)
  );
}

export function load(storage: Storage | undefined = safeStorage()): StoredState {
  if (storage === undefined) return initialState();

  let raw: string | null = null;
  try {
    raw = storage.getItem(KEY);
  } catch {
    return initialState();
  }
  if (raw === null) return initialState();

  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return initialState();

    const { canvases, selected } = parsed as Record<string, unknown>;
    const kept = Array.isArray(canvases) ? canvases.filter(isCanvas) : [];
    if (kept.length === 0) return initialState();

    // A selection naming a canvas that is gone would leave the board blank
    // with no way back, so it falls to the first one.
    const chosen =
      typeof selected === "string" && kept.some((canvas) => canvas.id === selected)
        ? selected
        : kept[0]!.id;
    return { canvases: kept, selected: chosen };
  } catch {
    return initialState();
  }
}

export function save(state: StoredState, storage: Storage | undefined = safeStorage()): void {
  if (storage === undefined) return;
  try {
    storage.setItem(KEY, JSON.stringify(state));
  } catch {
    // Out of quota, or site data blocked. The reader keeps working on the
    // board they have; only the record of it is lost, and crashing over that
    // would be the worse trade.
  }
}

/** `localStorage`, or undefined where touching it would throw. */
export function safeStorage(): Storage | undefined {
  try {
    return typeof window === "undefined" ? undefined : window.localStorage;
  } catch {
    return undefined;
  }
}
