import { act, renderHook } from "@testing-library/react";

import { useElementWidth } from "./use-element-width.ts";

type Callback = (entries: { contentRect: { width: number } }[]) => void;

// The observer the hook created, so the test can push widths through it.
const observed: { callback: Callback } = { callback: () => {} };
const disconnect = vi.fn();

class FakeObserver {
  constructor(callback: Callback) {
    observed.callback = callback;
  }
  disconnect(): void {
    disconnect();
  }
  observe(): void {
    // Width is pushed by the test through `callback`.
  }
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", FakeObserver);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useElementWidth", () => {
  it("is 0 without an element", () => {
    const { result } = renderHook(() => useElementWidth(null));
    expect(result.current).toBe(0);
  });

  it("tracks the observed width, floored, and disconnects on unmount", () => {
    const element = document.createElement("div");
    const { result, unmount } = renderHook(() => useElementWidth(element));
    act(() => {
      observed.callback([{ contentRect: { width: 640.7 } }]);
    });
    expect(result.current).toBe(640);
    act(() => {
      observed.callback([]);
    });
    expect(result.current).toBe(640);
    unmount();
    expect(disconnect).toHaveBeenCalledOnce();
  });
});
