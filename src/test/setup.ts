import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, vi } from "vitest";

import { invalidateRemoveCache } from "../client/remove-api.ts";

beforeEach(() => {
  vi.clearAllMocks();
  invalidateRemoveCache();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// jsdom has no layout engine and no ResizeObserver. The table and the summary
// chart both measure elements, so without these stubs the table windows down
// to zero rows and the chart draws at zero width.
//
// The numbers are fictional but consistent: an 800px-tall, 1200px-wide
// scroller over 40px rows (ROW_HEIGHT in items-table.tsx).
class ResizeObserverStub implements ResizeObserver {
  disconnect(): void {
    // Nothing is ever observed in jsdom, so nothing to tear down.
  }
  observe(): void {
    // Inert: sizes come from the stubs below.
  }
  unobserve(): void {
    // Inert.
  }
}

Reflect.set(globalThis, "ResizeObserver", ResizeObserverStub);

const VIEWPORT_HEIGHT = 800;
const VIEWPORT_WIDTH = 1200;
const ROW_HEIGHT = 40;

function heightOf(element: Element): number {
  return element.classList.contains("table-scroll") ? VIEWPORT_HEIGHT : ROW_HEIGHT;
}

// Absent in `@vitest-environment node` files (Astro container tests).
if (typeof HTMLElement !== "undefined") {
  Object.defineProperties(HTMLElement.prototype, {
    clientHeight: { configurable: true, get: (): number => VIEWPORT_HEIGHT },
    clientWidth: { configurable: true, get: (): number => VIEWPORT_WIDTH },
    offsetHeight: {
      configurable: true,
      get(this: HTMLElement): number {
        return heightOf(this);
      },
    },
    offsetWidth: { configurable: true, get: (): number => VIEWPORT_WIDTH },
    scrollTop: { configurable: true, get: (): number => 0, set: (): void => {} },
  });
}

// jsdom has no Clipboard API; tests spy on writeText.
Object.defineProperty(navigator, "clipboard", {
  configurable: true,
  value: { readText: (): Promise<string> => Promise.resolve(""), writeText: (): Promise<void> => Promise.resolve() },
});
