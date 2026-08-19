/**
 * How big each node is, and how small a reader may shrink it.
 *
 * Sizes are declared rather than measured. React Flow keeps a node
 * `visibility: hidden` until its ResizeObserver has reported dimensions, and
 * under StrictMode's double mount that observer can be torn down before it
 * ever fires -- nodes stay invisible and viewport framing has nothing of known
 * size to work with. Computing the size up front removes the dependency on
 * measurement entirely, which is also what makes resizing predictable: the
 * node's height is a number we own, not something the DOM reports back.
 */

import type { AsFiledStatement, Entity } from "./types";

export const LABEL_COLUMN = 300;
export const VALUE_COLUMN = 108;
export const INDENT_STEP = 13;

export const HEADER_HEIGHT = 66;
export const COLUMN_HEADER_HEIGHT = 34;
export const DATA_ROW_HEIGHT = 24;
export const SECTION_ROW_HEIGHT = 31;

/** The height a statement opens at. Beyond this it scrolls until resized. */
export const DEFAULT_STATEMENT_HEIGHT = 560;

/**
 * Below this a statement stops being one. The label column has a floor of its
 * own, so a narrower node only clips text; and fewer than about four rows of
 * body leaves a panel that is mostly chrome.
 */
export const MIN_STATEMENT_WIDTH = LABEL_COLUMN + VALUE_COLUMN;
export const MIN_STATEMENT_HEIGHT = HEADER_HEIGHT + COLUMN_HEADER_HEIGHT + DATA_ROW_HEIGHT * 4;

export function statementNodeWidth(statement: AsFiledStatement): number {
  return LABEL_COLUMN + Math.max(statement.columns.length, 1) * VALUE_COLUMN + 32;
}

/**
 * The height at which every row is visible and nothing scrolls.
 *
 * An estimate, because a long label wraps and the real row is taller than the
 * nominal one. It is deliberately the *lower* bound of the truth: overshooting
 * would leave a band of empty panel under the last row, which looks like a
 * bug, whereas undershooting leaves a few pixels of scroll, which does not.
 */
export function statementContentHeight(statement: AsFiledStatement): number {
  const body = statement.rows.reduce(
    (total, row) => total + (row.is_abstract ? SECTION_ROW_HEIGHT : DATA_ROW_HEIGHT),
    0,
  );
  return HEADER_HEIGHT + COLUMN_HEADER_HEIGHT + body + 12;
}

/** The height the node is created at: its content, capped. */
export function statementNodeHeight(statement: AsFiledStatement): number {
  return Math.min(statementContentHeight(statement), DEFAULT_STATEMENT_HEIGHT);
}

/** Whether opening this statement at its default height hides anything. */
export function overflowsDefault(statement: AsFiledStatement): boolean {
  return statementContentHeight(statement) > DEFAULT_STATEMENT_HEIGHT;
}

export const ENTITY_NODE_WIDTH = 360;

/** Enough for the header plus one row of the stat grid. */
export const MIN_ENTITY_WIDTH = 200;
export const MIN_ENTITY_HEIGHT = 120;

const CHARS_PER_LINE = 52;
const LINE_HEIGHT = 16;

/** The filing picker: form toggle, and a scrollable list under it. */
const FILING_PICKER_HEIGHT = 300;

/**
 * The entity card's height for the state it is in.
 *
 * Recomputed whenever the entity changes, because the card grows as ingestion
 * finishes: a "building the ledger" sentence becomes a stat grid, and an
 * unsupported filer adds an advisory.
 */
export function entityNodeHeight(entity: Entity): number {
  const chrome = 66 + 24;
  const body = entity.coverage
    ? 92 + (entity.coverage.earliest && entity.coverage.latest ? 46 : 0)
    : 64;
  const advisories = entity.advisories.reduce(
    (total, advisory) => total + 26 + Math.ceil(advisory.length / CHARS_PER_LINE) * LINE_HEIGHT,
    0,
  );
  return chrome + body + FILING_PICKER_HEIGHT + advisories;
}

/** Keep a resized dimension inside what the node can usefully be. */
export function clampSize(value: number, min: number, max = Number.MAX_SAFE_INTEGER): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(Math.max(value, min), Math.max(min, max));
}
