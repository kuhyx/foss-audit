import { CHROME, makeItem, makeScan } from "../test/fixtures.ts";
import {
  bannerKey,
  selectBannerMessages,
  selectCheckedItems,
  selectItems,
  selectResults,
  selectSelectedItem,
  selectTabCounts,
  selectWins,
} from "./selectors.ts";
import { initialState } from "./store.ts";

const BASH = makeItem();

function ready(overrides: Partial<ReturnType<typeof initialState>> = {}): ReturnType<typeof initialState> {
  const scan = makeScan({ items: [CHROME, BASH] });
  return { ...initialState(), scan: { kind: "ready", refreshError: null, refreshing: false, scan }, ...overrides };
}

describe("selectors", () => {
  it("are empty before the scan is ready", () => {
    const state = initialState();
    expect(selectItems(state)).toEqual([]);
    expect(selectTabCounts(state)).toEqual({ summary: 0, table: 0, wins: 0 });
    expect(selectBannerMessages(state)).toEqual([]);
    expect(bannerKey(state)).toBe("");
  });

  it("return the same array until an input changes", () => {
    const state = ready();
    expect(selectResults(state)).toBe(selectResults({ ...state, helpOpen: true }));
    expect(selectWins(state)).toBe(selectWins({ ...state }));
    const filtered = { ...state, url: { ...state.url, filter: { ...state.url.filter, query: "chrome" } } };
    expect(selectResults(filtered)).not.toBe(selectResults(state));
  });

  it("keep the previous answer too, so asking for the new and then the old state does not recompute", () => {
    const state = ready();
    const filtered = { ...state, url: { ...state.url, filter: { ...state.url.filter, query: "chrome" } } };
    const before = selectResults(state);
    const after = selectResults(filtered);
    expect(selectResults(state)).toBe(before);
    expect(selectResults(filtered)).toBe(after);
  });

  it("count the tabs, find the open item and the checked items", () => {
    const state = ready({
      selection: { anchor: null, ids: new Set([BASH.id]) },
      url: { ...initialState().url, filter: { ...initialState().url.filter, query: "chrome" }, selected: CHROME.id },
    });
    expect(selectTabCounts(state)).toEqual({ summary: 2, table: 1, wins: 1 });
    expect(selectSelectedItem(state)).toBe(CHROME);
    expect(selectCheckedItems(state)).toEqual([BASH]);
    expect(selectSelectedItem(ready())).toBeNull();
  });

  it("list scanner errors and a failed rescan, and honour a dismissal", () => {
    const base = ready();
    const scan = base.scan.kind === "ready" ? base.scan : null;
    expect(scan).not.toBeNull();
    const withError = {
      ...base,
      scan: { ...scan!, refreshError: "boom", scan: { ...scan!.scan, errors: [{ message: "denied", source: "aur" as const }] } },
    };
    expect(selectBannerMessages(withError)).toEqual(["aur: denied", "Rescan failed: boom"]);
    expect(selectBannerMessages({ ...withError, dismissedErrorKey: bannerKey(withError) })).toEqual([]);
  });
});
