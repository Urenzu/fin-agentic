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
  const visible = ordered(canvases, query);

  return (
    <aside className="flex h-full w-[232px] shrink-0 flex-col border-r border-hairline bg-void">
      <div className="flex items-center gap-1 px-3 pb-2 pt-3">
        <span className="eyebrow flex-1 text-[9px] text-ink-faint">Canvases</span>
        <IconButton label="New canvas" onClick={onCreate}>
          <path d="M6 2v8M2 6h8" strokeWidth="1.4" strokeLinecap="round" fill="none" />
        </IconButton>
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

      <div className="px-3 pb-2">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search canvases or tickers"
          aria-label="Search canvases"
          className="w-full rounded-lg border border-hairline bg-surface px-2.5 py-[6px] text-[11.5px] text-ink outline-none transition placeholder:text-ink-faint focus:border-hairline-strong"
        />
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-2 pb-3">
        {visible.length === 0 && (
          <p className="px-2 py-3 text-[11px] leading-relaxed text-ink-faint">
            {/* Says which of the two situations this is: an empty shelf reads
                very differently from a search that found nothing. */}
            {query.trim() === "" ? "No canvases yet." : `Nothing matches “${query.trim()}”.`}
          </p>
        )}

        {visible.map((canvas) => (
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
        ))}
      </div>
    </aside>
  );
}

/** The control that brings the sidebar back, shown only while it is away. */
export function SidebarHandle({ onExpand }: { onExpand: () => void }) {
  return (
    <button
      type="button"
      onClick={onExpand}
      aria-label="Show the sidebar"
      title="Show the sidebar"
      className="panel absolute left-3 top-3 z-20 rounded-lg border border-hairline p-1.5 text-ink-faint transition hover:border-hairline-strong hover:text-ink"
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
      className={`group relative rounded-lg transition ${
        active ? "bg-white/[0.06]" : "hover:bg-white/[0.035]"
      }`}
    >
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
          <span className="flex items-center gap-1.5">
            {canvas.pinned && (
              // A small mark rather than a filled control: pinned is a
              // property of the canvas, and the way to change it is the menu.
              <svg
                viewBox="0 0 12 12"
                aria-label="Pinned"
                role="img"
                className="h-[9px] w-[9px] shrink-0 text-ink-faint"
              >
                <path
                  d="M4.6 1.5h2.8l-.4 3 1.7 1.6H3.3L5 4.5l-.4-3M6 6.1V10.5"
                  stroke="currentColor"
                  strokeWidth="1.1"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  fill="currentColor"
                />
              </svg>
            )}
            <span className={`truncate text-[12px] ${active ? "text-ink" : "text-ink-muted"}`}>
              {canvas.name}
            </span>
          </span>
          <span className="eyebrow tnum mt-[2px] block truncate text-[8.5px] text-ink-faint">
            {/* What is actually on it, which is how a reader recognises a
                canvas they never got round to naming. */}
            {tickers.length > 0 ? tickers.join(" · ") : "empty"}
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
      className="w-full rounded-lg border border-hairline-strong bg-surface px-2.5 py-[7px] text-[12px] text-ink outline-none"
    />
  );
}
