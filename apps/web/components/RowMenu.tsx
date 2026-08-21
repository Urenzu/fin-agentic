"use client";

import { useEffect, useId, useRef, useState } from "react";

export type MenuItem = {
  label: string;
  onSelect: () => void;
  /** Marks a destructive action, which gets the only colour in the menu. */
  danger?: boolean;
};

/**
 * The actions on a sidebar row, behind one control.
 *
 * Two icons per row -- a pin and a cross -- meant a list of twenty canvases
 * carried forty small glyphs competing with the names, and neither said what
 * it did without being hovered. One dot control opens a list of words, which
 * needs no legend.
 */
export function RowMenu({ items, label }: { items: MenuItem[]; label: string }) {
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: PointerEvent) => {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };

    // Capture, so a click that also does something else -- selecting another
    // row, for instance -- still closes this first.
    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={container} className="relative">
      <button
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        title={label}
        onClick={(event) => {
          // The row underneath selects a canvas; opening its menu is not
          // choosing it.
          event.stopPropagation();
          setOpen((was) => !was);
        }}
        className={`rounded p-1 transition hover:bg-white/[0.08] hover:text-ink ${
          // Held open the control stays visible, or it would vanish under the
          // menu it opened.
          open
            ? "bg-white/[0.08] text-ink"
            : "text-ink-faint opacity-0 focus-visible:opacity-100 group-hover:opacity-100"
        }`}
      >
        <svg viewBox="0 0 12 12" aria-hidden className="h-[13px] w-[13px]">
          <circle cx="2.5" cy="6" r="1.05" fill="currentColor" />
          <circle cx="6" cy="6" r="1.05" fill="currentColor" />
          <circle cx="9.5" cy="6" r="1.05" fill="currentColor" />
        </svg>
      </button>

      {open && (
        <div
          id={id}
          role="menu"
          className="panel absolute right-0 top-full z-30 mt-1 w-[148px] overflow-hidden rounded-lg border border-hairline-strong py-1 shadow-lg shadow-black/40"
        >
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              onClick={(event) => {
                event.stopPropagation();
                setOpen(false);
                item.onSelect();
              }}
              className={`block w-full px-3 py-[6px] text-left text-[11.5px] transition hover:bg-white/[0.06] ${
                item.danger
                  ? "text-negative/90 hover:text-negative"
                  : "text-ink-muted hover:text-ink"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
