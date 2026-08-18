"use client";

import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";

import { NodeFrame } from "../NodeFrame";
import { formatValue, scaleExponent } from "@/lib/decimal";
import type { AsFiledStatement } from "@/lib/types";

export type StatementNodeData = {
  company: string;
  statement: AsFiledStatement;
};

export type StatementNodeType = Node<StatementNodeData, "statement">;

const LABEL_COLUMN = 300;
const VALUE_COLUMN = 108;
const INDENT_STEP = 13;

const HEADER_HEIGHT = 66;
const COLUMN_HEADER_HEIGHT = 34;
const DATA_ROW_HEIGHT = 23;
const SECTION_ROW_HEIGHT = 30;
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
  const { statement, company } = data;
  const monetaryExp = scaleExponent(statement.monetary_scale);
  const shareExp = scaleExponent(statement.share_scale);

  const filed = new Date(statement.filed).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <>
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-white/20" />
      <NodeFrame
        eyebrow={company}
        title={statement.short_name}
        meta={
          <span className="tabular">
            {statement.form} &middot; filed {filed} &middot; {unitsCaption(monetaryExp)}
          </span>
        }
        action={
          <a
            href={statement.source_url}
            target="_blank"
            rel="noreferrer"
            title="The SEC exhibit these numbers came from"
            className="nodrag shrink-0 rounded-md border border-white/10 bg-white/[0.04] px-2 py-1 text-[10px] font-medium text-ink-muted transition hover:border-accent/50 hover:text-ink"
          >
            SEC ↗
          </a>
        }
      >
        <div className="nowheel nodrag overflow-auto">
          <table className="w-full border-collapse text-[12px]">
            <thead className="sticky top-0 z-10 bg-surface/95 backdrop-blur">
              <tr>
                <th
                  className="px-4 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-ink-faint"
                  style={{ width: LABEL_COLUMN }}
                />
                {statement.columns.map((column) => (
                  <th
                    key={column}
                    className="whitespace-nowrap px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-ink-muted"
                    style={{ width: VALUE_COLUMN }}
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
                        className="px-4 pb-1 pt-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-faint"
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
                    className={
                      row.is_total
                        ? "border-t border-white/[0.14] font-semibold text-ink"
                        : "text-ink-muted hover:bg-white/[0.03]"
                    }
                  >
                    <td
                      className="py-[5px] pr-3 leading-snug"
                      style={{ paddingLeft: 16 + row.indent * INDENT_STEP }}
                      title={row.tag ?? undefined}
                    >
                      {row.label}
                    </td>
                    {statement.columns.map((column) => {
                      const value = row.values[column];
                      return (
                        <td
                          key={column}
                          className="tabular whitespace-nowrap px-3 py-[5px] text-right"
                        >
                          {value === undefined ? (
                            // Blank on the face of the statement means the line
                            // did not apply to that period. Rendering a zero
                            // would assert something the filer did not.
                            <span className="text-ink-faint/50">—</span>
                          ) : (
                            // Monetary and share figures are left unrounded:
                            // dividing by the scale the parser applied recovers
                            // exactly the digits the filing printed. Per-share
                            // amounts are pinned to two places so a $7.40 EPS
                            // does not render as "7.4" beside a "7.46".
                            <span className={value.startsWith("-") ? "text-negative/90" : undefined}>
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
      </NodeFrame>
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-white/20" />
    </>
  );
}
