import "./items-table.ts";
import { closeItem, openItem, setSort } from "../client/actions.ts";
import { resetStore, store } from "../client/store.ts";
import { DEAD_LAUNCHER, ITEMS, makeItem } from "../test/fixtures.ts";
import { click, find, mount, press, showTable } from "../test/table-setup.ts";

const NAME = 1;
const FIT = 10;
const LETTERS = ["d", "a", "e", "c", "b"].map((name) => makeItem({ name }));

function rows(root: ParentNode): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(".tr.row")];
}

function column(root: ParentNode, index: number): string[] {
  return rows(root).map((row) => row.querySelectorAll(".td")[index]?.textContent ?? "");
}

function box(root: ParentNode, name: string): HTMLInputElement {
  return find<HTMLInputElement>(root, `input[aria-label="Select ${name}"]`);
}

function header(root: ParentNode): HTMLInputElement {
  return find<HTMLInputElement>(root, 'input[aria-label="Select all shown"]');
}

function head(root: ParentNode, label: string): HTMLElement {
  const found = [...root.querySelectorAll<HTMLElement>(".th-button")].find((button) => button.textContent.startsWith(label));
  if (found === undefined) throw new Error(`no ${label} header`);
  return found;
}

function stubScrollTop(scroller: HTMLElement): { top: number } {
  const position = { top: 0 };
  Object.defineProperty(scroller, "scrollTop", {
    configurable: true,
    get: () => position.top,
    set: (value: number) => {
      position.top = value;
    },
  });
  return position;
}

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
    expect(table.querySelector(".table-empty")?.textContent).toContain("No items match these filters.");
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
    const text = (name: string): string => rows(table).find((row) => row.textContent.includes(name))!.textContent;
    expect(text("Some Game")).toContain("—");
    expect(text("Some Game")).toContain("0ad");
    expect(text("Some Game")).toContain("Good");
    expect(text("unrar")).toContain("dependency");
    expect(text("libfoo")).toContain("orphan");
    expect(text("backup.sh")).toContain("own");
    expect(text("mystery")).toContain("loose");
    expect(text("rpcs3")).toContain("dead");
    expect(find(rows(table)[0]!, ".verdict .dot").getAttribute("aria-hidden")).toBe("true");
  });

  it("sorts by the url sort and marks only that header", () => {
    showTable(ITEMS, { sort: { desc: false, id: "name" } });
    const table = mount("items-table");
    expect(column(table, NAME)[0]).toBe("backup.sh own");
    const marked = [...table.querySelectorAll(".th[aria-sort]")].filter((th) => th.getAttribute("aria-sort") !== "none");
    expect(marked).toHaveLength(1);
    expect(marked[0]?.getAttribute("aria-sort")).toBe("ascending");
    setSort({ desc: true, id: "fit" });
    expect(column(table, FIT).filter((fit) => fit !== "").slice(0, 3)).toEqual(["Good", "Good", "Drop-in"]);
    expect(column(table, FIT).at(-1)).toBe("");
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

describe("items-table selection", () => {
  const checked = (): string[] => [...store.getState().selection.ids].toSorted((a, b) => a.localeCompare(b));

  it("toggles a row from its checkbox without opening the detail panel", () => {
    showTable(ITEMS);
    const table = mount("items-table");
    click(box(table, "unrar"));
    expect(checked()).toEqual(["pacman:unrar"]);
    expect(box(table, "unrar").checked).toBe(true);
    expect(store.getState().url.selected).toBeNull();
    click(box(table, "unrar"));
    expect(checked()).toEqual([]);
  });

  it("keeps the row checkboxes out of the tab order and focus on the row", () => {
    showTable(ITEMS);
    const table = mount("items-table");
    expect(box(table, "bash").tabIndex).toBe(-1);
    click(box(table, "bash"));
    expect(document.activeElement).toBe(rows(table)[0]);
  });

  it("shift-selects the range in the current sorted order", () => {
    showTable(LETTERS, { sort: { desc: false, id: "name" } });
    const table = mount("items-table");
    click(box(table, "b"));
    click(box(table, "d"), { shiftKey: true });
    expect(checked()).toEqual(["pacman:b", "pacman:c", "pacman:d"]);
  });

  it("shift-selects the range in the current filtered order", () => {
    showTable(LETTERS);
    const table = mount("items-table");
    showTable(LETTERS.filter((item) => item.name !== "e"));
    click(box(table, "d"));
    click(box(table, "c"), { shiftKey: true });
    expect(checked()).toEqual(["pacman:a", "pacman:c", "pacman:d"]);
  });

  it("selects every shown row from the header, indeterminate when partial", () => {
    showTable(LETTERS);
    const table = mount("items-table");
    expect(header(table).checked).toBe(false);
    click(box(table, "a"));
    expect(header(table).indeterminate).toBe(true);
    click(header(table));
    expect(checked()).toHaveLength(5);
    expect(header(table).checked).toBe(true);
    expect(header(table).indeterminate).toBe(false);
    click(header(table));
    expect(checked()).toEqual([]);
  });

  it("keeps the selection across a filter change and adds to it", () => {
    const google = [makeItem({ name: "com.google.a" }), makeItem({ name: "com.google.b" })];
    const firebase = [makeItem({ name: "firebase-x" })];
    showTable(google);
    const table = mount("items-table");
    click(header(table));
    showTable(firebase);
    expect(header(table).checked).toBe(false);
    click(header(table));
    expect(checked()).toEqual(["pacman:com.google.a", "pacman:com.google.b", "pacman:firebase-x"]);
    click(header(table));
    expect(checked()).toEqual(["pacman:com.google.a", "pacman:com.google.b"]);
  });

  it("toggles the focused row with Space and extends with Shift+Space", () => {
    showTable(LETTERS, { sort: { desc: false, id: "name" } });
    const table = mount("items-table");
    const row = (name: string): HTMLElement => find(table, `.tr.row[data-id="pacman:${name}"]`);
    press(row("a"), " ");
    expect(checked()).toEqual(["pacman:a"]);
    press(row("c"), " ", { shiftKey: true });
    expect(checked()).toEqual(["pacman:a", "pacman:b", "pacman:c"]);
    press(row("a"), " ");
    expect(checked()).toEqual(["pacman:b", "pacman:c"]);
  });

  it("ignores Space on the scroller when no row has focus", () => {
    showTable(LETTERS);
    const table = mount("items-table");
    press(find(table, ".table-scroll"), " ");
    expect(checked()).toEqual([]);
  });
});
