"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useReactFlow,
  type Edge,
  type NodeTypes,
} from "@xyflow/react";

import { BoardActionsProvider, type BoardActions } from "./BoardActions";
import { TickerSearch } from "./TickerSearch";
import { EntityNode, type EntityNodeType } from "./nodes/EntityNode";
import { StatementNode, type StatementNodeType } from "./nodes/StatementNode";
import {
  DEFAULT_STATEMENT_HEIGHT,
  ENTITY_NODE_WIDTH,
  entityNodeHeight,
  statementNodeHeight,
  statementNodeWidth,
} from "@/lib/nodeSize";
import { api, ApiError, waitForEntity } from "@/lib/api";
import type { AsFiledStatement, Entity, FilingIndex, Registrant } from "@/lib/types";
import { frame } from "@/lib/viewport";

type BoardNode = EntityNodeType | StatementNodeType;

const nodeTypes: NodeTypes = {
  entity: EntityNode,
  statement: StatementNode,
};

const COLUMN_GAP = 40;
const ROW_GAP = 60;

function entityNode(entity: Entity, origin: { x: number; y: number }): EntityNodeType {
  return {
    id: `entity-${entity.registrant.cik}`,
    type: "entity",
    position: origin,
    width: ENTITY_NODE_WIDTH,
    height: entityNodeHeight(entity),
    data: { entity },
    dragHandle: ".drag-handle",
  };
}

/**
 * Lay one filing's statements out left to right in a row of their own.
 *
 * Statements are wide and tall, so a grid would leave most of the canvas empty
 * while forcing a scroll to compare two of them. A single row means panning
 * sideways walks through income statement, balance sheet, cash flow in the
 * order a reader expects.
 *
 * The row is indented past the entity column so a company's filings stack
 * under its card rather than beside it -- several filings can be open at once,
 * and each needs a row it does not share.
 */
function statementRow(
  registrant: Registrant,
  statements: AsFiledStatement[],
  origin: { x: number; y: number },
): StatementNodeType[] {
  const nodes: StatementNodeType[] = [];
  let x = origin.x;
  for (const statement of statements) {
    nodes.push({
      id: statementNodeId(registrant.cik, statement),
      type: "statement",
      position: { x, y: origin.y },
      width: statementNodeWidth(statement),
      height: statementNodeHeight(statement),
      data: {
        cik: registrant.cik,
        company: registrant.name,
        ticker: registrant.ticker || `CIK ${registrant.cik}`,
        statement,
      },
      dragHandle: ".drag-handle",
    });
    x += statementNodeWidth(statement) + COLUMN_GAP;
  }
  return nodes;
}

function statementNodeId(cik: number, statement: AsFiledStatement): string {
  return `stmt-${cik}-${statement.accession}-${statement.short_name}`;
}

function BoardInner() {
  const [nodes, setNodes, onNodesChange] = useNodesState<BoardNode>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { setViewport } = useReactFlow();
  const pane = useRef<HTMLDivElement>(null);

  // Where each company's card sits, and how many filing rows it has open.
  // A filing belongs beside the card it was opened from, so its statements are
  // placed against that company's own origin rather than at the foot of the
  // board -- otherwise opening one pushes it arbitrarily far from the picker.
  const origins = useRef(new Map<number, number>());
  const rowCounts = useRef(new Map<number, number>());

  const [focusToken, setFocusToken] = useState(0);
  const focusedToken = useRef(0);
  const focusTarget = useRef<readonly string[] | null>(null);

  /**
   * Frame what was just added, rather than the whole board.
   *
   * Fitting everything sounds helpful and is not: six nodes already push the
   * zoom below the summary threshold, which collapses the entity card to a
   * bare ticker -- taking the filing picker off screen -- and renders the
   * statements just opened as headline figures rather than as tables. Framing
   * the new row keeps it at reading size, which is why it was opened.
   */
  useEffect(() => {
    if (focusToken === focusedToken.current) return;
    focusedToken.current = focusToken;

    const box = pane.current?.getBoundingClientRect();
    if (!box) return;

    const target = focusTarget.current;
    const framed = target === null ? nodes : nodes.filter((node) => target.includes(node.id));
    const view = frame(framed.length > 0 ? framed : nodes, box.width, box.height);
    if (view) void setViewport(view, { duration: 400 });
  }, [focusToken, nodes, setViewport]);

  const upsertEntity = useCallback(
    (entity: Entity) => {
      setNodes((current) =>
        current.map((node) =>
          node.id === `entity-${entity.registrant.cik}`
            ? ({
                ...node,
                // The card grows when ingestion replaces the placeholder text
                // with a stat grid and any advisories, so its declared height
                // has to move with it -- unless the reader has already sized it
                // themselves, in which case theirs wins.
                height:
                  node.type === "entity" && node.data.sized === true
                    ? node.height
                    : entityNodeHeight(entity),
                data: { ...node.data, entity },
              } as BoardNode)
            : node,
        ),
      );
    },
    [setNodes],
  );

  /**
   * Seed the board with a company.
   *
   * Only the entity card: which filing to read is the reader's choice, and
   * opening the latest 10-K unasked meant the board could show figures eleven
   * months stale while newer quarterlies sat one query away. The card carries
   * the picker, so the next step is visible without anything being assumed.
   */
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

      const cardId = `entity-${registrant.cik}`;
      setNodes((current) => {
        // Below everything already on the board, measured from what is there
        // rather than from a running total, so a company whose filings have
        // grown downward is still cleared.
        const bottom = current.reduce(
          (lowest, node) => Math.max(lowest, node.position.y + (node.height ?? 0)),
          0,
        );
        const y = current.length === 0 ? 0 : bottom + ROW_GAP;
        origins.current.set(registrant.cik, y);
        const card = entityNode(pending, { x: 0, y });
        return [...current.filter((node) => node.id !== card.id), card];
      });
      focusTarget.current = [cardId];
      setFocusToken((token) => token + 1);

      try {
        await api.resolveCik(registrant.cik, registrant.ticker);
        await waitForEntity(registrant.cik, upsertEntity);
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : String(cause));
      } finally {
        setBusy(false);
      }
    },
    [setNodes, upsertEntity],
  );

  const [openAccessions, setOpenAccessions] = useState<ReadonlySet<string>>(new Set());
  const [pendingAccessions, setPendingAccessions] = useState<ReadonlySet<string>>(new Set());

  /** Put a filing's statements on the board, or take them off again. */
  const toggleFiling = useCallback(
    (registrant: Registrant, filing: FilingIndex) => {
      const { accession } = filing;

      if (openAccessions.has(accession)) {
        setNodes((current) =>
          current.filter(
            (node) => !(node.type === "statement" && node.data.statement.accession === accession),
          ),
        );
        setOpenAccessions((current) => {
          const next = new Set(current);
          next.delete(accession);
          return next;
        });
        return;
      }

      // Marked pending up front: a cold filing takes a few seconds to fetch and
      // parse, and without this the row in the picker looks like a dead click.
      setPendingAccessions((current) => new Set(current).add(accession));
      setError(null);

      void (async () => {
        try {
          const statements = await api.asFiled(registrant.cik, filing.form, accession);
          const origin = origins.current.get(registrant.cik) ?? 0;
          const taken = rowCounts.current.get(registrant.cik) ?? 0;
          const row = statementRow(registrant, statements, {
            x: ENTITY_NODE_WIDTH + COLUMN_GAP,
            y: origin + taken * (DEFAULT_STATEMENT_HEIGHT + ROW_GAP),
          });
          rowCounts.current.set(registrant.cik, taken + 1);

          setNodes((current) => [
            ...current.filter((node) => !row.some((added) => added.id === node.id)),
            ...row,
          ]);
          setOpenAccessions((current) => new Set(current).add(accession));
          // The card as well as the first statement: framing the row alone
          // takes the picker off screen, and opening a second filing then
          // means panning back to find it.
          focusTarget.current = [`entity-${registrant.cik}`, row[0]?.id].filter(
            (id): id is string => id !== undefined,
          );
          setFocusToken((token) => token + 1);
        } catch (cause) {
          setError(cause instanceof ApiError ? cause.message : String(cause));
        } finally {
          setPendingAccessions((current) => {
            const next = new Set(current);
            next.delete(accession);
            return next;
          });
        }
      })();
    },
    [openAccessions, setNodes],
  );

  const actions = useMemo<BoardActions>(
    () => ({ toggleFiling, openAccessions, pendingAccessions }),
    [toggleFiling, openAccessions, pendingAccessions],
  );

  /**
   * Edges are derived, not stored.
   *
   * Held as their own state they went missing: `setEdges` runs in the same tick
   * as the `setNodes` that adds a filing's statements, and React Flow prunes
   * edges whose endpoints it does not yet know about -- so the first filing's
   * connectors were dropped and only the most recently opened row kept any.
   * An edge here carries no information that the nodes do not already have, so
   * computing it removes the race rather than timing around it, and closing a
   * filing drops its connectors for free.
   */
  const edges = useMemo<Edge[]>(
    () =>
      nodes.flatMap((node) =>
        node.type === "statement"
          ? [
              {
                id: `edge-${node.id}`,
                source: `entity-${node.data.cik}`,
                target: node.id,
                animated: false,
              },
            ]
          : [],
      ),
    [nodes],
  );

  const empty = nodes.length === 0;

  const defaultEdgeOptions = useMemo(() => ({ style: { stroke: "#2b2b33", strokeWidth: 1 } }), []);

  return (
    <BoardActionsProvider value={actions}>
      <div ref={pane} className="relative h-full w-full">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          nodeTypes={nodeTypes}
          defaultEdgeOptions={defaultEdgeOptions}
          nodesConnectable={false}
          minZoom={0.15}
          maxZoom={2}
          proOptions={{ hideAttribution: false }}
        >
          <Background variant={BackgroundVariant.Dots} gap={30} size={1} color="#1e1e24" />
          <Controls position="bottom-right" showInteractive={false} />
          {!empty && (
            <MiniMap
              position="bottom-left"
              pannable
              zoomable
              maskColor="rgb(8 8 10 / 0.85)"
              nodeColor="#2b2b33"
              className="!rounded-xl !border !border-hairline !bg-surface"
            />
          )}
        </ReactFlow>

        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex justify-center pt-6">
          <div className="pointer-events-auto flex flex-col items-center gap-3">
            <TickerSearch onPick={load} busy={busy} />
            {error && (
              <div className="panel rounded-xl px-4 py-2 text-[12px] text-negative">{error}</div>
            )}
          </div>
        </div>

        {empty && (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-3 text-center">
            <h1 className="text-[30px] font-semibold tracking-[-0.03em] text-ink">fin-agentic</h1>
            <p className="max-w-sm text-[13px] leading-relaxed text-ink-faint">
              Search a ticker to pull its statements straight from EDGAR, rendered exactly as the
              filer laid them out.
            </p>
          </div>
        )}
      </div>
    </BoardActionsProvider>
  );
}

export function Board() {
  return (
    <ReactFlowProvider>
      <BoardInner />
    </ReactFlowProvider>
  );
}
