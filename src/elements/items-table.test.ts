import "./items-table.ts";
import { closeItem, openItem, setSort } from "../client/actions.ts";
import { resetStore, store } from "../client/store.ts";
import { DEAD_LAUNCHER, ITEMS, makeItem } from "../test/fixtures.ts";
import { box, column, FIT, head, LETTERS, NAME, rows, stubScrollTop } from "../test/items-table-helpers.ts";
import { click, find, mount, paintedWords, press, showTable, spoken } from "../test/table-setup.ts";

beforeEach(() => {
  resetStore();
});

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("items-table", () => {
  it("renders nothing until the table view has a ready scan", () => {
    const table = mount("items-table");
    expect(table.childElementCount).toBe(0);
    showTable(ITEMS, { view: "summary" });
    expect(table.childElementCount).toBe(0);
    showTable(ITEMS);
    expect(rows(table)).toHaveLength(ITEMS.length);
    store.set({ url: { ...store.getState().url, view: "wins" } });
    expect(table.childElementCount).toBe(0);
  });

  it("explains an empty result and recovers when rows return", () => {
    showTable([]);
    const table = mount("items-table");
    expect(find(table, ".table-empty [role=img]").getAttribute("aria-label")).toContain("No items match these filters.");
    expect(table.querySelector(".table-scroll")).toBeNull();
    showTable(ITEMS);
    expect(table.querySelector(".table-empty")).toBeNull();
    expect(rows(table)).toHaveLength(ITEMS.length);
  });

  it("renders every row with formatted cells and 13 column headers", () => {
    showTable([...ITEMS, DEAD_LAUNCHER]);
    const table = mount("items-table");
    expect(table.querySelectorAll('[role="columnheader"]')).toHaveLength(13);
    const first = rows(table)[0]!;
    expect(first.getAttribute("aria-rowindex")).toBe("2");
    expect(first.dataset.id).toBe("pacman:bash");
    const text = (name: string): string => spoken(rows(table).find((row) => row.textContent.includes(name))!);
    expect(text("Some Game")).toContain("—");
    expect(text("Some Game")).toContain("0ad");
    expect(text("Some Game")).toContain("Fit: Good, rank 1 of 4");
    expect(text("unrar")).toContain("dependency");
    expect(text("libfoo")).toContain("orphan");
    expect(text("backup.sh")).toContain("kuhy's own code");
    expect(text("mystery")).toContain("no repo or package tracks it");
    expect(text("rpcs3")).toContain("Exec target no longer exists");
    expect(find(rows(table)[0]!, ".verdict .verdict-mark").getAttribute("role")).toBe("img");
    expect(paintedWords(find(table, ".thead"))).toEqual([]);
  });

  it("sorts by the url sort and marks only that header", () => {
    showTable(ITEMS, { sort: { desc: false, id: "name" } });
    const table = mount("items-table");
    expect(column(table, NAME)[0]).toBe("backup.sh kuhy's own code");
    const marked = [...table.querySelectorAll(".th[aria-sort]")].filter((th) => th.getAttribute("aria-sort") !== "none");
    expect(marked).toHaveLength(1);
    expect(marked[0]?.getAttribute("aria-sort")).toBe("ascending");
    setSort({ desc: true, id: "fit" });
    expect(column(table, FIT).filter((fit) => fit !== "").slice(0, 3)).toEqual([
      "Fit: None, rank 4 of 4",
      "Fit: Good, rank 3 of 4",
      "Fit: Drop-in, rank 2 of 4",
    ]);
    expect(column(table, FIT).at(-1)).toBe("Fit: not ranked yet");
    expect(find(table, '.th[aria-sort="descending"] .sort-mark').textContent).toBe("▼");
  });

  it("cycles the sort from a header click: asc, desc, none", () => {
    showTable(ITEMS);
    const table = mount("items-table");
    click(head(table, "Name"));
    expect(store.getState().url.sort).toEqual({ desc: false, id: "name" });
    click(head(table, "Name"));
    expect(store.getState().url.sort).toEqual({ desc: true, id: "name" });
    click(head(table, "Name"));
    expect(store.getState().url.sort).toBeNull();
    click(head(table, "Version"));
    expect(store.getState().url.sort).toEqual({ desc: false, id: "version" });
  });

  it("opens an item on a row click, marks it and focuses the row", () => {
    showTable(ITEMS);
    const table = mount("items-table");
    click(find(rows(table)[1]!, ".td:nth-child(3)"));
    expect(store.getState().url.selected).toBe("aur:google-chrome");
    const chrome = rows(table)[1]!;
    expect(chrome.getAttribute("aria-selected")).toBe("true");
    expect(chrome.tabIndex).toBe(0);
    expect(rows(table).filter((row) => row.tabIndex === 0)).toHaveLength(1);
    expect(document.activeElement).toBe(chrome);
  });

  it("puts the one tab stop on the first row when nothing is open", () => {
    showTable(ITEMS);
    const table = mount("items-table");
    expect(rows(table).map((row) => row.tabIndex)).toEqual([0, ...Array.from({ length: ITEMS.length - 1 }, () => -1)]);
  });

  it("moves the selection with the arrow keys, clamped, and opens with Enter", () => {
    showTable(ITEMS);
    const table = mount("items-table");
    const scroller = find(table, ".table-scroll");
    press(scroller, "ArrowDown");
    expect(store.getState().url.selected).toBe("pacman:bash");
    press(find(table, '.tr.row[data-id="pacman:bash"]'), "ArrowDown");
    expect(store.getState().url.selected).toBe(ITEMS[1]?.id);
    expect(document.activeElement).toBe(rows(table)[1]);
    press(rows(table)[1]!, "ArrowUp");
    press(rows(table)[0]!, "ArrowUp");
    expect(store.getState().url.selected).toBe("pacman:bash");
    closeItem();
    press(scroller, "ArrowUp");
    expect(store.getState().url.selected).toBe(ITEMS.at(-1)?.id);
    press(scroller, "PageDown");
    expect(store.getState().url.selected).toBe(ITEMS.at(-1)?.id);
    closeItem();
    press(rows(table)[2]!, "Enter");
    expect(store.getState().url.selected).toBe(ITEMS[2]?.id);
  });

  it("ignores keys from the controls inside the table", () => {
    showTable(ITEMS);
    const table = mount("items-table");
    press(box(table, "bash"), " ");
    press(head(table, "Name"), "ArrowDown");
    expect(store.getState().selection.ids.size).toBe(0);
    expect(store.getState().url.selected).toBeNull();
  });

  it("returns focus to the row when the detail panel closes", () => {
    showTable(ITEMS);
    const table = mount("items-table");
    openItem("pacman:unrar");
    (document.activeElement as HTMLElement).blur();
    closeItem();
    expect(document.activeElement).toBe(find(table, '.tr.row[data-id="pacman:unrar"]'));
  });

  it("does not move focus when the closed row is filtered away", () => {
    showTable(ITEMS);
    mount("items-table");
    openItem("pacman:unrar");
    showTable(ITEMS.slice(0, 2), { selected: null });
    expect(document.activeElement).toBe(document.body);
  });

  it("mounts only a window of a long list and slides it with the scroll", () => {
    const many = Array.from({ length: 500 }, (_, index) => makeItem({ name: `pkg${String(index).padStart(3, "0")}` }));
    showTable(many);
    const table = mount("items-table");
    const scroller = find(table, ".table-scroll");
    const position = stubScrollTop(scroller);
    expect(find(table, ".tbody").style.height).toBe("20000px");
    expect(rows(table).length).toBeLessThan(60);
    expect(rows(table)[0]?.dataset.id).toBe("pacman:pkg000");
    position.top = 400 * 40;
    scroller.dispatchEvent(new Event("scroll"));
    const ids = rows(table).map((row) => row.dataset.id);
    expect(ids).not.toContain("pacman:pkg000");
    expect(ids).toContain("pacman:pkg400");
    expect(rows(table).map((row) => Number(row.getAttribute("aria-rowindex")))).toEqual(
      rows(table).map((_, offset) => Number(rows(table)[0]?.getAttribute("aria-rowindex")) + offset),
    );
    expect(find(table, '.tr.row[data-id="pacman:pkg400"]').style.transform).toBe("translateY(16000px)");
  });

  it("scrolls an opened row far outside the window into view", () => {
    const many = Array.from({ length: 500 }, (_, index) => makeItem({ name: `pkg${String(index).padStart(3, "0")}` }));
    showTable(many);
    const table = mount("items-table");
    const position = stubScrollTop(find(table, ".table-scroll"));
    openItem("pacman:pkg300");
    expect(position.top).toBe(301 * 40 - 760);
    expect(find(table, '.tr.row[data-id="pacman:pkg300"]').getAttribute("aria-selected")).toBe("true");
  });

  it("waits for the view to get a height before scrolling to the opened row", () => {
    const many = Array.from({ length: 500 }, (_, index) => makeItem({ name: `pkg${String(index).padStart(3, "0")}` }));
    let notify = (): void => {};
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(callback: () => void) {
          notify = callback;
        }
        disconnect(): void {}
        observe(): void {}
      },
    );
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(0);
    showTable(many, { selected: "pacman:pkg300" });
    const table = mount("items-table");
    const scroller = find(table, ".table-scroll");
    const position = stubScrollTop(scroller);
    notify();
    expect(position.top).toBe(0);
    Object.defineProperty(scroller, "clientHeight", { configurable: true, get: () => 800 });
    notify();
    expect(position.top).toBe(301 * 40 - 760);
    notify();
    expect(position.top).toBe(301 * 40 - 760);
  });

  it("reveals nothing when the observer fires with no pending reveal", () => {
    let notify = (): void => {};
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(callback: () => void) {
          notify = callback;
        }
        disconnect(): void {}
        observe(): void {}
      },
    );
    showTable(ITEMS);
    mount("items-table");
    expect(() => {
      notify();
    }).not.toThrow();
  });

  it("rebuilds the rows when the scan items change", () => {
    showTable(LETTERS);
    const table = mount("items-table");
    expect(rows(table)).toHaveLength(5);
    showTable(LETTERS.slice(0, 2));
    expect(rows(table)).toHaveLength(2);
    expect(find(table, ".tbody").style.height).toBe("80px");
  });
});
