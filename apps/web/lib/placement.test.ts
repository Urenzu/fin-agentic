import assert from "node:assert/strict";
import { test } from "node:test";

import { nextCardOrigin, nextRowOrigin, type PlaceableNode } from "./placement";

const APPLE = 320193;
const NVIDIA = 1045810;
const LAYOUT = { originX: 400, rowPitch: 620 };

function card(cik: number, y: number): PlaceableNode {
  return { id: `entity-${cik}`, type: "entity", position: { x: 0, y } };
}

function statement(cik: number, y: number, name = "operations"): PlaceableNode {
  return {
    id: `stmt-${cik}-${name}-${y}`,
    type: "statement",
    position: { x: 400, y },
    data: { cik },
  };
}

// ---------------------------------------------------------------------------
// rows
// ---------------------------------------------------------------------------

test("the first filing opens level with its company card", () => {
  const board = [card(APPLE, 0)];
  assert.deepEqual(nextRowOrigin(board, APPLE, LAYOUT), { x: 400, y: 0 });
});

test("a second filing opens one row below the first", () => {
  const board = [card(APPLE, 0), statement(APPLE, 0)];
  assert.deepEqual(nextRowOrigin(board, APPLE, LAYOUT), { x: 400, y: 620 });
});

test("closing a filing frees the band it was in", () => {
  // The bug this replaces: a tally that only ever counted up, so opening,
  // closing and opening again put the second filing two rows down with a gap
  // where the first had been.
  const opened = [card(APPLE, 0), statement(APPLE, 0)];
  const closed = opened.filter((n) => n.type !== "statement");
  assert.deepEqual(nextRowOrigin(closed, APPLE, LAYOUT), { x: 400, y: 0 });
});

test("a gap between rows is filled before going further down", () => {
  // Rows 0 and 2 are open, so the next filing belongs in row 1 rather than
  // row 3 -- which is what "pushed down very far" looked like.
  const board = [card(APPLE, 0), statement(APPLE, 0), statement(APPLE, 1240)];
  assert.deepEqual(nextRowOrigin(board, APPLE, LAYOUT), { x: 400, y: 620 });
});

test("deleting every statement puts the next filing back beside the card", () => {
  const board = [card(APPLE, 0)];
  for (let i = 0; i < 5; i += 1) {
    assert.equal(nextRowOrigin(board, APPLE, LAYOUT).y, 0, `attempt ${i}`);
  }
});

test("rows are counted from the card's own position, not from the origin", () => {
  // A second company sits below the first, and its filings belong beside it.
  const board = [card(APPLE, 0), card(NVIDIA, 1500), statement(APPLE, 0)];
  assert.deepEqual(nextRowOrigin(board, NVIDIA, LAYOUT), { x: 400, y: 1500 });
});

test("statements follow a card the reader has dragged", () => {
  // The old code stored where the card was created, so moving it left every
  // later filing behind at the original spot.
  const board = [card(APPLE, 900)];
  assert.deepEqual(nextRowOrigin(board, APPLE, LAYOUT), { x: 400, y: 900 });
});

test("another company's rows do not crowd this one", () => {
  const board = [card(APPLE, 0), statement(NVIDIA, 0), statement(NVIDIA, 620)];
  assert.deepEqual(nextRowOrigin(board, APPLE, LAYOUT), { x: 400, y: 0 });
});

test("a panel nudged a few pixels still counts as occupying its band", () => {
  const board = [card(APPLE, 0), statement(APPLE, 7)];
  assert.equal(nextRowOrigin(board, APPLE, LAYOUT).y, 620);
});

test("a panel dragged above the card does not claim a band", () => {
  // Negative bands are not rows, and treating one as row 0 would push the next
  // filing down for no reason.
  const board = [card(APPLE, 1000), statement(APPLE, -500)];
  assert.deepEqual(nextRowOrigin(board, APPLE, LAYOUT), { x: 400, y: 1000 });
});

test("a company with no card on the board still gets a usable row", () => {
  assert.deepEqual(nextRowOrigin([], APPLE, LAYOUT), { x: 400, y: 0 });
});

// ---------------------------------------------------------------------------
// cards
// ---------------------------------------------------------------------------

test("the first company starts at the origin", () => {
  assert.deepEqual(nextCardOrigin([], 60, 560), { x: 0, y: 0 });
});

test("a second company clears everything already on the board", () => {
  const board = [{ position: { x: 0, y: 0 }, height: 560 }];
  assert.deepEqual(nextCardOrigin(board, 60, 560), { x: 0, y: 620 });
});

test("a board that has had companies removed closes up", () => {
  // Measured from what is there, so the next arrival is not stranded past the
  // gap a deleted company left.
  const board = [{ position: { x: 0, y: 0 }, height: 560 }];
  const after = nextCardOrigin(board, 60, 560);
  assert.equal(after.y, 620);
  assert.deepEqual(nextCardOrigin([], 60, 560), { x: 0, y: 0 });
});

test("a node whose height is not known yet still clears", () => {
  const board = [{ position: { x: 0, y: 0 } }];
  assert.equal(nextCardOrigin(board, 60, 560).y, 620);
});
