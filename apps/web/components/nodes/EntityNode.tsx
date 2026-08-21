"use client";

import { Handle, NodeResizer, Position, useStore, type NodeProps, type Node } from "@xyflow/react";

import { FilingPicker } from "../FilingPicker";
import { NodeFrame } from "../NodeFrame";
import { fitScale, tierFor } from "@/lib/lod";
import { ENTITY_NODE_HEIGHT, MIN_ENTITY_HEIGHT, MIN_ENTITY_WIDTH } from "@/lib/nodeSize";
import type { Entity } from "@/lib/types";

export type EntityNodeData = {
  entity: Entity;
};

export type EntityNodeType = Node<EntityNodeData, "entity">;

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="eyebrow text-[9px] text-ink-faint">{label}</div>
      <div className="tabular mt-1 text-[13px] font-medium text-ink">{value}</div>
    </div>
  );
}

/**
 * Only a failure gets colour. "Ready" is the expected outcome and a green pill
 * on every card is decoration competing with the figures; an error is the one
 * state that has to interrupt the reader.
 */
const STATE_STYLES: Record<Entity["state"], string> = {
  ingesting: "border-hairline text-ink-faint",
  ready: "border-hairline text-ink-faint",
  error: "border-negative/40 text-negative",
};

export function EntityNode({ data, height: live }: NodeProps<EntityNodeType>) {
  const { entity } = data;
  const { registrant, coverage, shape } = entity;

  const height = live ?? ENTITY_NODE_HEIGHT;

  const resizer = <NodeResizer minWidth={MIN_ENTITY_WIDTH} minHeight={MIN_ENTITY_HEIGHT} />;
  // See StatementNode: selecting the stepped value rather than the raw zoom is
  // what keeps this off the per-frame render path.
  const tier = useStore((state) => tierFor(state.transform[2]));
  const scale = useStore((state) => fitScale(state.transform[2], height));
  const summarised = tier !== "detail";
  const identityOnly = tier === "identity";

  // The shape line names what kind of filer this is; the advisory explains the
  // consequence. Prefixing keeps the label without repeating the explanation.
  const advisories = entity.advisories.map((advisory) =>
    shape && advisory === shape.message
      ? { key: advisory, label: shape.shape, text: advisory }
      : { key: advisory, label: null, text: advisory },
  );

  if (identityOnly) {
    // Furthest out, the card is a label and nothing else. Keeping the header
    // here would spend most of a 154px panel on a CIK nobody can read at this
    // distance, and leave the ticker clipped.
    return (
      <>
        {resizer}
        <div className="panel panel-frame tier-fade drag-handle flex h-full w-full cursor-grab items-center justify-center overflow-hidden rounded-xl px-3">
          <span
            className="font-semibold leading-none tracking-tight text-ink"
            style={{ fontSize: `${Math.min(height * 0.42, 88)}px` }}
          >
            {registrant.ticker || `CIK ${registrant.cik}`}
          </span>
        </div>
        <Handle type="source" position={Position.Right} />
      </>
    );
  }

  return (
    <>
      {resizer}
      <NodeFrame
        eyebrow={`CIK ${registrant.cik}`}
        title={registrant.name}
        scale={summarised ? scale : 1}
        meta={registrant.ticker || undefined}
        action={
          <span
            className={`eyebrow shrink-0 rounded-full border px-2 py-[3px] text-[8.5px] ${STATE_STYLES[entity.state]}`}
          >
            {entity.state}
          </span>
        }
      >
        {summarised ? (
          // The anchor of the row. At a distance the ticker is the only thing
          // that has to survive -- it is how a reader tells which band of the
          // board belongs to which company.
          <div
            key={tier}
            className="tier-fade flex flex-1 items-center justify-center overflow-hidden px-4"
          >
            <span
              className="font-semibold leading-none tracking-tight text-ink"
              style={{ fontSize: `${Math.min(34 * scale, height - 66 * scale - 16)}px` }}
            >
              {registrant.ticker || `CIK ${registrant.cik}`}
            </span>
          </div>
        ) : (
          <div key={tier} className="tier-fade nowheel overflow-auto px-4 py-3">
            {coverage ? (
              <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                <Stat label="History" value={`${coverage.history_years.toFixed(1)} yrs`} />
                <Stat label="Annual reports" value={String(coverage.annual_reports)} />
                {coverage.earliest && coverage.latest && (
                  <div className="col-span-2">
                    <Stat label="Covering" value={`${coverage.earliest} → ${coverage.latest}`} />
                  </div>
                )}
              </div>
            ) : (
              <p className="text-[12px] leading-relaxed text-ink-muted">
                {entity.state === "error"
                  ? (entity.error ?? "Ingestion failed.")
                  : "Building the ledger from EDGAR. The statements alongside render from the filing itself and do not wait for this."}
              </p>
            )}

            {/* Advisories describe conditions that produce entirely reasonable
                looking output built on the wrong data, so they are shown rather
                than logged. An unsupported shape already contributes its message
                here, so rendering `shape.message` separately printed it twice. */}
            <FilingPicker registrant={registrant} />

            {advisories.map((advisory) => (
              <p
                key={advisory.key}
                className="mt-3 rounded-lg border border-caution/20 bg-caution/[0.06] px-3 py-2 text-[11px] leading-relaxed text-caution/90"
              >
                {advisory.label && (
                  <span className="mr-1.5 font-semibold uppercase tracking-wide">
                    {advisory.label}
                  </span>
                )}
                {advisory.text}
              </p>
            ))}
          </div>
        )}
      </NodeFrame>
      <Handle type="source" position={Position.Right} />
    </>
  );
}
