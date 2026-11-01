/**
 * The backend scans in the background; the hook watches /api/scan/progress.
 * Fake timers drive the 250 ms poll, and fetch is routed by URL.
 */
import { act, renderHook } from "@testing-library/react";

import type { Reply } from "../test/route.ts";

import { makeProgress, makeScan } from "../test/fixtures.ts";
import { callsTo, respond, route as routeFetch } from "../test/route.ts";
import { useScan } from "./use-scan.ts";

const FIRST = "2026-10-11T14:00:00Z";
const SECOND = "2026-10-11T14:05:00Z";
const PROGRESS = "/api/scan/progress";

const fetchMock = vi.fn<typeof fetch>();

function route(replies: Record<string, readonly Reply[]>): void {
  routeFetch(fetchMock, replies);
}

function calls(url: string): number {
  return callsTo(fetchMock, url);
}

async function tick(ms = 250): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useScan overlap and unmount", () => {
  it("never overlaps polls: waits for a slow progress reply", async () => {
    const slow = Promise.withResolvers<Response>();
    route({
      "/api/scan": [respond(makeScan({ generatedAt: FIRST, scanning: true }))],
      [PROGRESS]: [() => slow.promise],
    });
    renderHook(() => useScan());
    await tick(2000);
    expect(calls(PROGRESS)).toBe(1);
    route({
      "/api/scan": [respond(makeScan({ generatedAt: FIRST, scanning: true }))],
      [PROGRESS]: [respond(makeProgress({ generatedAt: FIRST }))],
    });
    slow.resolve(respond(makeProgress({ generatedAt: FIRST })));
    await tick();
    expect(calls(PROGRESS)).toBe(2);
  });

  it("clears its timer on unmount and ignores a late progress reply", async () => {
    const late = Promise.withResolvers<Response>();
    route({
      "/api/scan": [respond(makeScan({ generatedAt: FIRST, scanning: true }))],
      [PROGRESS]: [respond(makeProgress({ generatedAt: FIRST })), () => late.promise],
    });
    const { result, unmount } = renderHook(() => useScan());
    await tick(0);
    await tick();
    expect(calls(PROGRESS)).toBe(2);
    unmount();
    late.resolve(respond(makeProgress({ generatedAt: SECOND, scanning: false })));
    await tick(2000);
    expect(calls(PROGRESS)).toBe(2);
    expect(calls("/api/scan")).toBe(1);
    expect(vi.getTimerCount()).toBe(0);
    expect(result.current.progress?.generatedAt).toBe(FIRST);
  });

  it("clears its timer on unmount while waiting for the next tick", async () => {
    route({
      "/api/scan": [respond(makeScan({ generatedAt: FIRST, scanning: true }))],
      [PROGRESS]: [respond(makeProgress({ generatedAt: FIRST }))],
    });
    const { unmount } = renderHook(() => useScan());
    await tick(0);
    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("ignores a progress failure that lands after unmount", async () => {
    const lateFail = Promise.withResolvers<Response>();
    route({
      "/api/scan": [respond(makeScan({ generatedAt: FIRST, scanning: true }))],
      [PROGRESS]: [() => lateFail.promise],
    });
    const { result, unmount } = renderHook(() => useScan());
    await tick(0);
    unmount();
    lateFail.reject(new Error("late"));
    await tick(1000);
    expect(result.current.state).toMatchObject({ kind: "ready", refreshError: null });
  });

  it("ignores a scan refetch that lands after unmount", async () => {
    const lateScan = Promise.withResolvers<Response>();
    route({
      "/api/scan": [respond(makeScan({ generatedAt: FIRST, scanning: true })), () => lateScan.promise],
      [PROGRESS]: [respond(makeProgress({ generatedAt: SECOND, scanning: false }))],
    });
    const { result, unmount } = renderHook(() => useScan());
    await tick(0);
    unmount();
    lateScan.resolve(respond(makeScan({ generatedAt: SECOND, host: "late" })));
    await tick(1000);
    expect(result.current.state).toMatchObject({ scan: { host: "testhost" } });
  });
});
