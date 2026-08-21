"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Board } from "./Board";
import { Sidebar } from "./Sidebar";
import {
  createCanvas,
  remove,
  rename,
  togglePin,
  update,
  type Canvas,
  type CanvasNode,
} from "@/lib/canvas";
import { initialState, load, save, type StoredState } from "@/lib/canvasStore";

/**
 * The sidebar and the board it is choosing between.
 *
 * Canvas state lives here rather than in the board, because the board is about
 * one arrangement and this is about which arrangement. Keeping them apart is
 * also what makes the board remountable: choosing a canvas replaces it
 * outright rather than asking it to unpick the last one.
 */
export function Workspace() {
  // Deliberately not read during render. The server has no `localStorage`, so
  // reading it while rendering would produce markup that cannot match what the
  // browser then draws -- the first paint is the empty state either way.
  const [state, setState] = useState<StoredState>(() => initialState());
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setState(load());
    setReady(true);
  }, []);

  useEffect(() => {
    if (ready) save(state);
  }, [state, ready]);

  const { canvases, selected } = state;
  const current = useMemo(
    () => canvases.find((canvas) => canvas.id === selected) ?? canvases[0],
    [canvases, selected],
  );

  const onSnapshot = useCallback((nodes: CanvasNode[]) => {
    setState((previous) => {
      const canvas = previous.canvases.find((c) => c.id === previous.selected);
      if (canvas === undefined) return previous;
      // A board that has not actually changed must not bump the canvas up
      // the list: the snapshot is recomputed on every render, and treating
      // each one as an edit would reshuffle the sidebar continuously.
      if (JSON.stringify(canvas.nodes) === JSON.stringify(nodes)) return previous;
      return {
        ...previous,
        canvases: update(previous.canvases, previous.selected, { nodes }),
      };
    });
  }, []);

  const onCreate = useCallback(() => {
    setState((previous) => {
      const fresh = createCanvas(previous.canvases);
      return { canvases: [...previous.canvases, fresh], selected: fresh.id };
    });
  }, []);

  const onRemove = useCallback((id: string) => {
    setState((previous) => {
      const { canvases: kept, selected: next } = remove(previous.canvases, id);
      return { canvases: kept, selected: next };
    });
  }, []);

  if (current === undefined) return null;

  return (
    <div className="flex h-full w-full">
      <Sidebar
        canvases={canvases}
        selected={current.id}
        onSelect={(id) => setState((previous) => ({ ...previous, selected: id }))}
        onCreate={onCreate}
        onRename={(id, name) =>
          setState((previous) => ({ ...previous, canvases: rename(previous.canvases, id, name) }))
        }
        onTogglePin={(id) =>
          setState((previous) => ({
            ...previous,
            canvases: togglePin(previous.canvases, id),
          }))
        }
        onRemove={onRemove}
      />
      <div className="relative min-w-0 flex-1">
        {/* Keyed on the canvas, so choosing one builds a fresh board rather
            than asking the old one to unpick itself. */}
        <Board key={current.id} snapshot={current.nodes} onSnapshot={onSnapshot} />
      </div>
    </div>
  );
}

export type { Canvas };
