"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
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
import { ComparisonNode, type ComparisonNodeType } from "./nodes/ComparisonNode";
import { EntityNode, type EntityNodeType } from "./nodes/EntityNode";
import { StatementNode, type StatementNodeType } from "./nodes/StatementNode";
import {
  COMPARISON_NODE_HEIGHT,
  comparisonNodeWidth,
  DEFAULT_STATEMENT_HEIGHT,
  ENTITY_NODE_HEIGHT,
  ENTITY_NODE_WIDTH,
  STATEMENT_WIDTH,
} from "@/lib/nodeSize";
import { api, ApiError, waitForEntity } from "@/lib/api";
import type { AsFiledStatement, Entity, FilingIndex, Registrant } from "@/lib/types";
import type { CanvasNode } from "@/lib/canvas";
import { companiesToRestore, filingsToRestore, toSnapshot } from "@/lib/canvasSnapshot";
import { nextCardOrigin, nextRowOrigin } from "@/lib/placement";
import { filingKey, RequestCache } from "@/lib/prefetch";
import { removeFromBoard } from "@/lib/removal";
import { frame } from "@/lib/viewport";

type BoardNode = EntityNodeType | StatementNodeType | ComparisonNodeType;

const nodeTypes: NodeTypes = {
  entity: EntityNode,
  statement: StatementNode,
  comparison: ComparisonNode,
};

const COLUMN_GAP = 40;
const ROW_GAP = 60;

/**
 * The board's grid.
 *
 * Every statement occupies one cell of the same size, so the nth statement of
 * one filing sits directly above the nth of the next and the gaps between
 * panels are the same everywhere. The alternative -- advancing by each panel's
 * own width -- made the columns disagree between a 10-K row and a 10-Q row,
 * since the two forms print a different number of periods.
 */
const COLUMN_PITCH = STATEMENT_WIDTH + COLUMN_GAP;
const ROW_PITCH = DEFAULT_STATEMENT_HEIGHT + ROW_GAP;

/** Where a company's filings begin, one gap right of its card. */
const STATEMENT_ORIGIN_X = ENTITY_NODE_WIDTH + COLUMN_GAP;

/**
 * The zoom a newly opened filing is never framed below.
 *
 * A company card and a filing row two bands down only fit together at around
 * 0.5, which is under `SUMMARY_BELOW` -- so fitting both collapsed the
 * statements just opened into headline figures. Reading size wins, and the
 * card stays a short pan away.
 */
const READING_ZOOM = 0.7;

function entityNode(entity: Entity, origin: { x: number; y: number }): EntityNodeType {
  return {
    id: `entity-${entity.registrant.cik}`,
    type: "entity",
    position: origin,
    width: ENTITY_NODE_WIDTH,
    height: ENTITY_NODE_HEIGHT,
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
 *
 * Columns advance by a fixed pitch rather than by each panel's own width, so
 * every filing's statements land on the same grid.
 */
function statementRow(
  registrant: Registrant,
  statements: AsFiledStatement[],
  origin: { x: number; y: number },
): StatementNodeType[] {
  return statements.map((statement, index) => ({
    id: statementNodeId(registrant.cik, statement),
    type: "statement",
    position: { x: origin.x + index * COLUMN_PITCH, y: origin.y },
    width: STATEMENT_WIDTH,
    height: DEFAULT_STATEMENT_HEIGHT,
    data: {
      cik: registrant.cik,
      company: registrant.name,
      ticker: registrant.ticker || `CIK ${registrant.cik}`,
      statement,
    },
    dragHandle: ".drag-handle",
  }));
}

/** Where a saved node sat, by the id it will be rebuilt under. */
function positionOf(snapshot: CanvasNode[], id: string): { x: number; y: number } | undefined {
  const found = snapshot.find((node) => node.kind === "entity" && `entity-${node.cik}` === id);
  return found ? { x: found.x, y: found.y } : undefined;
}

/** The board id a saved statement will be rebuilt under. */
function nodeIdOf(node: CanvasNode, cik: number): string | null {
  return node.kind === "statement" ? `stmt-${cik}-${node.accession}-${node.shortName}` : null;
}

function statementNodeId(cik: number, statement: AsFiledStatement): string {
  return `stmt-${cik}-${statement.accession}-${statement.short_name}`;
}

type BoardProps = {
  /** The canvas to draw. Restored on mount; the board is remounted on switch. */
  snapshot: CanvasNode[];
  /** Called whenever the board changes, with references rather than figures. */
  onSnapshot: (nodes: CanvasNode[]) => void;
};

function BoardInner({ snapshot, onSnapshot }: BoardProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<BoardNode>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { setViewport } = useReactFlow();
  const pane = useRef<HTMLDivElement>(null);

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
    const boxes = framed.length > 0 ? framed : nodes;

    // The last target is what the reader just asked for -- the opened row's
    // first statement, or the card itself on a fresh search -- so that is what
    // stays centred if the two cannot be shown together at reading size.
    const anchorId = target?.[target.length - 1];
    const anchor = boxes.find((node) => node.id === anchorId);

    const view = frame(boxes, box.width, box.height, { minZoom: READING_ZOOM, anchor });
    if (view) void setViewport(view, { duration: 400 });
  }, [focusToken, nodes, setViewport]);

  const upsertEntity = useCallback(
    (entity: Entity) => {
      setNodes((current) =>
        current.map((node) =>
          node.id === `entity-${entity.registrant.cik}`
            ? // Height is deliberately left alone. The card is a fixed cell of
              // the grid, so there is nothing to recompute as ingestion fills
              // it in -- and not touching it means a card the reader has
              // dragged taller keeps the size they gave it.
              ({ ...node, data: { ...node.data, entity } } as BoardNode)
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
        const card = entityNode(pending, nextCardOrigin(current, ROW_GAP, ENTITY_NODE_HEIGHT));
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

  // Filings already fetched or being fetched. Held for the life of the board
  // rather than per node, so closing a filing and reopening it costs nothing
  // and a hover that precedes a click is not wasted.
  const filings = useRef(new RequestCache<AsFiledStatement[]>());

  /**
   * Fetch a filing ahead of the click.
   *
   * A filing is immutable once submitted and the request is a plain GET of
   * public data, so speculating costs bandwidth and nothing else. Failures are
   * swallowed here and surfaced only if the reader actually clicks.
   */
  const prefetchFiling = useCallback((registrant: Registrant, filing: FilingIndex) => {
    filings.current.warm(filingKey(registrant.cik, filing.form, filing.accession), (signal) =>
      api.asFiled(registrant.cik, filing.form, filing.accession, signal),
    );
  }, []);

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
          const statements = await filings.current.fetch(
            filingKey(registrant.cik, filing.form, accession),
            (signal) => api.asFiled(registrant.cik, filing.form, accession, signal),
          );
          // Placed inside the update, because where a row belongs depends on
          // what is on the board *now* -- which filings are open, and where the
          // reader has dragged the card.
          setNodes((current) => {
            const row = statementRow(
              registrant,
              statements,
              nextRowOrigin(current, registrant.cik, {
                originX: STATEMENT_ORIGIN_X,
                rowPitch: ROW_PITCH,
              }),
            );
            return [
              ...current.filter((node) => !row.some((added) => added.id === node.id)),
              ...row,
            ];
          });
          setOpenAccessions((current) => new Set(current).add(accession));
          // The card as well as the first statement: framing the row alone
          // takes the picker off screen, and opening a second filing then
          // means panning back to find it.
          const first = statements[0];
          focusTarget.current = [
            `entity-${registrant.cik}`,
            first ? statementNodeId(registrant.cik, first) : undefined,
          ].filter((id): id is string => id !== undefined);
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

  /**
   * Put a comparison of everything on the board into its own panel.
   *
   * Built from the companies already there rather than from a separate picker:
   * the board is the selection, so comparing is one action on what the reader
   * has already assembled instead of choosing the same companies twice.
   */
  const compareBoard = useCallback(() => {
    setNodes((current) => {
      const entities = current.filter((node): node is EntityNodeType => node.type === "entity");
      if (entities.length < 2) return current;

      const companies = entities
        .map((node) => node.data.entity.registrant)
        .filter((r) => r.ticker !== "")
        .map((r) => ({ cik: r.cik, ticker: r.ticker }));
      if (companies.length < 2) return current;

      // Left of the entity column and vertically centred on it, so it reads as
      // a summary of the board rather than as another company on it.
      const top = Math.min(...entities.map((node) => node.position.y));
      const bottom = Math.max(
        ...entities.map((node) => node.position.y + (node.height ?? ENTITY_NODE_HEIGHT)),
      );
      const width = comparisonNodeWidth(companies.length);

      const node: ComparisonNodeType = {
        id: "comparison",
        type: "comparison",
        position: {
          x: -(width + COLUMN_GAP),
          y: (top + bottom) / 2 - COMPARISON_NODE_HEIGHT / 2,
        },
        width,
        height: COMPARISON_NODE_HEIGHT,
        data: { companies, form: "10-K" },
        dragHandle: ".drag-handle",
      };

      focusTarget.current = ["comparison"];
      setFocusToken((token) => token + 1);
      return [...current.filter((n) => n.id !== node.id), node];
    });
  }, [setNodes]);

  /** Companies on the board that a comparison could be built from. */
  const comparable = useMemo(
    () =>
      nodes.filter((node) => node.type === "entity" && node.data.entity.registrant.ticker !== "")
        .length,
    [nodes],
  );

  /**
   * Take a panel off the board, along with anything that depended on it.
   *
   * The cascade lives in `lib/removal.ts`; what belongs here is the part the
   * board owns -- a filing whose last panel has gone is no longer open, so the
   * picker has to stop marking it. Leaving it marked gives the reader a row
   * that looks active and does nothing when clicked, because the board already
   * thinks it opened it.
   */
  const removeNode = useCallback(
    (id: string) => {
      setNodes((current) => {
        const { nodes: kept, closedAccessions } = removeFromBoard(current, id);
        if (closedAccessions.length > 0) {
          setOpenAccessions((open) => {
            const next = new Set(open);
            for (const accession of closedAccessions) next.delete(accession);
            return next;
          });
        }
        return kept;
      });
    },
    [setNodes],
  );

  const actions = useMemo<BoardActions>(
    () => ({ toggleFiling, prefetchFiling, removeNode, openAccessions, pendingAccessions }),
    [toggleFiling, prefetchFiling, removeNode, openAccessions, pendingAccessions],
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
      nodes.flatMap((node) => {
        if (node.type === "statement") {
          return [
            {
              id: `edge-${node.id}`,
              source: `entity-${node.data.cik}`,
              target: node.id,
              animated: false,
            },
          ];
        }
        // A comparison draws from several companies at once, so it gets an
        // edge from each -- which is also what shows at a glance who is in it.
        if (node.type === "comparison") {
          return node.data.companies.map((company) => ({
            id: `edge-${node.id}-${company.cik}`,
            source: `entity-${company.cik}`,
            target: node.id,
            animated: false,
          }));
        }
        return [];
      }),
    [nodes],
  );

  /**
   * Draw the saved canvas.
   *
   * Runs once per canvas, because the board is remounted when one is chosen.
   * The cards go up immediately with what the snapshot remembers, so the
   * layout is there before any request returns; the filings then arrive and
   * take the positions they were saved at.
   */
  const restored = useRef(false);
  useEffect(() => {
    if (restored.current || snapshot.length === 0) return;
    restored.current = true;

    const cards = companiesToRestore(snapshot).map((company) =>
      entityNode(
        {
          registrant: company,
          state: "ingesting",
          shape: null,
          coverage: null,
          error: null,
          advisories: [],
        },
        positionOf(snapshot, `entity-${company.cik}`) ?? { x: 0, y: 0 },
      ),
    );
    const comparisons = snapshot.flatMap((node) =>
      node.kind === "comparison"
        ? [
            {
              id: "comparison",
              type: "comparison" as const,
              position: { x: node.x, y: node.y },
              width: node.width ?? comparisonNodeWidth(node.companies.length),
              height: node.height ?? COMPARISON_NODE_HEIGHT,
              data: { companies: node.companies, form: node.form },
              dragHandle: ".drag-handle",
            },
          ]
        : [],
    );
    setNodes([...cards, ...comparisons] as BoardNode[]);

    // Coverage and advisories are not in the snapshot -- they are facts about
    // EDGAR rather than about the board -- so each company is resolved again.
    for (const company of companiesToRestore(snapshot)) {
      void (async () => {
        try {
          await api.resolveCik(company.cik, company.ticker);
          await waitForEntity(company.cik, upsertEntity);
        } catch {
          // A company that will not resolve leaves its card reading
          // "ingesting", which is visible and recoverable by reloading.
        }
      })();
    }

    for (const filing of filingsToRestore(snapshot)) {
      void (async () => {
        try {
          const statements = await filings.current.fetch(
            filingKey(filing.cik, filing.form, filing.accession),
            (signal) => api.asFiled(filing.cik, filing.form, filing.accession, signal),
          );
          const owner = companiesToRestore(snapshot).find((company) => company.cik === filing.cik);
          setNodes((current) => {
            const row = statements.flatMap((statement) => {
              const id = statementNodeId(filing.cik, statement);
              const saved = snapshot.find(
                (node) => node.kind === "statement" && nodeIdOf(node, filing.cik) === id,
              );
              if (saved === undefined) return [];
              return [
                {
                  id,
                  type: "statement" as const,
                  position: { x: saved.x, y: saved.y },
                  width: saved.width ?? STATEMENT_WIDTH,
                  height: saved.height ?? DEFAULT_STATEMENT_HEIGHT,
                  data: {
                    cik: filing.cik,
                    // Taken from the company saved alongside, not left blank:
                    // the eyebrow is what identifies a panel once the board is
                    // zoomed out far enough that the table is texture, and an
                    // empty one makes a restored board a wall of grey
                    // rectangles.
                    company: owner?.name ?? "",
                    ticker: owner?.ticker ?? "",
                    statement,
                  },
                  dragHandle: ".drag-handle",
                },
              ];
            });
            return [
              ...current.filter((node) => !row.some((added) => added.id === node.id)),
              ...row,
            ] as BoardNode[];
          });
          setOpenAccessions((open) => new Set(open).add(filing.accession));
        } catch {
          // The filing stays off the board rather than half-drawn.
        }
      })();
    }
  }, [snapshot, setNodes, upsertEntity]);

  /**
   * Record the board.
   *
   * Deferred a moment because a drag reports a new position on every frame,
   * and writing storage sixty times a second to save the same arrangement
   * would be work for nothing. Nothing is lost by the delay: the board in
   * front of the reader is the truth, and this only follows it.
   */
  useEffect(() => {
    const timer = setTimeout(() => onSnapshot(toSnapshot(nodes)), 400);
    return () => clearTimeout(timer);
  }, [nodes, onSnapshot]);

  const empty = nodes.length === 0;

  const defaultEdgeOptions = useMemo(() => ({ style: { stroke: "#2b2b33", strokeWidth: 1 } }), []);

  return (
    <BoardActionsProvider value={actions}>
      <div ref={pane} className="relative h-full w-full">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          // React Flow would drop the node and leave the rest of the cascade
          // undone, so removal goes through the one handler that knows what
          // else depended on it.
          onNodesDelete={(deleted) => {
            for (const node of deleted) removeNode(node.id);
          }}
          nodeTypes={nodeTypes}
          defaultEdgeOptions={defaultEdgeOptions}
          nodesConnectable={false}
          minZoom={0.15}
          maxZoom={2}
          proOptions={{ hideAttribution: false }}
        >
          <Background variant={BackgroundVariant.Dots} gap={30} size={1} color="#1e1e24" />
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
            {/* Appears only once there is something to compare. A control that
                cannot do anything is chrome competing with the figures. */}
            {comparable >= 2 && (
              <button
                type="button"
                onClick={compareBoard}
                className="eyebrow rounded-full border border-hairline-strong bg-surface px-3 py-[5px] text-[9px] text-ink-muted transition hover:border-ink-faint hover:text-ink"
              >
                Compare {comparable} companies
              </button>
            )}
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

export function Board({ snapshot, onSnapshot }: BoardProps) {
  return (
    <ReactFlowProvider>
      <BoardInner snapshot={snapshot} onSnapshot={onSnapshot} />
    </ReactFlowProvider>
  );
}
