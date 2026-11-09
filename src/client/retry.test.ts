import { makeScan } from "../test/fixtures.ts";
import { RETRY_DELAYS_MS, startRetry } from "./retry.ts";
import { resetStore, store } from "./store.ts";

function fail(message = "HTTP 502 from /api/scan"): void {
  store.set({ scan: { kind: "error", message } });
}

const handle = { stop: (): void => {} };

beforeEach(() => {
  vi.useFakeTimers();
  resetStore();
});

afterEach(() => {
  handle.stop();
  vi.useRealTimers();
});

describe("startRetry", () => {
  it("backs off 1, 2, 4 s and then holds at the cap until the load succeeds", () => {
    const load = vi.fn(() => {
      fail();
      return Promise.resolve();
    });
    handle.stop = startRetry(load);
    fail();
    const waits: number[] = [];
    for (let attempt = 0; attempt < 5; attempt += 1) {
      const before = Date.now();
      vi.advanceTimersToNextTimer();
      waits.push(Date.now() - before);
    }
    expect(waits).toEqual([1000, 2000, 4000, 5000, 5000]);
    expect(load).toHaveBeenCalledTimes(5);
    expect(Math.max(...RETRY_DELAYS_MS)).toBe(5000);
  });

  it("stops retrying once the scan is ready and starts over from 1 s after the next failure", () => {
    const load = vi.fn(() => Promise.resolve());
    handle.stop = startRetry(load);
    fail();
    vi.advanceTimersByTime(1000);
    fail();
    vi.advanceTimersByTime(2000);
    expect(load).toHaveBeenCalledTimes(2);
    store.set({ scan: { kind: "ready", refreshError: null, refreshing: false, scan: makeScan() } });
    expect(vi.getTimerCount()).toBe(0);
    store.set({ scan: { kind: "loading" } });
    fail();
    vi.advanceTimersByTime(1000);
    expect(load).toHaveBeenCalledTimes(3);
  });

  it("keeps one timer pending, ignores unrelated updates, and stop() cancels it", () => {
    const load = vi.fn(() => Promise.resolve());
    handle.stop = startRetry(load);
    fail("a");
    fail("b");
    store.set({ helpOpen: true });
    expect(vi.getTimerCount()).toBe(1);
    handle.stop();
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(10_000);
    expect(load).not.toHaveBeenCalled();
  });
});
