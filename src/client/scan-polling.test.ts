/**
scan.ts polls /api/scan/progress every 250 ms while a scan runs.
*/
import { makeProgress, makeScan } from "../test/fixtures.ts";
import { respond } from "../test/route.ts";
import { calls, FIRST, PROGRESS, route, scanState, SECOND, start, tick, useScanHarness } from "../test/scan-harness.ts";
import { store } from "./store.ts";

useScanHarness();

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
