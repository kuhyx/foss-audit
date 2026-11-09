import { observeWidth } from "./observe-width.ts";

type Callback = (entries: { contentRect: { width: number } }[]) => void;

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

describe("observeWidth", () => {
  it("reports the observed width, floored, and disconnects when stopped", () => {
    const widths: number[] = [];
    const stop = observeWidth(document.createElement("div"), (width) => {
      widths.push(width);
    });
    observed.callback([{ contentRect: { width: 640.7 } }]);
    observed.callback([]);
    expect(widths).toEqual([640]);
    stop();
    expect(disconnect).toHaveBeenCalledOnce();
  });
});
