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

describe("useScan polling", () => {
  it("does not poll when the first scan is not scanning", async () => {
    route({ "/api/scan": [respond(makeScan())] });
    const { result } = renderHook(() => useScan());
    await tick(2000);
    expect(result.current.state.kind).toBe("ready");
    expect(calls(PROGRESS)).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("shows a scanning 200 at once, polls every 250 ms, then swaps in the new scan", async () => {
    route({
      "/api/scan": [
        respond(makeScan({ generatedAt: FIRST, scanning: true })),
        respond(makeScan({ generatedAt: SECOND, host: "new", scanning: false })),
      ],
      [PROGRESS]: [
        respond(makeProgress({ generatedAt: FIRST, sourcesDone: 3 })),
        respond(makeProgress({ generatedAt: FIRST, sourcesDone: 14 })),
        respond(makeProgress({ generatedAt: SECOND, scanning: false, sourcesDone: 26 })),
      ],
    });
    const { result } = renderHook(() => useScan());
    await tick(0);
    expect(result.current.state).toMatchObject({ kind: "ready", refreshing: true });
    expect(calls(PROGRESS)).toBe(1);
    expect(result.current.progress?.sourcesDone).toBe(3);

    await tick();
    expect(calls(PROGRESS)).toBe(2);
    expect(result.current.progress?.sourcesDone).toBe(14);
    expect(calls("/api/scan")).toBe(1);

    await tick();
    expect(result.current.state).toMatchObject({ refreshing: false, scan: { host: "new" } });
    const polls = calls(PROGRESS);
    await tick(2000);
    expect(calls(PROGRESS)).toBe(polls);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("polls progress after a 202 and loads the scan when one appears", async () => {
    route({
      "/api/scan": [respond({ scanning: true }, 202), respond(makeScan({ generatedAt: FIRST }))],
      [PROGRESS]: [
        respond(makeProgress({ itemsFound: 10, sourcesDone: 1 })),
        respond(makeProgress({ itemsFound: 90, sourcesDone: 2 })),
        respond(makeProgress({ generatedAt: FIRST, scanning: false, sourcesDone: 26 })),
      ],
    });
    const { result } = renderHook(() => useScan());
    await tick(0);
    expect(result.current.state.kind).toBe("loading");
    expect(result.current.progress?.itemsFound).toBe(10);
    await tick();
    expect(result.current.state.kind).toBe("loading");
    expect(result.current.progress?.itemsFound).toBe(90);
    await tick();
    expect(result.current.state).toMatchObject({ kind: "ready", refreshing: false });
  });

  it("keeps polling when a 202 follows a progress that already names a scan", async () => {
    route({
      "/api/scan": [respond({ scanning: true }, 202), respond({ scanning: true }, 202), respond(makeScan())],
      [PROGRESS]: [respond(makeProgress({ generatedAt: FIRST }))],
    });
    const { result } = renderHook(() => useScan());
    await tick(0);
    await tick(500);
    expect(result.current.state.kind).toBe("ready");
  });

  it("rescan asks for refresh=1, keeps the old list, polls, then swaps", async () => {
    route({
      "/api/scan": [respond(makeScan({ generatedAt: FIRST }))],
      "/api/scan?refresh=1": [respond(makeScan({ generatedAt: FIRST, scanning: true }))],
      [PROGRESS]: [respond(makeProgress({ generatedAt: FIRST }))],
    });
    const { result } = renderHook(() => useScan());
    await tick(0);
    act(() => {
      result.current.rescan();
    });
    await tick(0);
    expect(calls("/api/scan?refresh=1")).toBe(1);
    expect(result.current.state).toMatchObject({ refreshing: true, scan: { host: "testhost" } });

    route({
      "/api/scan": [respond(makeScan({ generatedAt: SECOND, host: "again" }))],
      [PROGRESS]: [respond(makeProgress({ generatedAt: SECOND, scanning: false }))],
    });
    await tick();
    expect(result.current.state).toMatchObject({ refreshing: false, scan: { host: "again" } });
  });

  it("rescan in scan-file mode swaps the answer in without polling", async () => {
    route({
      "/api/scan": [respond(makeScan())],
      "/api/scan?refresh=1": [respond(makeScan({ host: "reread" }))],
    });
    const { result } = renderHook(() => useScan());
    await tick(0);
    act(() => {
      result.current.rescan();
    });
    await tick(1000);
    expect(result.current.state).toMatchObject({ refreshing: false, scan: { host: "reread" } });
    expect(calls(PROGRESS)).toBe(0);
  });

  it("rescan from an error with a 202 goes back to polling", async () => {
    route({
      "/api/scan": [() => Promise.reject(new Error("first"))],
      "/api/scan?refresh=1": [respond({ scanning: true }, 202)],
      [PROGRESS]: [respond(makeProgress({ sourcesDone: 5 }))],
    });
    const { result } = renderHook(() => useScan());
    await tick(0);
    expect(result.current.state.kind).toBe("error");
    act(() => {
      result.current.rescan();
    });
    await tick(0);
    expect(result.current.state.kind).toBe("loading");
    expect(result.current.progress?.sourcesDone).toBe(5);
  });

  it("shows a crashed rescan through the refresh error and stops polling", async () => {
    route({
      "/api/scan": [respond(makeScan({ generatedAt: FIRST, scanning: true }))],
      [PROGRESS]: [respond(makeProgress({ error: "scanner exploded", generatedAt: FIRST, scanning: false }))],
    });
    const { result } = renderHook(() => useScan());
    await tick(0);
    expect(result.current.state).toMatchObject({
      kind: "ready",
      refreshError: "scanner exploded",
      refreshing: false,
    });
    await tick(2000);
    expect(calls(PROGRESS)).toBe(1);
  });

  it("stops when progress says the scan ended without a newer result", async () => {
    route({
      "/api/scan": [respond(makeScan({ generatedAt: FIRST, scanning: true }))],
      [PROGRESS]: [respond(makeProgress({ generatedAt: FIRST, scanning: false }))],
    });
    const { result } = renderHook(() => useScan());
    await tick(0);
    await tick(2000);
    expect(calls(PROGRESS)).toBe(1);
    expect(vi.getTimerCount()).toBe(0);
    expect(result.current.state).toMatchObject({ kind: "ready" });
  });

  it("a progress error with no scan to show is a fatal error", async () => {
    route({
      "/api/scan": [respond({ scanning: true }, 202)],
      [PROGRESS]: [respond(makeProgress({ error: "boom", scanning: false }))],
    });
    const { result } = renderHook(() => useScan());
    await tick(0);
    expect(result.current.state).toEqual({ kind: "error", message: "boom" });
  });

  it("reports a failing progress request and stops", async () => {
    route({
      "/api/scan": [respond({ scanning: true }, 202)],
      [PROGRESS]: [respond({}, 500)],
    });
    const { result } = renderHook(() => useScan());
    await tick(0);
    expect(result.current.state).toEqual({ kind: "error", message: "HTTP 500 from /api/scan/progress" });
    expect(vi.getTimerCount()).toBe(0);
  });
});
