import { DEFAULT_FILTER } from "../lib/filter.ts";
import { CHROME, makeItem } from "../test/fixtures.ts";
import {
  clearSelection,
  clickRow,
  closeHelp,
  closeItem,
  dismissBanner,
  drill,
  navigate,
  openHelp,
  openItem,
  setFilter,
  setQuery,
  setRowsChecked,
  setSort,
  setView,
  toggleHelp,
} from "./actions.ts";
import { selectBannerMessages } from "./selectors.ts";
import { resetStore, store } from "./store.ts";

beforeEach(() => {
  globalThis.history.replaceState(null, "", "/");
  resetStore();
});

describe("navigate", () => {
  it("writes the URL and the store together", () => {
    navigate((s) => ({ ...s, view: "table" }));
    expect(globalThis.location.search).toBe("?view=table");
    expect(store.getState().url.view).toBe("table");
  });

  it("composes two updates from one handler", () => {
    setQuery("chrome");
    setSort({ desc: false, id: "name" });
    expect(store.getState().url.filter.query).toBe("chrome");
    expect(store.getState().url.sort).toEqual({ desc: false, id: "name" });
  });

  it("pushes a history entry only when asked", () => {
    const before = globalThis.history.length;
    navigate((s) => ({ ...s, view: "table" }));
    expect(globalThis.history.length).toBe(before);
    setView("wins");
    expect(globalThis.history.length).toBe(before + 1);
  });

  it("writes a clean path for the default state", () => {
    globalThis.history.replaceState(null, "", "/?view=table");
    setView("summary");
    expect(globalThis.location.search).toBe("");
    expect(globalThis.location.pathname).toBe("/");
  });
});

describe("url actions", () => {
  it("setQuery goes to the table, setFilter and setSort keep the rest", () => {
    setQuery("fire");
    expect(store.getState().url.view).toBe("table");
    setFilter({ ...DEFAULT_FILTER, query: "fire", verdicts: ["nonfree"] });
    setSort({ desc: true, id: "name" });
    expect(globalThis.location.search).toBe("?view=table&q=fire&v=nonfree&sort=-name");
  });

  it("opens and closes an item", () => {
    openItem(CHROME.id);
    expect(store.getState().url.selected).toBe(CHROME.id);
    closeItem();
    expect(store.getState().url.selected).toBeNull();
  });

  it("drill opens the table filtered to the verdicts and sources, as a new history entry", () => {
    const before = globalThis.history.length;
    openItem("x");
    drill(["nonfree"], ["aur"]);
    expect(store.getState().url).toMatchObject({
      filter: { sources: ["aur"], verdicts: ["nonfree"] },
      selected: null,
      view: "table",
    });
    expect(globalThis.history.length).toBe(before + 1);
  });
});

describe("selection and help actions", () => {
  it("clicks rows, sets many and clears", () => {
    const order = ["a", "b", "c"];
    clickRow("a", order, false);
    clickRow("c", order, true);
    expect([...store.getState().selection.ids]).toEqual(["a", "b", "c"]);
    setRowsChecked(["b"], false);
    expect([...store.getState().selection.ids]).toEqual(["a", "c"]);
    clearSelection();
    expect(store.getState().selection.ids.size).toBe(0);
  });

  it("opens, closes and toggles help", () => {
    openHelp();
    expect(store.getState().helpOpen).toBe(true);
    closeHelp();
    toggleHelp();
    expect(store.getState().helpOpen).toBe(true);
  });

  it("dismisses the current banner until the error changes", () => {
    const scan = {
      errors: [{ message: "denied", source: "pacman" as const }],
      generatedAt: "t1",
      items: [makeItem()],
    };
    store.set({ scan: { kind: "ready", refreshError: null, refreshing: false, scan: scan as never } });
    expect(selectBannerMessages(store.getState())).toEqual(["pacman: denied"]);
    dismissBanner();
    expect(selectBannerMessages(store.getState())).toEqual([]);
    store.set({ scan: { kind: "ready", refreshError: "boom", refreshing: false, scan: scan as never } });
    expect(selectBannerMessages(store.getState())).toEqual(["pacman: denied", "Rescan failed: boom"]);
  });
});
