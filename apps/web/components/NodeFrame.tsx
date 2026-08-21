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
  onDoubleClick,
  children,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  action?: ReactNode;
  scale?: number;
  /** Double clicking the header fits the panel to its content. */
  onDoubleClick?: () => void;
  children: ReactNode;
}) {
  const far = scale > 1.15;
  const px = (base: number): CSSProperties => ({ fontSize: `${base * scale}px` });

  return (
    // Fills the node box, whose size react-flow is told up front rather than
    // left to measure -- see nodeSize.ts.
    <div className="panel panel-frame relative flex h-full w-full flex-col overflow-hidden rounded-xl">
      <header
        onDoubleClick={onDoubleClick}
        className="drag-handle flex cursor-grab items-start gap-3 border-b border-hairline active:cursor-grabbing"
        style={{ padding: `${12 * scale}px ${15 * scale}px ${11 * scale}px` }}
      >
        <div className="min-w-0 flex-1">
          {eyebrow && (
            <div className="eyebrow mb-[3px] truncate text-ink-faint" style={px(9.5)}>
              {eyebrow}
            </div>
          )}
          <div
            className="truncate font-semibold text-ink"
            style={{ ...px(13), letterSpacing: "-0.011em" }}
          >
            {title}
          </div>
          {/* Filing date and units are reference detail, not identity. Once the
              header is being magnified to stay legible there is no room for
              them, and keeping them would push the title out of the panel. */}
          {meta && !far && <div className="mt-[5px] text-[11px] text-ink-faint">{meta}</div>}
        </div>
        {!far && action}
      </header>
      {children}
    </div>
  );
}
