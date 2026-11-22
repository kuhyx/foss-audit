import "./items-table.ts";
import { resetStore, store } from "../client/store.ts";
import { ITEMS, makeItem } from "../test/fixtures.ts";
import { box, header, LETTERS, rows } from "../test/items-table-helpers.ts";
import { click, find, mount, press, showTable } from "../test/table-setup.ts";

beforeEach(() => {
  resetStore();
});

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
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
