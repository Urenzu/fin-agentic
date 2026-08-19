import assert from "node:assert/strict";
import test from "node:test";

import { boundsOf, frame, HUD_INSET, type Box } from "./viewport";

const box = (x: number, y: number, width = 100, height = 100): Box => ({
  position: { x, y },
  width,
  height,
});

test("bounds span every box", () => {
  assert.deepEqual(boundsOf([box(0, 0), box(300, 200)]), {
    x: 0,
    y: 0,
    width: 400,
    height: 300,
  });
});

test("an empty board has no bounds and no viewport", () => {
  assert.equal(boundsOf([]), null);
  assert.equal(frame([], 1920, 1000), null);
});

test("content wider than the pane is zoomed out to fit", () => {
  // A board of statements runs several thousand pixels wide; the whole point is
  // that it lands on screen rather than off the right edge.
  const view = frame([box(0, 0, 3800, 560)], 1920, 1000);
  assert.ok(view);
  assert.ok(view.zoom < 1, `expected zoom < 1, got ${view.zoom}`);
  assert.ok(3800 * view.zoom <= 1920 - 96 + 0.001);
});

test("small content is never magnified past 1", () => {
  const view = frame([box(0, 0, 200, 100)], 1920, 1000);
  assert.ok(view);
  assert.equal(view.zoom, 1);
});

test("the top inset keeps the search bar clear of the content", () => {
  const view = frame([box(0, 0, 3800, 560)], 1920, 1000);
  assert.ok(view);
  // The topmost node maps to y = view.y at scale, which must sit below the HUD.
  assert.ok(view.y >= HUD_INSET, `top edge ${view.y} intrudes on the HUD`);
});

test("content is centred horizontally", () => {
  const view = frame([box(0, 0, 200, 100)], 1000, 600);
  assert.ok(view);
  assert.equal(view.x, 48 + (1000 - 96 - 200) / 2);
});

test("a negative origin is handled", () => {
  // Nodes are draggable, so the board can extend left of where it started.
  const view = frame([box(-500, -200, 100, 100)], 1000, 600);
  assert.ok(view);
  assert.equal(view.zoom, 1);
  assert.ok(view.x > 0);
});

test("a zero-area box does not produce a NaN zoom", () => {
  const view = frame([box(0, 0, 0, 0)], 1000, 600);
  assert.ok(view);
  assert.equal(view.zoom, 1);
  assert.ok(Number.isFinite(view.x) && Number.isFinite(view.y));
});

test("boxes without declared dimensions are treated as points", () => {
  assert.deepEqual(boundsOf([{ position: { x: 10, y: 20 } }]), {
    x: 10,
    y: 20,
    width: 0,
    height: 0,
  });
});
