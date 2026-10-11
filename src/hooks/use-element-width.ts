/**
 * Tracks an element's content width, for SVG drawn at real pixel size.
 *
 * The chart is drawn in device pixels rather than a scaled viewBox so that
 * the 2px segment gaps and 4px rounded ends stay exactly 2px and 4px at every
 * window width, instead of stretching with the container.
 */
import { useEffect, useState } from "react";

export function useElementWidth(element: HTMLElement | null): number {
  const [width, setWidth] = useState(0);

  useEffect(() => {
    if (element === null) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry !== undefined) setWidth(Math.floor(entry.contentRect.width));
    });
    observer.observe(element);
    return (): void => {
      observer.disconnect();
    };
  }, [element]);

  return width;
}
