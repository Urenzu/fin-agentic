"use client";

import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";

import { NodeFrame } from "../NodeFrame";
import type { Entity } from "@/lib/types";

export type EntityNodeData = {
  entity: Entity;
};

export type EntityNodeType = Node<EntityNodeData, "entity">;

export const ENTITY_NODE_WIDTH = 340;

const CHARS_PER_LINE = 52;
const LINE_HEIGHT = 16;

/**
 * The card's height for the state it is in.
 *
 * Recomputed whenever the entity changes, because the card grows as ingestion
 * finishes: a "building the ledger" sentence becomes a stat grid, and an
 * unsupported filer adds an advisory. See statementNodeHeight for why the size
 * is declared rather than measured.
 */
export function entityNodeHeight(entity: Entity): number {
  const chrome = 66 + 24;
  const body = entity.coverage
    ? 92 + (entity.coverage.earliest && entity.coverage.latest ? 46 : 0)
    : 64;
  const advisories = entity.advisories.reduce(
    (total, advisory) =>
      total + 26 + Math.ceil(advisory.length / CHARS_PER_LINE) * LINE_HEIGHT,
    0,
  );
  return chrome + body + advisories;
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-ink-faint">{label}</div>
      <div className="tabular mt-0.5 text-[13px] font-semibold text-ink">{value}</div>
    </div>
  );
}

const STATE_STYLES: Record<Entity["state"], string> = {
  ingesting: "bg-accent/15 text-accent",
  ready: "bg-positive/15 text-positive",
  error: "bg-negative/15 text-negative",
};

export function EntityNode({ data }: NodeProps<EntityNodeType>) {
  const { entity } = data;
  const { registrant, coverage, shape } = entity;

  // The shape line names what kind of filer this is; the advisory explains the
  // consequence. Prefixing keeps the label without repeating the explanation.
  const advisories = entity.advisories.map((advisory) =>
    shape && advisory === shape.message ? { key: advisory, label: shape.shape, text: advisory } : { key: advisory, label: null, text: advisory },
  );

  return (
    <>
      <NodeFrame
        eyebrow={`CIK ${registrant.cik}`}
        title={registrant.name}
        meta={registrant.ticker || undefined}
        action={
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium capitalize ${STATE_STYLES[entity.state]}`}
          >
            {entity.state}
          </span>
        }
      >
        <div className="nowheel overflow-auto px-4 py-3">
          {coverage ? (
            <div className="grid grid-cols-2 gap-x-4 gap-y-3">
              <Stat label="History" value={`${coverage.history_years.toFixed(1)} yrs`} />
              <Stat label="Annual reports" value={String(coverage.annual_reports)} />
              <Stat label="Facts" value={coverage.fact_count.toLocaleString()} />
              <Stat
                label="Corroborated"
                value={
                  coverage.fact_count
                    ? `${Math.round((coverage.verified_count / coverage.fact_count) * 100)}%`
                    : "—"
                }
              />
              {coverage.earliest && coverage.latest && (
                <div className="col-span-2">
                  <Stat label="Covering" value={`${coverage.earliest} → ${coverage.latest}`} />
                </div>
              )}
            </div>
          ) : (
            <p className="text-[12px] text-ink-muted">
              {entity.state === "error"
                ? (entity.error ?? "Ingestion failed.")
                : "Building the ledger from EDGAR. The statements above render from the filing itself and do not wait for this."}
            </p>
          )}

          {/* Advisories describe conditions that produce entirely reasonable
              looking output built on the wrong data, so they are shown rather
              than logged. An unsupported shape already contributes its message
              here, so rendering `shape.message` separately printed it twice. */}
          {advisories.map((advisory) => (
            <p
              key={advisory.key}
              className="mt-3 rounded-lg border border-amber-400/20 bg-amber-400/[0.06] px-3 py-2 text-[11px] leading-relaxed text-amber-200/90"
            >
              {advisory.label && (
                <span className="mr-1.5 font-semibold uppercase tracking-wide text-amber-200">
                  {advisory.label}
                </span>
              )}
              {advisory.text}
            </p>
          ))}
        </div>
      </NodeFrame>
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-white/20" />
    </>
  );
}
