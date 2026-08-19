"use client";

import { useEffect, useRef, useState } from "react";
import {
  Handle,
  NodeResizer,
  Position,
  useReactFlow,
  useStore,
  type NodeProps,
  type Node,
} from "@xyflow/react";

import { NodeFrame } from "../NodeFrame";
import { abbreviate, formatValue, scaleExponent } from "@/lib/decimal";
import { fitScale, headlineCapacity, headlineRows, tierFor } from "@/lib/lod";
import {
  INDENT_STEP,
  LABEL_COLUMN,
  MIN_STATEMENT_HEIGHT,
  MIN_STATEMENT_WIDTH,
  statementNodeHeight,
  VALUE_COLUMN,
} from "@/lib/nodeSize";
import type { AsFiledStatement } from "@/lib/types";

export type StatementNodeData = {
  company: string;
  ticker: string;
  statement: AsFiledStatement;
};

export type StatementNodeType = Node<StatementNodeData, "statement">;

/** "$ in Millions", derived from the multiplier the parser already applied. */
function unitsCaption(monetaryExp: number): string {
  switch (monetaryExp) {
    case 9:
      return "$ in billions";
    case 6:
      return "$ in millions";
    case 3:
      return "$ in thousands";
    default:
      return "$ in units";
  }
}

/**
 * Per-share amounts are printed at full precision by the filer and the API
 * leaves them unscaled, so restating them at the statement's monetary scale
 * would divide EPS by a million while still yielding a plausible-looking
 * number. The element name is what distinguishes them.
 */
function isPerShare(element: string | null): boolean {
  return element !== null && /PerShare|PerBasicShare|PerDilutedShare/.test(element);
}

function isShareCount(element: string | null): boolean {
  return element !== null && /[Ss]hares/.test(element) && !isPerShare(element);
}

export function StatementNode({ id, data, selected, width, height }: NodeProps<StatementNodeType>) {
  const { statement, company, ticker } = data;
  const { setNodes } = useReactFlow();
  const scroller = useRef<HTMLDivElement>(null);

  // The node's live height, which a resize changes. The level-of-detail
  // arithmetic has to read this rather than the default, or a statement
  // dragged taller would still budget its summary for the old size.
  const nodeHeight = height ?? statementNodeHeight(statement);
  const defaultHeight = statementNodeHeight(statement);

  /**
   * How much of the statement is out of view, measured rather than estimated.
   *
   * Node sizes are declared everywhere else precisely so nothing depends on
   * the DOM having been measured yet. This is the one place that cannot work
   * that way: the row estimate assumes one line per label, and a balance sheet
   * whose labels wrap to two runs hundreds of pixels taller than the arithmetic
   * predicts. Expanding to the estimate left the reader still scrolling, which
   * is the entire thing the control exists to stop. Reading it back from the
   * element is exact, and by the time anyone can click, the element is there.
   */
  const [hidden, setHidden] = useState(0);
  useEffect(() => {
    const element = scroller.current;
    setHidden(element ? element.scrollHeight - element.clientHeight : 0);
  }, [nodeHeight, width, statement]);

  const fitted = hidden <= 1;

  // Both selectors collapse a continuous zoom to a value that changes a
  // handful of times, so this node re-renders on a step boundary rather than
  // on every frame of a zoom gesture.
  const tier = useStore((state) => tierFor(state.transform[2]));
  const scale = useStore((state) => fitScale(state.transform[2], nodeHeight, 0.4));
  const monetaryExp = scaleExponent(statement.monetary_scale);
  const shareExp = scaleExponent(statement.share_scale);

  const filed = new Date(statement.filed).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  const summarised = tier !== "detail";
  const identityOnly = tier === "identity";
  const newest = statement.columns[0];

  /**
   * Grow the panel until nothing is hidden, or put it back to the default.
   *
   * Re-measures on the click rather than trusting the value in state, so the
   * result is right even if the reader has just dragged the node narrower and
   * pushed more labels onto a second line.
   */
  const toggleFit = () => {
    const element = scroller.current;
    const out = element ? element.scrollHeight - element.clientHeight : 0;
    const next = out > 1 ? nodeHeight + out : defaultHeight;
    setNodes((nodes) => nodes.map((node) => (node.id === id ? { ...node, height: next } : node)));
  };

  return (
    <>
      {/* Only while the node is selected -- handles on every panel at once
          would read as twelve nodes all mid-drag. Not offered in the far
          tiers: there is nothing to scroll to when the table is not drawn,
          and the handles would be the largest thing on the panel. */}
      <NodeResizer
        isVisible={selected === true && tier === "detail"}
        minWidth={MIN_STATEMENT_WIDTH}
        minHeight={MIN_STATEMENT_HEIGHT}
        lineClassName="!border-transparent"
        handleClassName="!h-2 !w-2 !rounded-sm !border !border-hairline-strong !bg-raised"
      />
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2 !w-2 !border-0 !bg-hairline-strong"
      />
      <NodeFrame
        // Zoomed out the ticker is what identifies the row; the full registrant
        // name is unreadable long before the panel stops being recognisable.
        eyebrow={summarised ? ticker : company}
        title={statement.short_name}
        scale={summarised ? scale : 1}
        meta={
          <span className="tnum">
            {statement.form} &middot; filed {filed} &middot; {unitsCaption(monetaryExp)}
          </span>
        }
        action={
          <div className="flex shrink-0 items-center gap-1.5">
            {(hidden > 1 || nodeHeight > defaultHeight) && (
              <button
                type="button"
                onClick={toggleFit}
                title={
                  fitted
                    ? "Collapse to the default height"
                    : "Grow the panel until every row is visible"
                }
                aria-label={fitted ? "Collapse statement" : "Expand statement to fit"}
                className="nodrag rounded border border-hairline-strong px-1.5 py-1 text-ink-muted transition hover:border-ink-faint hover:text-ink"
              >
                <svg viewBox="0 0 12 12" className="h-3 w-3 fill-none stroke-current stroke-[1.4]">
                  {fitted ? (
                    <>
                      <path d="M4.5 1.5v3h-3M7.5 10.5v-3h3" strokeLinecap="round" />
                    </>
                  ) : (
                    <>
                      <path d="M1.5 4.5v-3h3M10.5 7.5v3h-3" strokeLinecap="round" />
                    </>
                  )}
                </svg>
              </button>
            )}
            <a
              href={statement.source_url}
              target="_blank"
              rel="noreferrer"
              title="The SEC exhibit these numbers came from"
              className="nodrag shrink-0 rounded border border-hairline-strong px-2 py-1 text-[10px] font-medium text-ink-muted transition hover:border-ink-faint hover:text-ink"
            >
              SEC ↗
            </a>
          </div>
        }
      >
        {summarised ? (
          // Far view: the table is texture at this distance, so it is replaced
          // by the handful of lines that carry the most meaning per pixel, set
          // large enough to read without zooming back in.
          <div
            key={tier}
            className="tier-fade flex flex-1 flex-col justify-center overflow-hidden"
            style={{ padding: `0 ${16 * scale}px`, gap: `${10 * scale}px` }}
          >
            {!identityOnly &&
              newest !== undefined &&
              headlineRows(statement, Math.min(3, headlineCapacity(nodeHeight, scale))).map(
                (row, index) => {
                  const raw = row.values[newest];
                  if (raw === undefined) return null;
                  const perShare = isPerShare(row.element);
                  return (
                    <div key={index}>
                      <div
                        className="truncate uppercase tracking-[0.1em] text-ink-faint"
                        style={{ fontSize: `${9 * scale}px` }}
                      >
                        {row.label}
                      </div>
                      <div
                        className={`tabular font-semibold leading-tight ${
                          raw.startsWith("-") ? "text-negative" : "text-ink"
                        }`}
                        style={{ fontSize: `${20 * scale}px` }}
                      >
                        {/* Abbreviated deliberately: at this distance the reader
                          wants the magnitude, and "391.0B" survives being
                          small in a way that "391,035" does not. Per-share
                          amounts are already small numbers and abbreviating
                          them would destroy the only figure that matters. */}
                        {perShare ? formatValue(raw, 0, { dp: 2, parens: true }) : abbreviate(raw)}
                      </div>
                    </div>
                  );
                },
              )}
          </div>
        ) : (
          <div
            key={tier}
            ref={scroller}
            className="tier-fade nowheel nodrag min-h-0 flex-1 overflow-auto"
          >
            {/* `width` on a column is a hint, not a floor: a statement of
                shareholders' equity carries headers like "ACCUMULATED OTHER
                COMPREHENSIVE INCOME (LOSS)", and letting the table fit the
                panel squeezed the label column until every line wrapped to
                five or six rows. Sizing to content and scrolling instead keeps
                labels on one line, which is what makes the statement scannable. */}
            <table
              className="border-collapse text-[12px]"
              style={{ width: "max-content", minWidth: "100%" }}
            >
              <thead className="sticky top-0 z-10 bg-surface">
                <tr>
                  <th
                    className="border-b border-hairline px-4 pb-2 pt-3 text-left"
                    style={{ width: LABEL_COLUMN, minWidth: LABEL_COLUMN }}
                  />
                  {statement.columns.map((column, columnIndex) => (
                    <th
                      key={column}
                      // The newest period is the one being read; the
                      // comparatives are context. Giving them all equal weight
                      // is what made the table a wall of identical figures.
                      className={`eyebrow whitespace-nowrap border-b border-hairline px-3 pb-2 pt-3 text-right text-[9.5px] ${
                        columnIndex === 0 ? "text-ink-muted" : "text-ink-faint"
                      }`}
                      style={{ width: VALUE_COLUMN, minWidth: VALUE_COLUMN }}
                    >
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {statement.rows.map((row, index) => {
                  const scaleExp = isPerShare(row.element)
                    ? 0
                    : isShareCount(row.element)
                      ? shareExp
                      : monetaryExp;

                  if (row.is_abstract) {
                    return (
                      <tr key={index}>
                        <td
                          colSpan={statement.columns.length + 1}
                          className="eyebrow px-4 pb-1.5 pt-5 text-[9.5px] text-ink-faint"
                          style={{ paddingLeft: 16 + row.indent * INDENT_STEP }}
                        >
                          {row.label}
                        </td>
                      </tr>
                    );
                  }

                  return (
                    <tr
                      key={index}
                      className={`transition-colors hover:bg-white/[0.035] ${
                        row.is_total
                          ? "border-t border-hairline-strong font-medium text-ink"
                          : "text-ink-muted"
                      }`}
                    >
                      <td
                        className="py-[5px] pr-4 leading-snug"
                        style={{ paddingLeft: 16 + row.indent * INDENT_STEP }}
                        title={row.tag ?? undefined}
                      >
                        {row.label}
                      </td>
                      {statement.columns.map((column, columnIndex) => {
                        const value = row.values[column];
                        const negative = value !== undefined && value.startsWith("-");
                        return (
                          <td
                            key={column}
                            className={`tabular whitespace-nowrap px-3 py-[5px] text-right ${
                              columnIndex === 0 || row.is_total ? "" : "text-ink-faint"
                            }`}
                          >
                            {value === undefined ? (
                              // Blank on the face of the statement means the
                              // line did not apply to that period. Rendering a
                              // zero would assert something the filer did not.
                              <span className="text-ink-faint/60">—</span>
                            ) : (
                              // Monetary and share figures are left unrounded:
                              // dividing by the scale the parser applied
                              // recovers exactly the digits the filing printed.
                              // Per-share amounts are pinned to two places so a
                              // $7.40 EPS does not render as "7.4" beside a
                              // "7.46".
                              <span className={negative ? "text-negative" : undefined}>
                                {formatValue(value, scaleExp, {
                                  parens: true,
                                  dp: isPerShare(row.element) ? 2 : undefined,
                                })}
                              </span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </NodeFrame>
      <Handle
        type="source"
        position={Position.Right}
        className="!h-2 !w-2 !border-0 !bg-hairline-strong"
      />
    </>
  );
}
