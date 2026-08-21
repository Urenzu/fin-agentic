import assert from "node:assert/strict";
import { test } from "node:test";

import type { Canvas } from "./canvas";
import { initialState, load, save, type StoredState } from "./canvasStore";
import {
  companiesToRestore,
  filingsToRestore,
  toSnapshot,
  type SnapshottableNode,
} from "./canvasSnapshot";

/** A `Storage` that behaves, and one that throws the way a locked-down browser does. */
function memoryStorage(initial: Record<string, string> = {}): Storage {
  const map = new Map(Object.entries(initial));
  return {
    get length() {
      return map.size;
    },
    clear: () => map.clear(),
    getItem: (k: string) => map.get(k) ?? null,
    key: (i: number) => [...map.keys()][i] ?? null,
    removeItem: (k: string) => void map.delete(k),
    setItem: (k: string, v: string) => void map.set(k, v),
  };
}

function hostileStorage(): Storage {
  const throwing = () => {
    throw new DOMException("blocked");
  };
  return {
    get length(): number {
      return throwing();
    },
    clear: throwing,
    getItem: throwing,
    key: throwing,
    removeItem: throwing,
    setItem: throwing,
  } as unknown as Storage;
}

const canvas = (partial: Partial<Canvas> & { id: string }): Canvas => ({
  name: partial.id,
  pinned: false,
  updatedAt: 0,
  nodes: [],
  ...partial,
});

// ---------------------------------------------------------------------------
// storage
// ---------------------------------------------------------------------------

test("a first run starts with one empty canvas", () => {
  // The board needs somewhere to put things, so there is never zero.
  const state = load(memoryStorage());
  assert.equal(state.canvases.length, 1);
  assert.equal(state.selected, state.canvases[0]?.id);
});

test("what was saved comes back", () => {
  const storage = memoryStorage();
  const state: StoredState = {
    canvases: [canvas({ id: "a", name: "Semis" })],
    selected: "a",
    sidebar: false,
  };
  save(state, storage);
  assert.deepEqual(load(storage), state);
});

test("storage that throws does not take the board down with it", () => {
  // A browser set to block site data throws on access rather than returning
  // empty, and losing a list of names is a better outcome than a blank page.
  assert.doesNotThrow(() => load(hostileStorage()));
  assert.doesNotThrow(() => save(initialState(), hostileStorage()));
  assert.equal(load(hostileStorage()).canvases.length, 1);
});

test("nothing stored is a first run, not a crash", () => {
  assert.equal(load(memoryStorage()).canvases.length, 1);
});

test("unparseable storage starts fresh instead of throwing", () => {
  const storage = memoryStorage({ "finagentic.canvases.v1": "{not json" });
  assert.equal(load(storage).canvases.length, 1);
});

test("a half-valid canvas is discarded rather than rendered", () => {
  // Storage is shared with every earlier version of this code, so what comes
  // back is untrusted input; a malformed canvas would crash the sidebar.
  const storage = memoryStorage({
    "finagentic.canvases.v1": JSON.stringify({
      canvases: [{ id: "ok", name: "Fine", pinned: false, updatedAt: 1, nodes: [] }, { id: 7 }],
      selected: "ok",
    }),
  });
  const state = load(storage);
  assert.equal(state.canvases.length, 1);
  assert.equal(state.canvases[0]?.id, "ok");
});

test("a selection naming a canvas that is gone falls back to one that exists", () => {
  // Otherwise the board opens blank with no way back to anything.
  const storage = memoryStorage({
    "finagentic.canvases.v1": JSON.stringify({
      canvases: [{ id: "a", name: "A", pinned: false, updatedAt: 1, nodes: [] }],
      selected: "deleted-long-ago",
    }),
  });
  assert.equal(load(storage).selected, "a");
});

// ---------------------------------------------------------------------------
// snapshots
// ---------------------------------------------------------------------------

const board: SnapshottableNode[] = [
  {
    id: "entity-320193",
    type: "entity",
    position: { x: 0, y: 0 },
    width: 360,
    height: 560,
    data: { entity: { registrant: { cik: 320193, ticker: "AAPL", name: "Apple Inc." } } },
  },
  {
    id: "stmt-1",
    type: "statement",
    position: { x: 400, y: 0 },
    data: {
      cik: 320193,
      statement: {
        accession: "0000320193-25-000079",
        form: "10-K",
        short_name: "CONSOLIDATED STATEMENTS OF OPERATIONS",
        // A whole statement's worth of rows would be saved too, if the
        // snapshot kept figures. It does not.
        rows: Array.from({ length: 60 }, (_, i) => ({ label: `Line ${i}` })),
      },
    },
  },
  {
    id: "comparison",
    type: "comparison",
    position: { x: -800, y: 100 },
    data: { companies: [{ cik: 320193, ticker: "AAPL" }], form: "10-K" },
  },
];

test("a snapshot keeps references, never figures", () => {
  const saved = toSnapshot(board);
  const serialised = JSON.stringify(saved);
  assert.ok(!serialised.includes("Line 0"), "statement rows were saved");
  assert.ok(serialised.length < 600, `snapshot is ${serialised.length} bytes`);
});

test("a snapshot keeps where everything sat", () => {
  const [entity] = toSnapshot(board);
  assert.ok(entity && entity.kind === "entity");
  assert.deepEqual([entity.x, entity.y, entity.width, entity.height], [0, 0, 360, 560]);
});

test("a node whose size was never measured saves without one", () => {
  const saved = toSnapshot([board[1]!]);
  assert.equal(saved[0]?.width, undefined);
});

test("a node missing what identifies it is dropped rather than half-saved", () => {
  const broken: SnapshottableNode[] = [
    { id: "x", type: "statement", position: { x: 0, y: 0 }, data: { cik: 1 } },
    { id: "y", type: "entity", position: { x: 0, y: 0 }, data: {} },
    { id: "z", type: "comparison", position: { x: 0, y: 0 }, data: { companies: [] } },
  ];
  assert.deepEqual(toSnapshot(broken), []);
});

test("one filing's panels are one fetch, not five", () => {
  const nodes = toSnapshot([
    board[1]!,
    { ...board[1]!, id: "stmt-2", position: { x: 1204, y: 0 } },
  ]);
  assert.deepEqual(filingsToRestore(nodes), [
    { cik: 320193, accession: "0000320193-25-000079", form: "10-K" },
  ]);
});

test("restoring names the companies to resolve", () => {
  assert.deepEqual(companiesToRestore(toSnapshot(board)), [
    { cik: 320193, ticker: "AAPL", name: "Apple Inc." },
  ]);
});

test("an empty board snapshots to nothing", () => {
  assert.deepEqual(toSnapshot([]), []);
  assert.deepEqual(filingsToRestore([]), []);
});

test("the sidebar being hidden is remembered", () => {
  // A reader who hid it wanted the width for the statements, and did not mean
  // only until the next reload.
  const storage = memoryStorage();
  save({ canvases: [canvas({ id: "a" })], selected: "a", sidebar: false }, storage);
  assert.equal(load(storage).sidebar, false);
});

test("state written before the sidebar could be hidden still shows it", () => {
  const storage = memoryStorage({
    "finagentic.canvases.v1": JSON.stringify({
      canvases: [{ id: "a", name: "A", pinned: false, updatedAt: 1, nodes: [] }],
      selected: "a",
    }),
  });
  assert.equal(load(storage).sidebar, true);
});
