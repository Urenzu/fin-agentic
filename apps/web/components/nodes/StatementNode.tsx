"use client";

import { Handle, Position, useStore, type NodeProps, type Node } from "@xyflow/react";

import { NodeFrame } from "../NodeFrame";
import { abbreviate, formatValue, scaleExponent } from "@/lib/decimal";
import { fitScale, headlineCapacity, headlineRows, IDENTITY_BELOW, SUMMARY_BELOW } from "@/lib/lod";
import type { AsFiledStatement } from "@/lib/types";

export type StatementNodeData = {
  company: string;
  ticker: string;
  statement: AsFiledStatement;
};

export type StatementNodeType = Node<StatementNodeData, "statement">;

const LABEL_COLUMN = 300;
const VALUE_COLUMN = 108;
const INDENT_STEP = 13;

const HEADER_HEIGHT = 66;
const COLUMN_HEADER_HEIGHT = 34;
const DATA_ROW_HEIGHT = 24;
const SECTION_ROW_HEIGHT = 31;
export const MAX_NODE_HEIGHT = 560;

export function statementNodeWidth(statement: AsFiledStatement): number {
  return LABEL_COLUMN + Math.max(statement.columns.length, 1) * VALUE_COLUMN + 32;
}

/**
 * The rendered height of a statement, estimated from its row counts.
 *
 * Declaring a size matters beyond layout: React Flow keeps a node
 * `visibility: hidden` until its ResizeObserver has measured it, and under
 * StrictMode's double mount that observer can be torn down before it ever
 * fires -- leaving nodes invisible and `fitView` a no-op, because the library
 * believes it has nothing with a known size to fit. Supplying dimensions up
 * front removes the dependency on measurement entirely.
 */
export function statementNodeHeight(statement: AsFiledStatement): number {
  const body = statement.rows.reduce(
    (total, row) => total + (row.is_abstract ? SECTION_ROW_HEIGHT : DATA_ROW_HEIGHT),
    0,
  );
  return Math.min(HEADER_HEIGHT + COLUMN_HEADER_HEIGHT + body + 12, MAX_NODE_HEIGHT);
}

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

export function StatementNode({ data }: NodeProps<StatementNodeType>) {
  const { statement, company, ticker } = data;
  const zoom = useStore((state) => state.transform[2]);
  const monetaryExp = scaleExponent(statement.monetary_scale);
  const shareExp = scaleExponent(statement.share_scale);

  const filed = new Date(statement.filed).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  // Bounded by the panel: a comprehensive-income statement can be short
  // enough that an unbounded header would not leave room for the figures.
  const nodeHeight = statementNodeHeight(statement);
  const scale = fitScale(zoom, nodeHeight, 0.4);
  const summarised = zoom < SUMMARY_BELOW;
  const identityOnly = zoom < IDENTITY_BELOW;
  const newest = statement.columns[0];

  return (
    <>
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
          <a
            href={statement.source_url}
            target="_blank"
            rel="noreferrer"
            title="The SEC exhibit these numbers came from"
            className="nodrag shrink-0 rounded border border-hairline-strong px-2 py-1 text-[10px] font-medium text-ink-muted transition hover:border-ink-faint hover:text-ink"
          >
            SEC ↗
          </a>
        }
      >
        {summarised ? (
          // Far view: the table is texture at this distance, so it is replaced
          // by the handful of lines that carry the most meaning per pixel, set
          // large enough to read without zooming back in.
          <div
            className="flex flex-1 flex-col justify-center overflow-hidden"
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
          <div className="nowheel nodrag overflow-auto">
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
