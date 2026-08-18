import type { ReactNode } from "react";

/**
 * The glass shell every node shares.
 *
 * `drag-handle` is what react-flow grabs, so the body stays selectable: a
 * statement whose numbers cannot be copied is not much use.
 */
export function NodeFrame({
  eyebrow,
  title,
  meta,
  action,
  children,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    // Fills the node box, whose size react-flow is told up front rather than
    // left to measure -- see statementNodeHeight.
    <div className="glass glass-frame relative flex h-full w-full flex-col overflow-hidden rounded-xl">
      {/* Statements routinely run longer than the panel, and a hard edge mid-row
          reads as a rendering fault rather than as more content below. */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 h-10 bg-gradient-to-t from-surface to-transparent" />
      <header className="drag-handle flex cursor-grab items-start gap-3 border-b border-white/[0.07] px-4 py-3 active:cursor-grabbing">
        <div className="min-w-0 flex-1">
          {eyebrow && (
            <div className="mb-1 text-[10px] font-medium uppercase tracking-[0.14em] text-ink-faint">
              {eyebrow}
            </div>
          )}
          <div className="truncate text-[13px] font-semibold tracking-tight text-ink">{title}</div>
          {meta && <div className="mt-1 text-[11px] text-ink-muted">{meta}</div>}
        </div>
        {action}
      </header>
      {children}
    </div>
  );
}
