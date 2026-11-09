// Table window: a sticky header one row tall, then `count * ROW_HEIGHT` of body, mounted near the viewport only.
export const ROW_HEIGHT = 40;
export const OVERSCAN = 12;

export interface RowRange {
  readonly end: number;
  readonly start: number;
}

function bodyViewport(viewportHeight: number): number {
  return Math.max(0, viewportHeight - ROW_HEIGHT);
}

export function visibleRange(scrollTop: number, viewportHeight: number, count: number): RowRange {
  const top = Math.max(0, scrollTop);
  const start = Math.floor(top / ROW_HEIGHT) - OVERSCAN;
  const end = Math.ceil((top + bodyViewport(viewportHeight)) / ROW_HEIGHT) + OVERSCAN;
  return { end: Math.min(count, end), start: Math.min(count, Math.max(0, start)) };
}

export function scrollTopToReveal(index: number, scrollTop: number, viewportHeight: number): number {
  const rowTop = index * ROW_HEIGHT;
  if (rowTop < scrollTop) return rowTop;
  const viewport = bodyViewport(viewportHeight);
  const rowBottom = rowTop + ROW_HEIGHT;
  return rowBottom > scrollTop + viewport ? rowBottom - viewport : scrollTop;
}

export type ArrowKey = "ArrowDown" | "ArrowUp";

// With nothing current (-1), Down starts at the first row and Up at the last.
export function arrowTarget(current: number, count: number, key: ArrowKey): number {
  const isDown = key === "ArrowDown";
  if (current === -1) return isDown ? 0 : count - 1;
  return Math.min(count - 1, Math.max(0, current + (isDown ? 1 : -1)));
}
