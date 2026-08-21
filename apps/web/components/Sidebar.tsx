"use client";

import { useEffect, useRef, useState } from "react";

import { ordered, tickersOf, type Canvas } from "@/lib/canvas";

/**
 * The canvases a reader keeps.
 *
 * Fixed to the left rather than floating over the board, because it is the one
 * piece of chrome that is not about the filing in front of you -- it is where
 * you are, and a panel that comes and goes would make the board feel like it
 * had moved.
 */
export function Sidebar({
  canvases,
  selected,
  onSelect,
  onCreate,
  onRename,
  onTogglePin,
  onRemove,
}: {
  canvases: Canvas[];
  selected: string;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onRename: (id: string, name: string) => void;
  onTogglePin: (id: string) => void;
  onRemove: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const visible = ordered(canvases, query);

  return (
    <aside className="flex h-full w-[232px] shrink-0 flex-col border-r border-hairline bg-void">
      <div className="flex items-center gap-2 px-3 pb-2 pt-3">
        <span className="eyebrow flex-1 text-[9px] text-ink-faint">Canvases</span>
        <button
          type="button"
          onClick={onCreate}
          title="New canvas"
          aria-label="New canvas"
          className="rounded p-1 text-ink-faint transition hover:bg-white/[0.06] hover:text-ink"
        >
          <svg viewBox="0 0 12 12" aria-hidden className="h-3 w-3">
            <path
              d="M6 2v8M2 6h8"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
              fill="none"
            />
          </svg>
        </button>
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
          // Double click to rename, so renaming costs no pixels and lands
          // where the reader already is -- the same gesture the panel headers
          // use to fit themselves.
          onDoubleClick={onStartRename}
          className="block w-full px-2.5 py-[7px] pr-14 text-left"
        >
          <span className={`block truncate text-[12px] ${active ? "text-ink" : "text-ink-muted"}`}>
            {canvas.name}
          </span>
          <span className="eyebrow tnum mt-[2px] block truncate text-[8.5px] text-ink-faint">
            {/* What is actually on it, which is how a reader recognises a
                canvas they never got round to naming. */}
            {tickers.length > 0 ? tickers.join(" · ") : "empty"}
          </span>
        </button>
      )}

      {!editing && (
        <div className="absolute right-1.5 top-1.5 flex items-center gap-0.5">
          <button
            type="button"
            onClick={onTogglePin}
            aria-label={canvas.pinned ? "Unpin this canvas" : "Pin this canvas"}
            title={canvas.pinned ? "Unpin this canvas" : "Pin this canvas"}
            // A pinned canvas keeps its mark visible; an unpinned one only
            // offers the control when the row is under the pointer, so a list
            // of twenty is a list of names rather than forty small icons.
            className={`rounded p-1 transition hover:bg-white/[0.08] hover:text-ink ${
              canvas.pinned
                ? "text-ink"
                : "text-ink-faint opacity-0 focus-visible:opacity-100 group-hover:opacity-100"
            }`}
          >
            <svg viewBox="0 0 12 12" aria-hidden className="h-[11px] w-[11px]">
              <path
                d="M4.6 1.5h2.8l-.4 3 1.7 1.6H5.6m-1.9 0H2.3L4 4.5l-.4-3M6 6.1V10.5"
                stroke="currentColor"
                strokeWidth="1.1"
                strokeLinejoin="round"
                strokeLinecap="round"
                fill={canvas.pinned ? "currentColor" : "none"}
              />
            </svg>
          </button>
          <button
            type="button"
            onClick={onRemove}
            aria-label="Delete this canvas"
            title="Delete this canvas"
            className="rounded p-1 text-ink-faint opacity-0 transition hover:bg-white/[0.08] hover:text-negative focus-visible:opacity-100 group-hover:opacity-100"
          >
            <svg viewBox="0 0 12 12" aria-hidden className="h-[11px] w-[11px]">
              <path
                d="M2.5 2.5l7 7M9.5 2.5l-7 7"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinecap="round"
                fill="none"
              />
            </svg>
          </button>
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
