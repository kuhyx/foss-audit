import { CHROME, DEAD_LAUNCHER, ITEMS, makeItem, UNRAR } from "../test/fixtures.ts";
import { COLUMNS } from "./columns.ts";
import { nextSort, sortItems } from "./sort.ts";

const names = (items: readonly { name: string }[]): string[] => items.map((item) => item.name);
const LETTERS = ["d", "A", "e", "c", "b"].map((name) => makeItem({ name }));

describe("nextSort", () => {
  it("cycles ascending, descending, none and restarts on another column", () => {
    const asc = nextSort(null, "name");
    expect(asc).toEqual({ desc: false, id: "name" });
    const desc = nextSort(asc, "name");
    expect(desc).toEqual({ desc: true, id: "name" });
    expect(nextSort(desc, "name")).toBeNull();
    expect(nextSort(desc, "version")).toEqual({ desc: false, id: "version" });
  });
});

describe("sortItems", () => {
  it("returns the items as they are without a sort or for an unknown column", () => {
    expect(sortItems(ITEMS, null)).toBe(ITEMS);
    expect(sortItems(ITEMS, { desc: false, id: "nope" })).toBe(ITEMS);
  });

  it("sorts text case-insensitively, both ways, without touching the input", () => {
    const input = [...LETTERS];
    expect(names(sortItems(input, { desc: false, id: "name" }))).toEqual(["A", "b", "c", "d", "e"]);
    expect(names(sortItems(input, { desc: true, id: "name" }))).toEqual(["e", "d", "c", "b", "A"]);
    expect(input).toEqual(LETTERS);
  });

  it("keeps ties in scan order in both directions", () => {
    const same = [makeItem({ name: "x1" }), makeItem({ name: "x2" }), makeItem({ name: "x3" })];
    expect(names(sortItems(same, { desc: false, id: "source" }))).toEqual(["x1", "x2", "x3"]);
    expect(names(sortItems(same, { desc: true, id: "source" }))).toEqual(["x1", "x2", "x3"]);
  });

  it("sorts rank columns and keeps absent values last whichever way", () => {
    const fits = (isDesc: boolean): string[] =>
      sortItems(ITEMS, { desc: isDesc, id: "fit" }).map((item) => item.alternative?.fit ?? "-");
    expect(fits(false)).toEqual(["drop-in", "good", "good", ...Array.from({ length: 6 }, () => "-")]);
    expect(fits(true).slice(0, 3)).toEqual(["good", "good", "drop-in"]);
    expect(fits(true).at(-1)).toBe("-");
  });

  it("puts a missing licence last, ascending and descending", () => {
    const rows = [makeItem({ license: "", name: "none" }), makeItem({ license: "MIT", name: "mit" }), makeItem({ license: "Apache", name: "apache" })];
    expect(names(sortItems(rows, { desc: false, id: "license" }))).toEqual(["apache", "mit", "none"]);
    expect(names(sortItems(rows, { desc: true, id: "license" }))).toEqual(["mit", "apache", "none"]);
  });

  it.each(COLUMNS.map((column) => column.id))("sorts by %s without losing rows", (id) => {
    const sorted = sortItems([...ITEMS, DEAD_LAUNCHER], { desc: true, id });
    expect(sorted).toHaveLength(ITEMS.length + 1);
    const unique = new Set(sorted);
    expect(unique.size).toBe(ITEMS.length + 1);
  });
});

describe("COLUMNS", () => {
  const byId = (id: string) => COLUMNS.find((column) => column.id === id)!;

  it("renders the cell text of each column", () => {
    const row = (item: Parameters<(typeof COLUMNS)[number]["text"]>[0]): string[] => COLUMNS.map((column) => column.text(item));
    expect(row(CHROME)).toEqual([
      "google-chrome", "5.2.0-1", "aur", "Non-free", "custom:chrome", "explicit", "", "", "Chromium", "Drop-in", "XL", "ungoogled-chromium-bin",
    ]);
    expect(row(UNRAR).slice(5, 8)).toEqual(["dependency", "", "1"]);
    expect(byId("orphan").text(makeItem({ orphan: true }))).toBe("orphan");
    expect(byId("version").text(makeItem({ version: null }))).toBe("—");
    expect(byId("license").text(makeItem({ license: "" }))).toBe("—");
  });

  it("keys absent values as undefined", () => {
    const bare = makeItem({ license: "", version: null });
    for (const id of ["alternative", "fit", "effort", "installed", "version", "license"]) {
      expect(byId(id).sortKey(bare)).toBeUndefined();
    }
    expect(COLUMNS.map((column) => column.text(bare)).filter((_, index) => index !== 3)).toEqual(["bash", "—", "pacman", "—", "explicit", "", "", "", "", "", ""]);
    expect(byId("alternative").text(makeItem({ alternative: { ...CHROME.alternative!, names: [] } }))).toBe("");
    expect(byId("effort").sortKey(makeItem({ alternative: { ...CHROME.alternative!, effort: null } }))).toBeUndefined();
  });
});
