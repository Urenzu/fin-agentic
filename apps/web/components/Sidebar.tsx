"use client";

import { useEffect, useRef, useState } from "react";

import { RowMenu } from "./RowMenu";
import { ordered, tickersOf, type Canvas } from "@/lib/canvas";

/**
 * The canvases a reader keeps.
 *
 * Fixed to the left rather than floating over the board, because it is the one
 * piece of chrome that is not about the filing in front of you -- it is where
 * you are, and a panel that came and went would make the board feel like it
 * had moved. It collapses instead, which gives the whole width to the
 * statements without ever moving them.
 */
export function Sidebar({
  canvases,
  selected,
  onSelect,
  onCreate,
  onRename,
  onTogglePin,
  onRemove,
  onCollapse,
}: {
  canvases: Canvas[];
  selected: string;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onRename: (id: string, name: string) => void;
  onTogglePin: (id: string) => void;
  onRemove: (id: string) => void;
  onCollapse: () => void;
}) {
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<string | null>(null);

  // One ordering, split for display. `ordered` already puts pinned first, so
  // the headings describe the list rather than imposing a second sort on it.
  const visible = ordered(canvases, query);
  const pinned = visible.filter((canvas) => canvas.pinned);
  const rest = visible.filter((canvas) => !canvas.pinned);

  const row = (canvas: Canvas) => (
    <Row
      key={canvas.id}
      canvas={canvas}
      active={canvas.id === selected}
      editing={editing === canvas.id}
      onSelect={() => onSelect(canvas.id)}
      onStartRename={() => setEditing(canvas.id)}
      onRename={(name) => {
        onRename(canvas.id, name);
        setEditing(null);
      }}
      onCancelRename={() => setEditing(null)}
      onTogglePin={() => onTogglePin(canvas.id)}
      onRemove={() => onRemove(canvas.id)}
    />
  );

  return (
    <aside className="flex h-full w-[248px] flex-col border-r border-hairline bg-void">
      {/* Just the collapse control, pushed to the edge. A wordmark here would
          name the product to the one person who already knows what they
          opened, and it is the first thing the eye lands on. */}
      <div className="flex items-center justify-end px-3 pb-2 pt-3">
        <IconButton label="Hide the sidebar" onClick={onCollapse}>
          <path
            d="M7.5 2.5l-3.5 3.5 3.5 3.5"
            strokeWidth="1.4"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          />
        </IconButton>
      </div>

      <div className="flex flex-col gap-1.5 px-3">
        <div className="relative">
          <svg
            viewBox="0 0 12 12"
            aria-hidden
            className="pointer-events-none absolute left-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-ink-faint"
            stroke="currentColor"
            fill="none"
          >
            <circle cx="5" cy="5" r="3.2" strokeWidth="1.2" />
            <path d="M7.4 7.4L10 10" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search"
            aria-label="Search canvases"
            className="w-full rounded-lg border border-transparent bg-white/[0.04] py-[7px] pl-[30px] pr-2.5 text-[12px] text-ink outline-none transition placeholder:text-ink-faint hover:bg-white/[0.06] focus:border-hairline-strong focus:bg-surface"
          />
        </div>

        {/* A labelled row rather than a bare `+`: it is the one thing a reader
            with no canvases yet needs to find, and an icon makes them guess. */}
        <button
          type="button"
          onClick={onCreate}
          className="flex w-full items-center gap-2 rounded-lg px-2.5 py-[7px] text-left text-[12px] text-ink-muted transition hover:bg-white/[0.06] hover:text-ink"
        >
          <svg viewBox="0 0 12 12" aria-hidden className="h-3 w-3" stroke="currentColor">
            <path d="M6 2v8M2 6h8" strokeWidth="1.4" strokeLinecap="round" fill="none" />
          </svg>
          New canvas
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-2 pb-3 pt-2">
        {visible.length === 0 && (
          <p className="px-2.5 py-3 text-[11.5px] leading-relaxed text-ink-faint">
            {/* Says which of the two situations this is: an empty shelf reads
                very differently from a search that found nothing. */}
            {query.trim() === "" ? "No canvases yet." : `Nothing matches “${query.trim()}”.`}
          </p>
        )}

        {/* Headings only once there is a pinned canvas to head. With none, a
            lone "Recent" label over the whole list says nothing. */}
        {pinned.length > 0 && <Heading>Pinned</Heading>}
        {pinned.map(row)}
        {pinned.length > 0 && rest.length > 0 && <Heading>Recent</Heading>}
        {rest.map(row)}
      </div>
    </aside>
  );
}

/** The control that brings the sidebar back, shown only while it is away. */
export function SidebarHandle({ shown, onExpand }: { shown: boolean; onExpand: () => void }) {
  return (
    <button
      type="button"
      onClick={onExpand}
      aria-label="Show the sidebar"
      title="Show the sidebar"
      // Kept mounted so it can fade rather than blink, and held back until the
      // sidebar has finished sliding out of the space it appears in.
      inert={!shown}
      className={`panel absolute left-3 top-3 z-20 rounded-lg border border-hairline p-1.5 text-ink-faint transition-opacity duration-150 hover:border-hairline-strong hover:text-ink motion-reduce:duration-75 ${
        shown ? "opacity-100 delay-150" : "pointer-events-none opacity-0"
      }`}
    >
      <svg viewBox="0 0 12 12" aria-hidden className="h-3 w-3">
        <path
          d="M4.5 2.5l3.5 3.5-3.5 3.5"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </svg>
    </button>
  );
}

function Heading({ children }: { children: React.ReactNode }) {
  return (
    <p className="eyebrow px-2.5 pb-1 pt-2 text-[8.5px] text-ink-faint first:pt-0">{children}</p>
  );
}

function IconButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      className="rounded p-1 text-ink-faint transition hover:bg-white/[0.06] hover:text-ink"
    >
      <svg viewBox="0 0 12 12" aria-hidden className="h-3 w-3" stroke="currentColor">
        {children}
      </svg>
    </button>
  );
}

function Row({
  canvas,
  active,
  editing,
  onSelect,
  onStartRename,
  onRename,
  onCancelRename,
  onTogglePin,
  onRemove,
}: {
  canvas: Canvas;
  active: boolean;
  editing: boolean;
  onSelect: () => void;
  onStartRename: () => void;
  onRename: (name: string) => void;
  onCancelRename: () => void;
  onTogglePin: () => void;
  onRemove: () => void;
}) {
  const tickers = tickersOf(canvas);

  return (
    <div
      className={`group relative rounded-lg transition-colors ${
        active ? "bg-white/[0.07]" : "hover:bg-white/[0.035]"
      }`}
    >
      {/* The selected canvas gets a mark down its edge as well as a fill: at
          these contrasts a fill alone is easy to lose against a hover. */}
      <span
        aria-hidden
        className={`absolute left-0 top-1/2 h-4 w-[2px] -translate-y-1/2 rounded-full bg-ink transition-opacity ${
          active ? "opacity-100" : "opacity-0"
        }`}
      />

      {editing ? (
        <RenameField initial={canvas.name} onCommit={onRename} onCancel={onCancelRename} />
      ) : (
        <button
          type="button"
          onClick={onSelect}
          // Double click renames as well, which is the same gesture the panel
          // headers use and costs no pixels.
          onDoubleClick={onStartRename}
          className="block w-full py-[7px] pl-2.5 pr-8 text-left"
        >
          <span
            className={`block truncate text-[12.5px] ${active ? "text-ink" : "text-ink-muted"}`}
          >
            {canvas.name}
          </span>
          <span className="tnum mt-[1px] block truncate text-[10px] text-ink-faint">
            {/* What is actually on it, which is how a reader recognises a
                canvas they never got round to naming. */}
            {tickers.length > 0 ? tickers.join(" · ") : "Empty"}
          </span>
        </button>
      )}

      {!editing && (
        <div className="absolute right-1.5 top-1.5">
          <RowMenu
            label={`Actions for ${canvas.name}`}
            items={[
              { label: "Rename", onSelect: onStartRename },
              { label: canvas.pinned ? "Unpin" : "Pin to top", onSelect: onTogglePin },
              { label: "Delete", onSelect: onRemove, danger: true },
            ]}
          />
        </div>
      )}
    </div>
  );
}

function RenameField({
  initial,
  onCommit,
  onCancel,
}: {
  initial: string;
  onCommit: (name: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initial);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Selected rather than just focused: renaming usually means replacing the
    // default name, not appending to it.
    input.current?.select();
  }, []);

  return (
    <input
      ref={input}
      value={value}
      autoFocus
      onChange={(event) => setValue(event.target.value)}
      // Committing on blur means clicking away keeps the edit, which is what a
      // reader means by it far more often than discarding.
      onBlur={() => onCommit(value)}
      onKeyDown={(event) => {
        if (event.key === "Enter") onCommit(value);
        if (event.key === "Escape") onCancel();
      }}
      aria-label="Canvas name"
      className="w-full rounded-lg border border-hairline-strong bg-surface px-2.5 py-[7px] text-[12.5px] text-ink outline-none"
    />
  );
}
