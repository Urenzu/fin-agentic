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

import { needsGroupRow } from "./columns";
import type { AsFiledStatement } from "./types";

export const LABEL_COLUMN = 300;
export const VALUE_COLUMN = 108;
export const INDENT_STEP = 13;

export const HEADER_HEIGHT = 66;
export const COLUMN_HEADER_HEIGHT = 34;
/** The "3 Months Ended" row a quarterly statement carries above its dates. */
export const GROUP_HEADER_HEIGHT = 26;
export const DATA_ROW_HEIGHT = 24;
export const SECTION_ROW_HEIGHT = 31;

/**
 * The height every statement opens at. Beyond this it scrolls until resized.
 *
 * Uniform for the same reason `STATEMENT_WIDTH` is: one cell of the board's
 * grid. Opening each panel at its own content height, capped here, meant a
 * short statement -- comprehensive income runs about 500px -- came up
 * noticeably smaller than the operations statement beside it, and a row that
 * should read as a set looked like a mistake instead.
 *
 * The cost is a band of empty panel under a short statement's last row. That
 * is the quieter of the two, and a double click on the header still fits any
 * panel to its own content.
 */
export const DEFAULT_STATEMENT_HEIGHT = 560;

/**
 * Below this a statement stops being one. The label column has a floor of its
 * own, so a narrower node only clips text; and fewer than about four rows of
 * body leaves a panel that is mostly chrome.
 */
export const MIN_STATEMENT_WIDTH = LABEL_COLUMN + VALUE_COLUMN;
export const MIN_STATEMENT_HEIGHT = HEADER_HEIGHT + COLUMN_HEADER_HEIGHT + DATA_ROW_HEIGHT * 4;

/**
 * The width every statement opens at.
 *
 * Fixed rather than fitted to the column count, so that the nth statement of
 * one filing lines up with the nth statement of every other. Sizing each panel
 * to its own content left the board ragged: a 10-Q's four-column operations
 * statement is 764 wide and a 10-K's three-column one is 656, so the two rows
 * disagreed about where the second column began and nothing lined up.
 *
 * Sized for four periods, which is the widest ordinary case -- a 10-Q printing
 * a quarter beside its year to date. A statement with more columns than that
 * scrolls sideways inside its panel, and can be dragged wider.
 */
export const STATEMENT_WIDTH = LABEL_COLUMN + 4 * VALUE_COLUMN + 32;

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
  const groupRow = needsGroupRow(statement.columns) ? GROUP_HEADER_HEIGHT : 0;
  return HEADER_HEIGHT + COLUMN_HEADER_HEIGHT + groupRow + body + 12;
}

/** Whether opening this statement at its default height hides anything. */
export function overflowsDefault(statement: AsFiledStatement): boolean {
  return statementContentHeight(statement) > DEFAULT_STATEMENT_HEIGHT;
}

export const ENTITY_NODE_WIDTH = 360;

/** Enough for the header plus one row of the stat grid. */
export const MIN_ENTITY_WIDTH = 200;
export const MIN_ENTITY_HEIGHT = 120;

/**
 * The entity card fills the same cell as a statement.
 *
 * It used to size itself to its contents and so came up about 30px shorter
 * than the statements beside it -- close enough to read as a misalignment
 * rather than as a decision. Deriving it from the statement height means the
 * two can never drift apart.
 *
 * The card's body scrolls, so a filer carrying several advisories still shows
 * all of them; the card grew to fit them before, and can still be dragged
 * taller.
 */
export const ENTITY_NODE_HEIGHT = DEFAULT_STATEMENT_HEIGHT;

/** Keep a resized dimension inside what the node can usefully be. */
export function clampSize(value: number, min: number, max = Number.MAX_SAFE_INTEGER): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(Math.max(value, min), Math.max(min, max));
}

/**
 * A comparison panel's width, which is the one node that grows with its
 * contents: a column per company being compared.
 *
 * Deliberately not the fixed cell the statements use. Those are placed on a
 * grid so filings line up between rows; a comparison sits on its own and has
 * nothing to line up with, and forcing three companies into a five-column
 * width would leave a band of empty panel doing nothing.
 */
export function comparisonNodeWidth(companies: number): number {
  return LABEL_COLUMN + Math.max(companies, 1) * VALUE_COLUMN + 32;
}

/**
 * The height a comparison opens at.
 *
 * Every metric gets a row whether or not a company reports it, so the height
 * is known exactly rather than estimated: the table is always twelve rows.
 * Its column header runs to two lines -- ticker above period -- so it needs
 * more than a statement's single-line one.
 */
//: The parts below are measured from the rendered panel rather than estimated.
//: The statement constants do not fit it: a comparison's header runs to three
//: lines where a statement's runs to two, and its rows are taller because each
//: column header carries a ticker above a period. Guessing left the twelfth
//: metric permanently below the fold, which is the one row a reader would
//: never think to scroll for.
export const COMPARISON_HEADER_HEIGHT = 82;
export const COMPARISON_COLUMN_HEADER_HEIGHT = 46;
export const COMPARISON_ROW_HEIGHT = 29;
export const COMPARISON_METRIC_COUNT = 12;
export const COMPARISON_NODE_HEIGHT =
  COMPARISON_HEADER_HEIGHT +
  COMPARISON_COLUMN_HEADER_HEIGHT +
  COMPARISON_ROW_HEIGHT * COMPARISON_METRIC_COUNT +
  8;
