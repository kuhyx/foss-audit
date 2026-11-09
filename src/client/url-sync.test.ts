import { DEFAULT_STATE } from "../lib/url-state.ts";
import { resetStore, store } from "./store.ts";
import { reuseUnchanged, startUrlSync } from "./url-sync.ts";

beforeEach(() => {
  globalThis.history.replaceState(null, "", "/");
  resetStore();
});

describe("startUrlSync", () => {
  it("reads the address bar at once and again on popstate", () => {
    globalThis.history.replaceState(null, "", "/?view=wins");
    const stop = startUrlSync();
    expect(store.getState().url.view).toBe("wins");
    globalThis.history.replaceState(null, "", "/?view=table&q=a");
    globalThis.dispatchEvent(new PopStateEvent("popstate"));
    expect(store.getState().url).toMatchObject({ filter: { query: "a" }, view: "table" });
    stop();
    globalThis.history.replaceState(null, "", "/?view=wins");
    globalThis.dispatchEvent(new PopStateEvent("popstate"));
    expect(store.getState().url.view).toBe("table");
  });

  it("keeps slice identity when only the view changed", () => {
    const stop = startUrlSync();
    const { filter } = store.getState().url;
    globalThis.history.replaceState(null, "", "/?view=table");
    globalThis.dispatchEvent(new PopStateEvent("popstate"));
    expect(store.getState().url.filter).toBe(filter);
    stop();
  });
});

describe("reuseUnchanged", () => {
  it("takes the new slices when they differ", () => {
    const next = { ...DEFAULT_STATE, sort: { desc: true, id: "name" } };
    expect(reuseUnchanged(DEFAULT_STATE, next).sort).toBe(next.sort);
    const filtered = { ...DEFAULT_STATE, filter: { ...DEFAULT_STATE.filter, query: "x" } };
    expect(reuseUnchanged(DEFAULT_STATE, filtered).filter).toBe(filtered.filter);
  });
});
