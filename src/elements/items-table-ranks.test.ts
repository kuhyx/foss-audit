import "./items-table.ts";
import { resetStore } from "../client/store.ts";
import { CHROME, DEAD_LAUNCHER, ITEMS, makeItem } from "../test/fixtures.ts";
import { ALTERNATIVE, EFFORT, FIT, INSTALLED, ORPHAN, REQUIRED_BY, rows } from "../test/items-table-helpers.ts";
import { find, mount, showTable, spoken } from "../test/table-setup.ts";

beforeEach(() => {
  resetStore();
});

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("items-table rank cells", () => {
  let table: HTMLElement;

  beforeEach(() => {
    showTable([...ITEMS, DEAD_LAUNCHER]);
    table = mount("items-table");
  });

  function cells(name: string, index: number): HTMLElement {
    const row = rows(table).find((candidate) => candidate.dataset.id?.endsWith(`:${name}`));
    return row!.querySelectorAll<HTMLElement>(".td")[index]!;
  }

  it("paints the rank number, spoken with the meaning and the total", () => {
    const fit = cells("google-chrome", FIT);
    expect(fit.textContent).toBe("2");
    expect(spoken(fit)).toBe("Fit: Drop-in, rank 2 of 4");
    expect(find(fit, ".rank").getAttribute("aria-description")).toBe("a browser engine is a huge build");
    expect(spoken(cells("google-chrome", EFFORT))).toBe("Effort: XL · infeasible, rank 2 of 4");
    expect(spoken(cells("Some Game", EFFORT))).toBe("Effort: unknown, rank 3 of 4");
    expect(spoken(cells("linux-firmware", FIT))).toBe("Fit: None, rank 4 of 4");
    expect(find(fit, ".rank").hasAttribute("aria-description")).toBe(true);
    expect(cells("unrar", FIT).querySelector("[aria-description]")).toBeNull();
  });

  it("never paints the reason", () => {
    expect(table.textContent).not.toContain("huge build");
  });

  it("shows the warning glyph in both cells of an unranked item", () => {
    for (const index of [FIT, EFFORT]) {
      const cell = cells("mystery", index);
      expect(cell.textContent).toBe("⚠");
      expect(find(cell, "[role=img]").getAttribute("aria-label")).toMatch(/not ranked yet$/u);
    }
  });

  it("leaves rank cells empty for FOSS rows and for a to-replace row without rank fields", () => {
    for (const index of [FIT, EFFORT]) {
      expect(cells("bash", index).textContent).toBe("");
      expect(cells("rpcs3", index).textContent).toBe("");
    }
  });

  it("answers none with a glyph on to-replace rows only", () => {
    expect([ALTERNATIVE, INSTALLED, ORPHAN, REQUIRED_BY].map((index) => cells("mystery", index).textContent)).toEqual([
      "∅",
      "∅",
      "✕",
      "0",
    ]);
    expect(spoken(cells("mystery", ALTERNATIVE))).toBe("No alternative");
    expect(spoken(cells("mystery", INSTALLED))).toBe("Nothing installed");
    expect(spoken(cells("mystery", ORPHAN))).toBe("not an orphan");
    expect([ALTERNATIVE, INSTALLED, ORPHAN, REQUIRED_BY].map((index) => cells("bash", index).textContent)).toEqual(["", "", "", ""]);
    expect(cells("google-chrome", INSTALLED).textContent).toBe("ungoogled-chromium-bin");
    expect(cells("unar", INSTALLED).textContent).toBe("∅");
    expect(cells("unrar", REQUIRED_BY).textContent).toBe("1");
    expect(cells("libfoo", ORPHAN).textContent).toBe("🏝");
  });

  it("treats an alternative with no names or nothing installed as none", () => {
    const bare = makeItem({ alternative: { ...CHROME.alternative!, installed: [], names: [] }, name: "bare", verdict: "nonfree" });
    showTable([bare]);
    const row = rows(table)[0]!;
    const td = row.querySelectorAll<HTMLElement>(".td");
    expect([td[ALTERNATIVE]!.textContent, td[INSTALLED]!.textContent]).toEqual(["∅", "∅"]);
  });
});
