import "./filter-bar.ts";
import { setFilter } from "../client/actions.ts";
import { resetStore, store } from "../client/store.ts";
import { DEFAULT_FILTER } from "../lib/filter.ts";
import { ITEMS } from "../test/fixtures.ts";
import { click, find, mount, showTable } from "../test/table-setup.ts";

function chips(bar: ParentNode, group: string): HTMLElement[] {
  return [...find(bar, `.chips[aria-label="${group}"]`).querySelectorAll<HTMLElement>(".chip")];
}

function chip(bar: ParentNode, group: string, label: RegExp): HTMLElement {
  const found = chips(bar, group).find((candidate) => label.test(candidate.textContent));
  if (found === undefined) throw new Error(`no ${group} chip ${label}`);
  return found;
}

function seg(bar: ParentNode, group: string, option: string): HTMLElement {
  const found = [...find(bar, `.segmented[aria-label="${group}"]`).querySelectorAll<HTMLElement>(".seg")].find((button) => button.textContent === option);
  if (found === undefined) throw new Error(`no ${group} ${option}`);
  return found;
}

const filterNow = (): typeof DEFAULT_FILTER => store.getState().url.filter;

beforeEach(() => {
  resetStore();
});

afterEach(() => {
  document.body.replaceChildren();
});

describe("filter-bar", () => {
  it("renders only on the table view with a ready scan", () => {
    const bar = mount("filter-bar");
    expect(bar.childElementCount).toBe(0);
    showTable(ITEMS, { view: "wins" });
    expect(bar.childElementCount).toBe(0);
    showTable(ITEMS);
    expect(bar.querySelector(".filters")).not.toBeNull();
    showTable(ITEMS, { view: "summary" });
    expect(bar.childElementCount).toBe(0);
  });

  it("shows whole-scan counts on chips, only present sources, and the result count", () => {
    showTable(ITEMS);
    const bar = mount("filter-bar");
    expect(chips(bar, "Verdict")).toHaveLength(3);
    expect(chip(bar, "Verdict", /Non-free/u).querySelector(".chip-count")?.textContent).toBe("5");
    expect(chips(bar, "Source").map((button) => button.textContent)).toEqual(["pacman5", "aur1", "opt1", "local-bin1", "steam1"]);
    expect(find(bar, ".result-count").textContent).toBe("9 of 9 items");
    expect(find(bar, ".result-count strong").textContent).toBe("9");
    expect(find<HTMLButtonElement>(bar, "[data-reset]").disabled).toBe(true);
  });

  it("shows 0 for a verdict the scan does not contain", () => {
    showTable(ITEMS.slice(0, 2));
    const bar = mount("filter-bar");
    expect(chip(bar, "Verdict", /^FOSS \(partial\)/u).querySelector(".chip-count")?.textContent).toBe("0");
  });

  it("toggles verdict and source chips on and off through the url", () => {
    showTable(ITEMS);
    const bar = mount("filter-bar");
    click(chip(bar, "Verdict", /Non-free/u));
    expect(filterNow().verdicts).toEqual(["nonfree"]);
    expect(chip(bar, "Verdict", /Non-free/u).getAttribute("aria-pressed")).toBe("true");
    expect(find(bar, ".result-count strong").textContent).toBe("5");
    click(chip(bar, "Verdict", /^FOSS \(partial\)/u));
    expect(filterNow().verdicts).toEqual(["foss-partial", "nonfree"]);
    click(chip(bar, "Verdict", /Non-free/u));
    expect(filterNow().verdicts).toEqual(["foss-partial"]);
    click(chip(bar, "Source", /^steam/u));
    expect(filterNow().sources).toEqual(["steam"]);
    expect(globalThis.location.search).toContain("src=steam");
  });

  it("sets each segmented facet", () => {
    showTable(ITEMS);
    const bar = mount("filter-bar");
    const cases = [
      ["Installed as", "Dependency", "kind", "dependency"],
      ["Orphan", "Yes", "orphan", "yes"],
      ["Own code", "Yes", "own", "yes"],
      ["Untracked file", "Yes", "loose", "yes"],
      ["Dead launcher", "Yes", "dangling", "yes"],
      ["Has alternative", "No", "hasAlt", "no"],
      ["Alternative installed", "Yes", "altInstalled", "yes"],
    ] as const;
    for (const [group, option, key, value] of cases) {
      click(seg(bar, group, option));
      expect(filterNow()[key]).toBe(value);
      expect(seg(bar, group, option).getAttribute("aria-pressed")).toBe("true");
      expect(seg(bar, group, "Any").getAttribute("aria-pressed")).toBe("false");
    }
  });

  it("resets to the default filter, query included", () => {
    showTable(ITEMS);
    const bar = mount("filter-bar");
    setFilter({ ...DEFAULT_FILTER, orphan: "yes", query: "lib" });
    const reset = find<HTMLButtonElement>(bar, "[data-reset]");
    expect(reset.disabled).toBe(false);
    expect(seg(bar, "Orphan", "Yes").getAttribute("aria-pressed")).toBe("true");
    click(reset);
    expect(filterNow()).toEqual(DEFAULT_FILTER);
    expect(reset.disabled).toBe(true);
  });

  it("starts collapsed for narrow screens and the toggle folds it open and shut", () => {
    showTable(ITEMS);
    const bar = mount("filter-bar");
    const root = find(bar, ".filters");
    const toggle = find(bar, ".filter-toggle");
    expect(root.dataset.collapsed).toBe("true");
    click(toggle);
    expect(root.dataset.collapsed).toBe("false");
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    click(toggle);
    expect(root.dataset.collapsed).toBe("true");
  });

  it("keeps the bar and its collapse state while the filter changes, rebuilds for a new scan", () => {
    showTable(ITEMS);
    const bar = mount("filter-bar");
    const root = find(bar, ".filters");
    click(find(bar, ".filter-toggle"));
    setFilter({ ...DEFAULT_FILTER, query: "x" });
    expect(find(bar, ".filters")).toBe(root);
    expect(root.dataset.collapsed).toBe("false");
    showTable(ITEMS.slice(0, 3));
    expect(find(bar, ".filters")).not.toBe(root);
    expect(find(bar, ".result-count").textContent).toBe("3 of 3 items");
  });

  it("ignores clicks that miss a button", () => {
    showTable(ITEMS);
    const bar = mount("filter-bar");
    click(find(bar, ".facet-label"));
    click(find(bar, ".filters"));
    expect(filterNow()).toEqual(DEFAULT_FILTER);
  });
});
