"use client";

import { useEffect, useState } from "react";
import { Handle, NodeResizer, Position, useStore, type Node, type NodeProps } from "@xyflow/react";

import { NodeFrame } from "../NodeFrame";
import { api, ApiError } from "@/lib/api";
import { ABSENT, buildRows, cellProvenance, periodCaption } from "@/lib/comparison";
import { fitScale, tierFor } from "@/lib/lod";
import {
  COMPARISON_NODE_HEIGHT,
  LABEL_COLUMN,
  MIN_STATEMENT_HEIGHT,
  MIN_STATEMENT_WIDTH,
  VALUE_COLUMN,
} from "@/lib/nodeSize";
import type { Comparison } from "@/lib/types";

export type ComparisonNodeData = {
  tickers: string[];
  /** The companies this was built from, so the board can draw an edge to each. */
  ciks: number[];
  form: string;
};

export type ComparisonNodeType = Node<ComparisonNodeData, "comparison">;

export function ComparisonNode({ data, height }: NodeProps<ComparisonNodeType>) {
  const { tickers, form } = data;
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [error, setError] = useState<string | null>(null);

  const nodeHeight = height ?? COMPARISON_NODE_HEIGHT;
  // Same stepped selectors the other nodes use, so a zoom gesture re-renders
  // this on a step boundary rather than on every frame.
  const tier = useStore((state) => tierFor(state.transform[2]));
  const scale = useStore((state) => fitScale(state.transform[2], nodeHeight, 0.4));
  const summarised = tier !== "detail";

  const key = tickers.join(",");
  useEffect(() => {
    const controller = new AbortController();
    setComparison(null);
    setError(null);

    api
      .compare(key.split(","), form, controller.signal)
      .then(setComparison)
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setError(cause instanceof ApiError ? cause.message : "Could not compare these filers.");
      });

    return () => controller.abort();
  }, [key, form]);

  const rows = comparison ? buildRows(comparison) : [];

  return (
    <>
      <NodeResizer minWidth={MIN_STATEMENT_WIDTH} minHeight={MIN_STATEMENT_HEIGHT} />
      {/* One per company, so the board can show which filings feed this. */}
      <Handle type="target" position={Position.Left} />
      <NodeFrame
        eyebrow="Comparison"
        title={tickers.join("  ·  ")}
        scale={summarised ? scale : 1}
        meta={<span className="tnum">{form} &middot; each company&rsquo;s most recent filing</span>}
      >
        {summarised ? (
          // At a distance the tickers are what identify this panel, the same
          // way a statement collapses to its headline figures.
          <div
            key={tier}
            className="tier-fade flex flex-1 items-center justify-center overflow-hidden px-4"
          >
            <span
              className="font-semibold leading-none tracking-tight text-ink"
              style={{ fontSize: `${Math.min(26 * scale, nodeHeight * 0.3)}px` }}
            >
              {tickers.join(" · ")}
            </span>
          </div>
        ) : (
          <div key={tier} className="tier-fade nowheel nodrag min-h-0 flex-1 overflow-auto">
            {error !== null && <p className="px-4 py-3 text-[12px] text-negative">{error}</p>}

            {error === null && comparison === null && (
              <p className="px-4 py-3 text-[12px] text-ink-faint">Reading each filing…</p>
            )}

            {comparison !== null && (
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
                    {comparison.companies.map((company) => (
                      <th
                        key={company.registrant.cik}
                        className="border-b border-hairline px-3 pb-2 pt-3 text-right"
                        style={{ width: VALUE_COLUMN, minWidth: VALUE_COLUMN }}
                        title={company.registrant.name}
                      >
                        <span className="block text-[11px] font-semibold text-ink">
                          {company.registrant.ticker || `CIK ${company.registrant.cik}`}
                        </span>
                        {/* Which filing the column is drawn from. Two companies
                            with different year ends are not being compared over
                            the same months, and that has to be visible. */}
                        <span className="eyebrow tnum mt-[3px] block whitespace-nowrap text-[8.5px] text-ink-faint">
                          {periodCaption(company.period_end)}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr
                      key={row.descriptor.metric}
                      className={`transition-colors hover:bg-white/[0.035] ${
                        row.empty ? "text-ink-faint/60" : "text-ink-muted"
                      }`}
                    >
                      <td className="py-[5px] pl-4 pr-4 leading-snug">{row.descriptor.label}</td>
                      {row.cells.map((cell, index) => {
                        const company = comparison.companies[index];
                        return (
                          <td
                            key={company?.registrant.cik ?? index}
                            className={`tabular whitespace-nowrap px-3 py-[5px] text-right ${
                              cell.negative ? "text-negative" : cell.value ? "text-ink" : ""
                            }`}
                            // Two filers report the same metric under different
                            // element names, which is the reason the mapping
                            // exists, so which line was used is inspectable
                            // rather than taken on trust.
                            title={cellProvenance(company?.registrant.ticker ?? "", cell)}
                          >
                            {cell.value === undefined ? (
                              // The filer prints no such line -- Costco reports
                              // no gross profit. Their choice, not our gap, and
                              // a zero would assert something they did not.
                              <span className="text-ink-faint/60">{ABSENT}</span>
                            ) : (
                              cell.text
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </NodeFrame>
    </>
  );
}
