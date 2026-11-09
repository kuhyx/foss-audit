/**
 * Reports an element's content width so SVG can be drawn at real pixel size.
 * Observe an inner box (`.chart`), never a `display: contents` host.
 *
 * @returns The stop function.
 */
export function observeWidth(element: Element, onWidth: (width: number) => void): () => void {
  const observer = new ResizeObserver((entries) => {
    const entry = entries[0];
    if (entry !== undefined) onWidth(Math.floor(entry.contentRect.width));
  });
  observer.observe(element);
  return (): void => {
    observer.disconnect();
  };
}
