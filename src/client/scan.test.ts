/**
 * The backend scans in the background; scan.ts watches /api/scan/progress.
 * Fake timers drive the 250 ms poll, and fetch is routed by URL.
 */
import type { Reply } from "../test/route.ts";

import { makeProgress, makeScan } from "../test/fixtures.ts";
import { callsTo, respond, route as routeFetch } from "../test/route.ts";
import { load, refresh, resetScan } from "./scan.ts";
import { resetStore, store } from "./store.ts";

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

function scanState(): ReturnType<typeof store.getState>["scan"] {
  return store.getState().scan;
}

async function tick(ms = 250): Promise<void> {
  await vi.advanceTimersByTimeAsync(ms);
}

async function start(): Promise<void> {
  void load();
  await tick(0);
}

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

describe("load", () => {
  it("loads and validates /api/scan", async () => {
    route({ "/api/scan": [respond(makeScan())] });
    expect(scanState().kind).toBe("loading");
    await start();
    expect(scanState().kind).toBe("ready");
    expect(fetchMock).toHaveBeenCalledWith("/api/scan");
  });

  it("reports an HTTP error", async () => {
    route({ "/api/scan": [respond({}, 500)] });
    await start();
    expect(scanState()).toEqual({ kind: "error", message: "HTTP 500 from /api/scan" });
  });

  it("reports a schema failure with its path", async () => {
    route({ "/api/scan": [respond({ ...makeScan(), host: 1 })] });
    await start();
    const state = scanState();
    expect(state.kind === "error" && state.message).toContain('"host"');
  });

  it("stringifies a non-Error rejection", async () => {
    // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors -- a non-Error rejection is the case under test
    route({ "/api/scan": [() => Promise.reject("offline")] });
    await start();
    expect(scanState()).toEqual({ kind: "error", message: "offline" });
  });
});

describe("refresh", () => {
  it("asks for refresh=1 and keeps the old scan visible meanwhile", async () => {
    route({ "/api/scan": [respond(makeScan())] });
    await start();
    const pending = Promise.withResolvers<Response>();
    route({ "/api/scan?refresh=1": [() => pending.promise] });
    refresh();
    expect(scanState()).toMatchObject({ kind: "ready", refreshing: true });
    expect(fetchMock).toHaveBeenLastCalledWith("/api/scan?refresh=1");
    pending.resolve(respond(makeScan({ host: "new" })));
    await tick(0);
    expect(scanState()).toMatchObject({ refreshing: false, scan: { host: "new" } });
  });

  it("keeps the last scan and records the error when a rescan fails", async () => {
    route({ "/api/scan": [respond(makeScan())] });
    await start();
    route({ "/api/scan?refresh=1": [() => Promise.reject(new Error("boom"))] });
    refresh();
    await tick(0);
    expect(scanState()).toMatchObject({ kind: "ready", refreshError: "boom", refreshing: false });
  });

  it("falls back to loading, then error, when rescanning from an error", async () => {
    route({ "/api/scan": [() => Promise.reject(new Error("first"))] });
    await start();
    expect(scanState().kind).toBe("error");
    route({ "/api/scan?refresh=1": [() => Promise.reject(new Error("second"))] });
    refresh();
    expect(scanState().kind).toBe("loading");
    await tick(0);
    expect(scanState()).toEqual({ kind: "error", message: "second" });
  });

  it("swaps the answer in without polling in scan-file mode", async () => {
    route({ "/api/scan": [respond(makeScan())], "/api/scan?refresh=1": [respond(makeScan({ host: "reread" }))] });
    await start();
    refresh();
    await tick(1000);
    expect(scanState()).toMatchObject({ refreshing: false, scan: { host: "reread" } });
    expect(calls(PROGRESS)).toBe(0);
  });

  it("polls, keeps the old list, then swaps", async () => {
    route({
      "/api/scan": [respond(makeScan({ generatedAt: FIRST }))],
      "/api/scan?refresh=1": [respond(makeScan({ generatedAt: FIRST, scanning: true }))],
      [PROGRESS]: [respond(makeProgress({ generatedAt: FIRST }))],
    });
    await start();
    refresh();
    await tick(0);
    expect(calls("/api/scan?refresh=1")).toBe(1);
    expect(scanState()).toMatchObject({ refreshing: true, scan: { host: "testhost" } });
    route({
      "/api/scan": [respond(makeScan({ generatedAt: SECOND, host: "again" }))],
      [PROGRESS]: [respond(makeProgress({ generatedAt: SECOND, scanning: false }))],
    });
    await tick();
    expect(scanState()).toMatchObject({ refreshing: false, scan: { host: "again" } });
  });

  it("goes back to polling when rescanning from an error with a 202", async () => {
    route({
      "/api/scan": [() => Promise.reject(new Error("first"))],
      "/api/scan?refresh=1": [respond({ scanning: true }, 202)],
      [PROGRESS]: [respond(makeProgress({ sourcesDone: 5 }))],
    });
    await start();
    expect(scanState().kind).toBe("error");
    refresh();
    await tick(0);
    expect(scanState().kind).toBe("loading");
    expect(store.getState().progress?.sourcesDone).toBe(5);
  });
});

describe("polling", () => {
  it("does not poll when the first scan is not scanning", async () => {
    route({ "/api/scan": [respond(makeScan())] });
    await start();
    await tick(2000);
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
    await start();
    expect(scanState()).toMatchObject({ kind: "ready", refreshing: true });
    expect(calls(PROGRESS)).toBe(1);
    expect(store.getState().progress?.sourcesDone).toBe(3);
    await tick();
    expect(calls(PROGRESS)).toBe(2);
    expect(store.getState().progress?.sourcesDone).toBe(14);
    expect(calls("/api/scan")).toBe(1);
    await tick();
    expect(scanState()).toMatchObject({ refreshing: false, scan: { host: "new" } });
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
    await start();
    expect(scanState().kind).toBe("loading");
    expect(store.getState().progress?.itemsFound).toBe(10);
    await tick();
    expect(scanState().kind).toBe("loading");
    expect(store.getState().progress?.itemsFound).toBe(90);
    await tick();
    expect(scanState()).toMatchObject({ kind: "ready", refreshing: false });
  });

  it("keeps polling when a 202 follows a progress that already names a scan", async () => {
    route({
      "/api/scan": [respond({ scanning: true }, 202), respond({ scanning: true }, 202), respond(makeScan())],
      [PROGRESS]: [respond(makeProgress({ generatedAt: FIRST }))],
    });
    await start();
    await tick(500);
    expect(scanState().kind).toBe("ready");
  });

  it("shows a crashed rescan through the refresh error and stops polling", async () => {
    route({
      "/api/scan": [respond(makeScan({ generatedAt: FIRST, scanning: true }))],
      [PROGRESS]: [respond(makeProgress({ error: "scanner exploded", generatedAt: FIRST, scanning: false }))],
    });
    await start();
    expect(scanState()).toMatchObject({ kind: "ready", refreshError: "scanner exploded", refreshing: false });
    await tick(2000);
    expect(calls(PROGRESS)).toBe(1);
  });

  it("stops when progress says the scan ended without a newer result", async () => {
    route({
      "/api/scan": [respond(makeScan({ generatedAt: FIRST, scanning: true }))],
      [PROGRESS]: [respond(makeProgress({ generatedAt: FIRST, scanning: false }))],
    });
    await start();
    await tick(2000);
    expect(calls(PROGRESS)).toBe(1);
    expect(vi.getTimerCount()).toBe(0);
    expect(scanState().kind).toBe("ready");
  });

  it("treats a progress error with no scan to show as fatal", async () => {
    route({
      "/api/scan": [respond({ scanning: true }, 202)],
      [PROGRESS]: [respond(makeProgress({ error: "boom", scanning: false }))],
    });
    await start();
    expect(scanState()).toEqual({ kind: "error", message: "boom" });
  });

  it("reports a failing progress request and stops", async () => {
    route({ "/api/scan": [respond({ scanning: true }, 202)], [PROGRESS]: [respond({}, 500)] });
    await start();
    expect(scanState()).toEqual({ kind: "error", message: "HTTP 500 from /api/scan/progress" });
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("stopping", () => {
  it("never overlaps polls: waits for a slow progress reply", async () => {
    const slow = Promise.withResolvers<Response>();
    route({
      "/api/scan": [respond(makeScan({ generatedAt: FIRST, scanning: true }))],
      [PROGRESS]: [() => slow.promise],
    });
    await start();
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

  it("clears its timer and ignores a late progress reply", async () => {
    const late = Promise.withResolvers<Response>();
    route({
      "/api/scan": [respond(makeScan({ generatedAt: FIRST, scanning: true }))],
      [PROGRESS]: [respond(makeProgress({ generatedAt: FIRST })), () => late.promise],
    });
    await start();
    await tick();
    expect(calls(PROGRESS)).toBe(2);
    resetScan();
    late.resolve(respond(makeProgress({ generatedAt: SECOND, scanning: false })));
    await tick(2000);
    expect(calls(PROGRESS)).toBe(2);
    expect(calls("/api/scan")).toBe(1);
    expect(vi.getTimerCount()).toBe(0);
    expect(store.getState().progress?.generatedAt).toBe(FIRST);
  });

  it("clears its timer while waiting for the next tick", async () => {
    route({
      "/api/scan": [respond(makeScan({ generatedAt: FIRST, scanning: true }))],
      [PROGRESS]: [respond(makeProgress({ generatedAt: FIRST }))],
    });
    await start();
    expect(vi.getTimerCount()).toBe(1);
    resetScan();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("ignores a progress failure that lands after stopping", async () => {
    const lateFail = Promise.withResolvers<Response>();
    route({
      "/api/scan": [respond(makeScan({ generatedAt: FIRST, scanning: true }))],
      [PROGRESS]: [() => lateFail.promise],
    });
    await start();
    resetScan();
    lateFail.reject(new Error("late"));
    await tick(1000);
    expect(scanState()).toMatchObject({ kind: "ready", refreshError: null });
  });

  it("ignores a scan refetch that lands after stopping", async () => {
    const lateScan = Promise.withResolvers<Response>();
    route({
      "/api/scan": [respond(makeScan({ generatedAt: FIRST, scanning: true })), () => lateScan.promise],
      [PROGRESS]: [respond(makeProgress({ generatedAt: SECOND, scanning: false }))],
    });
    await start();
    resetScan();
    lateScan.resolve(respond(makeScan({ generatedAt: SECOND, host: "late" })));
    await tick(1000);
    expect(scanState()).toMatchObject({ scan: { host: "testhost" } });
  });
});
