import assert from "node:assert/strict";
import { test } from "node:test";

import { removeFromBoard, type RemovableNode } from "./removal";

const APPLE = 320193;
const NVIDIA = 1045810;
//: Accessions belong to one filer -- EDGAR issues them per submission -- so
//: two companies never share one. Fixtures that pretended otherwise hid the
//: behaviour these tests exist to pin.
const AAPL_FY2025 = "0000320193-25-000079";
const AAPL_FY2024 = "0000320193-24-000123";
const NVDA_FY2025 = "0001045810-26-000021";

function entity(cik: number): RemovableNode {
  return { id: `entity-${cik}`, type: "entity", data: { entity: { registrant: { cik } } } };
}

function statement(cik: number, accession: string, name: string): RemovableNode {
  return {
    id: `stmt-${cik}-${accession}-${name}`,
    type: "statement",
    data: { cik, statement: { accession } },
  };
}

function comparison(...ciks: number[]): RemovableNode {
  return {
    id: "comparison",
    type: "comparison",
    data: { companies: ciks.map((cik) => ({ cik, ticker: `T${cik}` })) },
  };
}

const BOARD: RemovableNode[] = [
  entity(APPLE),
  entity(NVIDIA),
  statement(APPLE, AAPL_FY2025, "operations"),
  statement(APPLE, AAPL_FY2025, "balance"),
  statement(NVIDIA, NVDA_FY2025, "operations"),
  comparison(APPLE, NVIDIA),
];

const ids = (nodes: RemovableNode[]) => nodes.map((n) => n.id);

// ---------------------------------------------------------------------------
// statements
// ---------------------------------------------------------------------------

test("removing one statement leaves the rest of its filing alone", () => {
  const { nodes, closedAccessions } = removeFromBoard(
    BOARD,
    `stmt-${APPLE}-${AAPL_FY2025}-operations`,
  );
  assert.ok(ids(nodes).includes(`stmt-${APPLE}-${AAPL_FY2025}-balance`));
  // The filing still has a panel on the board, so it is still open.
  assert.deepEqual(closedAccessions, []);
});

test("removing the last statement of a filing marks it closed", () => {
  // Otherwise the picker shows a row as open that has nothing on the board,
  // and clicking it does nothing because the board thinks it already did.
  const board = BOARD.filter((n) => n.id !== `stmt-${APPLE}-${AAPL_FY2025}-balance`);
  const { closedAccessions } = removeFromBoard(board, `stmt-${APPLE}-${AAPL_FY2025}-operations`);
  assert.deepEqual(closedAccessions, [AAPL_FY2025]);
});

test("one company's filing closing leaves another company's open", () => {
  const { closedAccessions } = removeFromBoard(BOARD, `stmt-${NVIDIA}-${NVDA_FY2025}-operations`);
  assert.deepEqual(closedAccessions, [NVDA_FY2025]);
});

// ---------------------------------------------------------------------------
// companies
// ---------------------------------------------------------------------------

test("removing a company takes its statements with it", () => {
  // The alternative is panels whose card is gone: unreachable from the picker
  // that opened them, and connected to nothing.
  const { nodes } = removeFromBoard(BOARD, `entity-${APPLE}`);
  assert.deepEqual(ids(nodes), [`entity-${NVIDIA}`, `stmt-${NVIDIA}-${NVDA_FY2025}-operations`]);
});

test("removing a company closes every filing it had open", () => {
  const board = [...BOARD, statement(APPLE, AAPL_FY2024, "operations")];
  const { closedAccessions } = removeFromBoard(board, `entity-${APPLE}`);
  assert.deepEqual(closedAccessions.sort(), [AAPL_FY2024, AAPL_FY2025].sort());
});

test("removing a company leaves every other company's filings open", () => {
  const { closedAccessions } = removeFromBoard(BOARD, `entity-${NVIDIA}`);
  // NVIDIA's own filing closes; Apple's two panels are untouched.
  assert.deepEqual(closedAccessions, [NVDA_FY2025]);
});

// ---------------------------------------------------------------------------
// comparisons
// ---------------------------------------------------------------------------

test("a comparison of two loses both columns when one company goes", () => {
  // A comparison of one company is a list.
  const { nodes } = removeFromBoard(BOARD, `entity-${APPLE}`);
  assert.ok(!ids(nodes).includes("comparison"));
});

test("a comparison of three drops to two rather than disappearing", () => {
  const board = [entity(APPLE), entity(NVIDIA), entity(1), comparison(APPLE, NVIDIA, 1)];
  const { nodes } = removeFromBoard(board, "entity-1");

  const survivor = nodes.find((n) => n.id === "comparison");
  assert.ok(survivor && survivor.type === "comparison");
  assert.deepEqual(
    survivor.data.companies.map((c) => c.cik),
    [APPLE, NVIDIA],
  );
});

test("a company's ticker leaves with its cik", () => {
  // The two travel together, so a column cannot end up labelled with one
  // company's ticker and filled with another's figures.
  const board = [entity(APPLE), entity(NVIDIA), entity(1), comparison(APPLE, NVIDIA, 1)];
  const { nodes } = removeFromBoard(board, `entity-${NVIDIA}`);

  const survivor = nodes.find((n) => n.id === "comparison");
  assert.ok(survivor && survivor.type === "comparison");
  assert.deepEqual(
    survivor.data.companies.map((c) => c.ticker),
    [`T${APPLE}`, "T1"],
  );
});

test("removing the comparison itself touches nothing else", () => {
  const { nodes, closedAccessions } = removeFromBoard(BOARD, "comparison");
  assert.equal(nodes.length, BOARD.length - 1);
  assert.deepEqual(closedAccessions, []);
});

// ---------------------------------------------------------------------------
// edges
// ---------------------------------------------------------------------------

test("removing something that is not there changes nothing", () => {
  const { nodes, closedAccessions } = removeFromBoard(BOARD, "entity-999");
  assert.equal(nodes, BOARD);
  assert.deepEqual(closedAccessions, []);
});

test("the board can be emptied one company at a time", () => {
  let board = BOARD;
  for (const cik of [APPLE, NVIDIA]) {
    board = removeFromBoard(board, `entity-${cik}`).nodes;
  }
  assert.deepEqual(board, []);
});
