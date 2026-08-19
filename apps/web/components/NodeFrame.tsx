import type { CSSProperties, ReactNode } from "react";

/**
 * The panel shell every node shares.
 *
 * `drag-handle` is what react-flow grabs, so the body stays selectable: a
 * statement whose numbers cannot be copied is not much use.
 *
 * `scale` counter-scales the header so the node stays identifiable when the
 * board is zoomed out. The title is the one thing that must survive at any
 * distance -- a canvas of unlabelled grey rectangles is the failure mode this
 * exists to prevent -- so it is the last thing allowed to shrink.
 */
export function NodeFrame({
  eyebrow,
  title,
  meta,
  action,
  scale = 1,
  children,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  action?: ReactNode;
  scale?: number;
  children: ReactNode;
}) {
  const far = scale > 1.15;
  const px = (base: number): CSSProperties => ({ fontSize: `${base * scale}px` });

  return (
    // Fills the node box, whose size react-flow is told up front rather than
    // left to measure -- see statementNodeHeight.
    <div className="panel panel-frame relative flex h-full w-full flex-col overflow-hidden rounded-lg">
      <header
        className="drag-handle flex cursor-grab items-start gap-3 border-b border-hairline bg-raised active:cursor-grabbing"
        style={{ padding: `${11 * scale}px ${14 * scale}px` }}
      >
        <div className="min-w-0 flex-1">
          {eyebrow && (
            <div
              className="mb-1 truncate font-medium uppercase tracking-[0.14em] text-ink-faint"
              style={px(10)}
            >
              {eyebrow}
            </div>
          )}
          <div className="truncate font-semibold tracking-tight text-ink" style={px(13)}>
            {title}
          </div>
          {/* Filing date and units are reference detail, not identity. Once the
              header is being magnified to stay legible there is no room for
              them, and keeping them would push the title out of the panel. */}
          {meta && !far && <div className="mt-1 text-[11px] text-ink-muted">{meta}</div>}
        </div>
        {!far && action}
      </header>
      {children}
    </div>
  );
}
