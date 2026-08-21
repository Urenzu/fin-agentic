"use client";

import { createContext, useContext } from "react";

import type { FilingIndex, Registrant } from "@/lib/types";

/**
 * What a node may ask the board to do.
 *
 * Passed by context rather than through node data. React Flow treats `data` as
 * a value it may copy and compare, and putting callbacks there means every
 * board-level change produces new function identities on every node -- and a
 * node's data stops being the plain, inspectable description of what it shows.
 */
export type BoardActions = {
  /** Put a filing's statements on the board, or take them off again. */
  toggleFiling: (registrant: Registrant, filing: FilingIndex) => void;
  /**
   * Fetch a filing before it is asked for, on hover or on the list settling.
   *
   * Speculative and silent: a prefetch that is never used costs bandwidth, and
   * one that fails is reported only if the reader goes on to click.
   */
  prefetchFiling: (registrant: Registrant, filing: FilingIndex) => void;
  /** Accessions currently on the board, so the picker can show what is open. */
  openAccessions: ReadonlySet<string>;
  /** Accessions being fetched, so a slow filing does not look like a dead click. */
  pendingAccessions: ReadonlySet<string>;
  /**
   * Take a panel off the board, along with anything that depended on it.
   *
   * Removing a company also removes its statements and its column in any
   * comparison -- see lib/removal.ts, where that judgement lives.
   */
  removeNode: (id: string) => void;
};

const BoardActionsContext = createContext<BoardActions | null>(null);

export const BoardActionsProvider = BoardActionsContext.Provider;

export function useBoardActions(): BoardActions {
  const actions = useContext(BoardActionsContext);
  if (actions === null) {
    throw new Error("useBoardActions must be used inside the board");
  }
  return actions;
}
