import assert from "node:assert/strict";
import { test } from "node:test";

import {
  createCanvas,
  matches,
  ordered,
  remove,
  rename,
  tickersOf,
  togglePin,
  uniqueName,
  type Canvas,
  type CanvasNode,
} from "./canvas";

function canvas(partial: Partial<Canvas> & { id: string }): Canvas {
  return {
    name: partial.id,
    pinned: false,
    updatedAt: 0,
    nodes: [],
    ...partial,
  };
}

function entity(cik: number, ticker: string): CanvasNode {
  return { kind: "entity", cik, ticker, name: `${ticker} Inc.`, x: 0, y: 0 };
}

const names = (list: readonly Canvas[]) => list.map((c) => c.id);

// ---------------------------------------------------------------------------
// creating
// ---------------------------------------------------------------------------

test("a new canvas gets a name that is not already taken", () => {
  const first = createCanvas([]);
  const second = createCanvas([first]);
  const third = createCanvas([first, second]);
  assert.notEqual(first.name, second.name);
  assert.notEqual(second.name, third.name);
});

test("names are only made unique when they collide", () => {
  assert.equal(uniqueName([]), "Untitled canvas");
  assert.equal(uniqueName([canvas({ id: "a", name: "Untitled canvas" })]), "Untitled canvas 2");
});

test("a fresh id is not shared even within the same millisecond", () => {
  const now = 1_700_000_000_000;
  const ids = new Set(Array.from({ length: 50 }, () => createCanvas([], now).id));
  assert.equal(ids.size, 50);
});

// ---------------------------------------------------------------------------
// ordering
// ---------------------------------------------------------------------------

test("the most recently touched canvas comes first", () => {
  const list = [canvas({ id: "old", updatedAt: 1 }), canvas({ id: "new", updatedAt: 9 })];
  assert.deepEqual(names(ordered(list)), ["new", "old"]);
});

test("pinning outranks recency entirely", () => {
  // A pinned board untouched for a month still belongs above one opened this
  // morning, or pinning would not mean anything.
  const list = [
    canvas({ id: "recent", updatedAt: 9 }),
    canvas({ id: "pinned-and-old", updatedAt: 1, pinned: true }),
  ];
  assert.deepEqual(names(ordered(list)), ["pinned-and-old", "recent"]);
});

test("pinned canvases are ordered among themselves by recency", () => {
  const list = [
    canvas({ id: "pinned-old", updatedAt: 1, pinned: true }),
    canvas({ id: "pinned-new", updatedAt: 9, pinned: true }),
  ];
  assert.deepEqual(names(ordered(list)), ["pinned-new", "pinned-old"]);
});

test("two canvases saved in the same millisecond keep a stable order", () => {
  // Otherwise they swap places between renders for no reason the reader can see.
  const list = [canvas({ id: "b", updatedAt: 5 }), canvas({ id: "a", updatedAt: 5 })];
  assert.deepEqual(names(ordered(list)), names(ordered(list)));
  assert.deepEqual(names(ordered(list)), ["a", "b"]);
});

// ---------------------------------------------------------------------------
// searching
// ---------------------------------------------------------------------------

test("an empty query matches everything", () => {
  assert.ok(matches(canvas({ id: "a", name: "Anything" }), "   "));
});

test("a canvas is found by its name, whatever the case", () => {
  assert.ok(matches(canvas({ id: "a", name: "Semis teardown" }), "SEMIS"));
});

test("a canvas is found by a company on it", () => {
  // The reader remembers "the one with Apple" more often than what they called
  // it, and matching only names would miss exactly the canvases worth finding.
  const board = canvas({ id: "a", name: "Untitled canvas", nodes: [entity(320193, "AAPL")] });
  assert.ok(matches(board, "aapl"));
  assert.ok(!matches(board, "nvda"));
});

test("a company in a comparison counts as being on the canvas", () => {
  const board = canvas({
    id: "a",
    name: "Untitled canvas",
    nodes: [
      {
        kind: "comparison",
        companies: [{ cik: 1, ticker: "NVDA" }],
        form: "10-K",
        x: 0,
        y: 0,
      },
    ],
  });
  assert.deepEqual(tickersOf(board), ["NVDA"]);
  assert.ok(matches(board, "nvda"));
});

test("a filer with no ticker does not contribute an empty match", () => {
  const board = canvas({ id: "a", nodes: [entity(34088, "")] });
  assert.deepEqual(tickersOf(board), []);
});

test("searching narrows the list without reordering what is left", () => {
  const list = [
    canvas({ id: "a", name: "Apple", updatedAt: 9 }),
    canvas({ id: "b", name: "Banks", updatedAt: 5 }),
    canvas({ id: "c", name: "Apples to apples", updatedAt: 1 }),
  ];
  assert.deepEqual(names(ordered(list, "appl")), ["a", "c"]);
});

// ---------------------------------------------------------------------------
// editing
// ---------------------------------------------------------------------------

test("renaming touches the canvas so it rises in the list", () => {
  const list = [canvas({ id: "a", updatedAt: 1 })];
  const [renamed] = rename(list, "a", "Semis", 500);
  assert.equal(renamed?.name, "Semis");
  assert.equal(renamed?.updatedAt, 500);
});

test("a name of only whitespace is refused", () => {
  // An empty row in the sidebar has nothing to click on and nothing to tell it
  // from its neighbours.
  const list = [canvas({ id: "a", name: "Semis" })];
  assert.equal(rename(list, "a", "   ")[0]?.name, "Semis");
});

test("a name is stored trimmed", () => {
  assert.equal(rename([canvas({ id: "a" })], "a", "  Semis  ")[0]?.name, "Semis");
});

test("pinning does not count as touching the canvas", () => {
  // Pinning is not editing: it must not reorder the recency it sits above.
  const list = [canvas({ id: "a", updatedAt: 1 })];
  const [pinned] = togglePin(list, "a");
  assert.equal(pinned?.pinned, true);
  assert.equal(pinned?.updatedAt, 1);
});

test("pinning is a toggle", () => {
  const once = togglePin([canvas({ id: "a" })], "a");
  assert.equal(togglePin(once, "a")[0]?.pinned, false);
});

// ---------------------------------------------------------------------------
// removing
// ---------------------------------------------------------------------------

test("removing a canvas selects the next one in the list", () => {
  const list = [canvas({ id: "a", updatedAt: 9 }), canvas({ id: "b", updatedAt: 5 })];
  const { canvases, selected } = remove(list, "a");
  assert.deepEqual(names(canvases), ["b"]);
  assert.equal(selected, "b");
});

test("removing a canvas prefers a pinned survivor", () => {
  const list = [
    canvas({ id: "a", updatedAt: 9 }),
    canvas({ id: "b", updatedAt: 1 }),
    canvas({ id: "c", updatedAt: 5, pinned: true }),
  ];
  assert.equal(remove(list, "a").selected, "c");
});

test("removing the last canvas leaves a fresh one rather than nothing", () => {
  // A board with no canvas has nowhere to put anything.
  const { canvases, selected } = remove([canvas({ id: "only" })], "only");
  assert.equal(canvases.length, 1);
  assert.equal(canvases[0]?.id, selected);
  assert.deepEqual(canvases[0]?.nodes, []);
});
