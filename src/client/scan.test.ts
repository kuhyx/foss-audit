/**
 * The backend scans in the background; scan.ts watches /api/scan/progress.
 * Load, refresh and stopping; polling lives in scan-polling.test.ts.
 */
import { makeProgress, makeScan } from "../test/fixtures.ts";
import { respond } from "../test/route.ts";
import { calls, fetchMock, FIRST, PROGRESS, route, scanState, SECOND, start, tick, useScanHarness } from "../test/scan-harness.ts";
import { refresh, resetScan } from "./scan.ts";
import { store } from "./store.ts";

useScanHarness();

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
