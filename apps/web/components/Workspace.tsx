"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Board } from "./Board";
import { Sidebar, SidebarHandle } from "./Sidebar";
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
      return { ...previous, canvases: [...previous.canvases, fresh], selected: fresh.id };
    });
  }, []);

  const onRemove = useCallback((id: string) => {
    setState((previous) => {
      const { canvases: kept, selected: next } = remove(previous.canvases, id);
      return { ...previous, canvases: kept, selected: next };
    });
  }, []);

  if (current === undefined) return null;

  const setSidebar = (sidebar: boolean) => setState((previous) => ({ ...previous, sidebar }));

  return (
    <div className="flex h-full w-full">
      {/* The sidebar slides rather than vanishing: it is the one thing on
          screen that says where you are, and having it blink out makes the
          board look like it reloaded. Held at its full width inside a wrapper
          that shrinks, so the rows keep their layout instead of reflowing
          narrower and narrower on the way out. `inert` because a control
          nobody can see must not still be reachable by tab. */}
      <div
        inert={!state.sidebar}
        className={`h-full shrink-0 overflow-hidden ${
          // Not on the first paint: the server renders with the sidebar
          // showing, and a stored preference to hide it would otherwise
          // animate shut in front of the reader every time they load.
          // Shortened rather than dropped under reduced motion: sliding is
          // what tells the reader the sidebar went somewhere it can come back
          // from, and a 200ms width change is not the kind of movement that
          // setting is protecting anyone from.
          ready ? "transition-[width] duration-200 ease-out motion-reduce:duration-75" : ""
        } ${state.sidebar ? "w-[248px]" : "w-0"}`}
      >
        <Sidebar
          canvases={canvases}
          selected={current.id}
          onSelect={(id) => setState((previous) => ({ ...previous, selected: id }))}
          onCreate={onCreate}
          onRename={(id, name) =>
            setState((previous) => ({
              ...previous,
              canvases: rename(previous.canvases, id, name),
            }))
          }
          onTogglePin={(id) =>
            setState((previous) => ({
              ...previous,
              canvases: togglePin(previous.canvases, id),
            }))
          }
          onRemove={onRemove}
          onCollapse={() => setSidebar(false)}
        />
      </div>
      <div className="relative min-w-0 flex-1">
        <SidebarHandle shown={!state.sidebar} onExpand={() => setSidebar(true)} />
        {/* Keyed on the canvas, so choosing one builds a fresh board rather
            than asking the old one to unpick itself. */}
        <Board key={current.id} snapshot={current.nodes} onSnapshot={onSnapshot} />
      </div>
    </div>
  );
}

export type { Canvas };
