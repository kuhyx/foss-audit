import { CHROME, makeItem, makeScan } from "../test/fixtures.ts";
import { setView } from "./actions.ts";
import { searchInput, startShell } from "./shell.ts";
import { resetStore, store } from "./store.ts";

const FIXTURE = `
<main id="home">homepage</main>
<main id="app-msg" hidden>
  <div id="msg-loading"></div>
  <div id="msg-error" hidden><span id="msg-error-text"></span></div>
</main>
<div id="app" hidden>
  <span data-meta="host"></span><time data-meta="scanned"></time><span data-meta="took"></span>
  <input aria-label="Search name or id" class="search" />
  <button aria-label="Rescan" id="rescan" type="button">⟳</button>
  <nav>
    <button class="tab" data-view="summary"><span class="tab-count"></span></button>
    <button class="tab" data-view="table"><span class="tab-count"></span></button>
    <button class="tab" data-view="wins"><span class="tab-count"></span></button>
  </nav>
  <div class="view" data-view="summary"></div>
  <div class="view" data-view="table"></div>
  <div class="view" data-view="wins"></div>
</div>`;

function isHidden(selector: string): boolean {
  return document.querySelector(selector)?.hasAttribute("hidden") ?? false;
}

function ready(isRefreshing = false): void {
  const scan = makeScan({ items: [CHROME, makeItem()] });
  store.set({ scan: { kind: "ready", refreshError: null, refreshing: isRefreshing, scan } });
}

const handle = { stop: (): void => {} };

beforeEach(() => {
  globalThis.history.replaceState(null, "", "/");
  const parser = new DOMParser();
  const parsed = parser.parseFromString(FIXTURE, "text/html");
  document.body.replaceChildren(...parsed.body.children);
  resetStore();
  handle.stop = startShell();
});

afterEach(() => {
  handle.stop();
});

describe("startShell", () => {
  it("swaps the homepage for the loading screen at once", () => {
    expect(isHidden("#home")).toBe(true);
    expect(isHidden("#app-msg")).toBe(false);
    expect(isHidden("#msg-loading")).toBe(false);
    expect(isHidden("#app")).toBe(true);
  });

  it("shows the app, the meta line and the tab counts once the scan is ready", () => {
    ready();
    expect(isHidden("#app")).toBe(false);
    expect(isHidden("#app-msg")).toBe(true);
    expect(document.querySelector('[data-meta="host"]')?.textContent).toBe("testhost");
    expect(document.querySelector('[data-meta="scanned"]')?.getAttribute("datetime")).toBe(makeScan().generatedAt);
    expect(document.querySelector('.tab[data-view="summary"] .tab-count')?.textContent).toBe("2");
    expect(document.querySelector("#rescan")?.getAttribute("aria-label")).toBe("Rescan");
    expect(document.querySelector("#rescan")?.textContent).toBe("⟳");
  });

  it("shows the readable error and no [object Object]", () => {
    store.set({ scan: { kind: "error", message: "HTTP 500 from /api/scan" } });
    expect(isHidden("#msg-error")).toBe(false);
    expect(document.querySelector("#msg-error-text")?.textContent).toBe("HTTP 500 from /api/scan");
  });

  it("marks the current tab and shows only its view", () => {
    ready();
    expect(document.querySelector('.tab[data-view="summary"]')?.getAttribute("aria-current")).toBe("page");
    expect(isHidden('.view[data-view="summary"]')).toBe(false);
    expect(isHidden('.view[data-view="table"]')).toBe(true);
    document.querySelector<HTMLElement>('.tab[data-view="wins"]')?.click();
    expect(store.getState().url.view).toBe("wins");
    expect(document.querySelector('.tab[data-view="summary"]')?.hasAttribute("aria-current")).toBe(false);
    expect(isHidden('.view[data-view="wins"]')).toBe(false);
  });

  it("types into the search box through the store, and follows Back into the box", () => {
    ready();
    searchInput().value = "fire";
    searchInput().dispatchEvent(new Event("input"));
    expect(store.getState().url).toMatchObject({ filter: { query: "fire" }, view: "table" });
    expect(document.querySelector('.tab[data-view="table"] .tab-count')?.textContent).toBe("0");
    store.set({ url: { ...store.getState().url, filter: { ...store.getState().url.filter, query: "" } } });
    expect(searchInput().value).toBe("");
  });

  it("reflects a rescan on the button", () => {
    ready(true);
    const button = document.querySelector<HTMLButtonElement>("#rescan");
    expect(button?.disabled).toBe(true);
    expect(button?.getAttribute("aria-busy")).toBe("true");
    expect(button?.getAttribute("aria-label")).toBe("Rescanning…");
    expect(button?.textContent).toBe("⟳");
  });

  it("stops listening when told", () => {
    handle.stop();
    setView("wins");
    expect(isHidden('.view[data-view="wins"]')).toBe(true);
    document.querySelector<HTMLElement>("#rescan")?.click();
    expect(store.getState().scan.kind).toBe("loading");
  });
});
