import "@testing-library/jest-dom/vitest";
import { beforeEach, vi } from "vitest";

beforeEach(() => {
  vi.clearAllMocks();
});

// jsdom has no layout engine and no ResizeObserver. @tanstack/react-virtual
// and the summary chart both measure elements, so without these stubs the
// table windows down to zero rows and the chart draws at zero width.
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
