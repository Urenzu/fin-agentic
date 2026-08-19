"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Edge,
  type NodeTypes,
} from "@xyflow/react";

import { TickerSearch } from "./TickerSearch";
import {
  ENTITY_NODE_WIDTH,
  EntityNode,
  entityNodeHeight,
  type EntityNodeType,
} from "./nodes/EntityNode";
import {
  MAX_NODE_HEIGHT,
  StatementNode,
  statementNodeHeight,
  statementNodeWidth,
  type StatementNodeType,
} from "./nodes/StatementNode";
import { api, ApiError, waitForEntity } from "@/lib/api";
import type { AsFiledStatement, Entity, Registrant } from "@/lib/types";
import { frame } from "@/lib/viewport";

type BoardNode = EntityNodeType | StatementNodeType;

const nodeTypes: NodeTypes = {
  entity: EntityNode,
  statement: StatementNode,
};

const COLUMN_GAP = 40;
const ROW_GAP = 60;

/**
 * Lay a company's statements out left to right beside its entity card.
 *
 * Statements are wide and tall, so a grid would leave most of the canvas empty
 * while forcing a scroll to compare two of them. A single row means panning
 * sideways walks through income statement, balance sheet, cash flow in the
 * order a reader expects.
 */
function layout(
  entity: Entity,
  statements: AsFiledStatement[],
  origin: { x: number; y: number },
): BoardNode[] {
  const nodes: BoardNode[] = [
    {
      id: `entity-${entity.registrant.cik}`,
      type: "entity",
      position: origin,
      width: ENTITY_NODE_WIDTH,
      height: entityNodeHeight(entity),
      data: { entity },
      dragHandle: ".drag-handle",
    },
  ];

  let x = origin.x + ENTITY_NODE_WIDTH + COLUMN_GAP;
  for (const statement of statements) {
    nodes.push({
      id: `stmt-${entity.registrant.cik}-${statement.accession}-${statement.short_name}`,
      type: "statement",
      position: { x, y: origin.y },
      width: statementNodeWidth(statement),
      height: statementNodeHeight(statement),
      data: {
        company: entity.registrant.name,
        ticker: entity.registrant.ticker || `CIK ${entity.registrant.cik}`,
        statement,
      },
      dragHandle: ".drag-handle",
    });
    x += statementNodeWidth(statement) + COLUMN_GAP;
  }
  return nodes;
}

function BoardInner() {
  const [nodes, setNodes, onNodesChange] = useNodesState<BoardNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { setViewport } = useReactFlow();
  const pane = useRef<HTMLDivElement>(null);

  // Where the next company's row starts. Boards accumulate, so a second ticker
  // lands below the first rather than on top of it.
  const nextRow = useRef(0);

  const [focusToken, setFocusToken] = useState(0);
  const focusedToken = useRef(0);

  /** Frame the whole board, including whatever was just added. */
  useEffect(() => {
    if (focusToken === focusedToken.current) return;
    focusedToken.current = focusToken;

    const box = pane.current?.getBoundingClientRect();
    if (!box) return;
    const view = frame(nodes, box.width, box.height);
    if (view) void setViewport(view, { duration: 400 });
  }, [focusToken, nodes, setViewport]);

  const upsertEntity = useCallback(
    (entity: Entity) => {
      setNodes((current) =>
        current.map((node) =>
          node.id === `entity-${entity.registrant.cik}`
            ? // The card grows when ingestion replaces the placeholder text with
              // a stat grid and any advisories, so its declared height has to
              // move with it.
              ({ ...node, height: entityNodeHeight(entity), data: { entity } } as BoardNode)
            : node,
        ),
      );
    },
    [setNodes],
  );

  const load = useCallback(
    async (registrant: Registrant) => {
      setBusy(true);
      setError(null);

      const pending: Entity = {
        registrant,
        state: "ingesting",
        shape: null,
        coverage: null,
        error: null,
        advisories: [],
      };

      const origin = { x: 0, y: nextRow.current };

      try {
        // The as-filed path does not need the ledger, so the statements are
        // fetched first and shown while ingestion runs behind them. Waiting for
        // both would leave the canvas blank for the several seconds a cold
        // companyfacts download takes.
        const statements = await api.asFiled(registrant.cik);
        const added = layout(pending, statements, origin);

        setNodes((current) => [
          ...current.filter((node) => !added.some((n) => n.id === node.id)),
          ...added,
        ]);
        setEdges((current) => [
          ...current,
          ...added
            .filter((node) => node.type === "statement")
            .map((node) => ({
              id: `edge-${node.id}`,
              source: `entity-${registrant.cik}`,
              target: node.id,
              animated: false,
            })),
        ]);

        nextRow.current += MAX_NODE_HEIGHT + ROW_GAP;
        // Framing is deferred to an effect so it reads the committed node list
        // rather than a copy assembled inside a state updater, which StrictMode
        // is free to invoke more than once.
        setFocusToken((token) => token + 1);

        await api.resolveCik(registrant.cik, registrant.ticker);
        await waitForEntity(registrant.cik, upsertEntity);
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : String(cause));
      } finally {
        setBusy(false);
      }
    },
    [setEdges, setNodes, upsertEntity],
  );

  const empty = nodes.length === 0;

  const defaultEdgeOptions = useMemo(() => ({ style: { stroke: "#3a3a3a", strokeWidth: 1 } }), []);

  return (
    <div ref={pane} className="relative h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        defaultEdgeOptions={defaultEdgeOptions}
        minZoom={0.15}
        maxZoom={2}
        proOptions={{ hideAttribution: false }}
      >
        <Background variant={BackgroundVariant.Dots} gap={26} size={1.4} color="#2b3142" />
        <Controls position="bottom-right" showInteractive={false} />
        {!empty && (
          <MiniMap
            position="bottom-left"
            pannable
            zoomable
            maskColor="rgb(13 13 13 / 0.82)"
            nodeColor="#3a3a3a"
            className="!rounded-lg !border !border-hairline !bg-surface"
          />
        )}
      </ReactFlow>

      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex justify-center pt-6">
        <div className="pointer-events-auto flex flex-col items-center gap-3">
          <TickerSearch onPick={load} busy={busy} />
          {error && (
            <div className="panel rounded-lg px-4 py-2 text-[12px] text-negative">{error}</div>
          )}
        </div>
      </div>

      {empty && (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-3 text-center">
          <h1 className="text-[28px] font-semibold tracking-tight text-ink">fin-agentic</h1>
          <p className="max-w-md text-[13px] leading-relaxed text-ink-muted">
            Search a ticker to pull its statements straight from EDGAR, rendered exactly as the
            filer laid them out.
          </p>
        </div>
      )}
    </div>
  );
}

export function Board() {
  return (
    <ReactFlowProvider>
      <BoardInner />
    </ReactFlowProvider>
  );
}
