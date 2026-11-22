/**
 * Shared harness for the scan.ts tests: fake timers drive the 250 ms poll,
 * and fetch is routed by URL. Call `useScanHarness()` once per test file.
 */
import type { Reply } from "./route.ts";

import { load, resetScan } from "../client/scan.ts";
import { resetStore, store } from "../client/store.ts";
import { callsTo, route as routeFetch } from "./route.ts";

export const FIRST = "2026-10-11T14:00:00Z";
export const SECOND = "2026-10-11T14:05:00Z";
export const PROGRESS = "/api/scan/progress";

export const fetchMock = vi.fn<typeof fetch>();

export function route(replies: Record<string, readonly Reply[]>): void {
  routeFetch(fetchMock, replies);
}

export function calls(url: string): number {
  return callsTo(fetchMock, url);
}

export function scanState(): ReturnType<typeof store.getState>["scan"] {
  return store.getState().scan;
}

export async function tick(ms = 250): Promise<void> {
  await vi.advanceTimersByTimeAsync(ms);
}

export async function start(): Promise<void> {
  void load();
  await tick(0);
}

export function useScanHarness(): void {
  beforeEach(() => {
    vi.useFakeTimers();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    resetScan();
    resetStore();
  });

  afterEach(() => {
    resetScan();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });
}
