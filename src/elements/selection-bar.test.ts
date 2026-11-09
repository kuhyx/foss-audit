import "./selection-bar.ts";
import { clearSelection, setFilter, setRowsChecked } from "../client/actions.ts";
import { resetStore } from "../client/store.ts";
import { DEFAULT_FILTER } from "../lib/filter.ts";
import { buildRemoveScript } from "../lib/remove-script.ts";
import { buildSelectionPrompt } from "../lib/selection-prompt.ts";
import { CHROME, makeItem } from "../test/fixtures.ts";
import { postedIds, stubRemove } from "../test/remove-stub.ts";
import { click, find, mount, showTable } from "../test/table-setup.ts";

const BASH = makeItem();

function copy(bar: ParentNode, prefix: string): HTMLElement {
  const found = [...bar.querySelectorAll<HTMLElement>(":scope .selection-bar button")].find((button) => button.textContent.startsWith(prefix));
  if (found === undefined) throw new Error(`no ${prefix} button`);
  return found;
}

beforeEach(() => {
  resetStore();
  showTable([CHROME, BASH]);
});

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("selection-bar", () => {
  it("is empty with nothing selected, and off the table view", () => {
    const bar = mount("selection-bar");
    expect(bar.childElementCount).toBe(0);
    setRowsChecked([CHROME.id], true);
    expect(bar.querySelector(".selection-bar")).not.toBeNull();
    showTable([CHROME, BASH], { view: "wins" });
    expect(bar.childElementCount).toBe(0);
  });

  it("counts the selection and clears it", () => {
    const bar = mount("selection-bar");
    setRowsChecked([CHROME.id, BASH.id], true);
    expect(find(bar, ".selection-count").textContent).toBe("2 selected · Clear");
    expect(find(bar, "section").getAttribute("aria-label")).toBe("Selection");
    click(find(bar, ".selection-count .link"));
    expect(bar.childElementCount).toBe(0);
  });

  it("follows the count and keeps its elements while the selection changes", () => {
    const bar = mount("selection-bar");
    setRowsChecked([CHROME.id], true);
    const section = find(bar, "section");
    setRowsChecked([BASH.id], true);
    expect(find(bar, "section")).toBe(section);
    expect(copy(bar, "Copy Claude prompt").textContent).toBe("Copy Claude prompt (2)");
    expect(copy(bar, "Copy remove commands").textContent).toBe("Copy remove commands (2)");
    clearSelection();
    expect(bar.childElementCount).toBe(0);
  });

  it("fetches nothing on selection, then exactly the selected ids when a copy button is used", async () => {
    const mock = stubRemove([CHROME, BASH]);
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    const bar = mount("selection-bar");
    setRowsChecked([CHROME.id, BASH.id], true);
    expect(mock).not.toHaveBeenCalled();
    click(copy(bar, "Copy Claude prompt"));
    await vi.waitFor(() => {
      expect(copy(bar, "Copy Claude prompt").nextElementSibling?.textContent).toBe("Copied");
    });
    expect(writeText).toHaveBeenLastCalledWith(buildSelectionPrompt([CHROME, BASH]));
    click(copy(bar, "Copy remove commands"));
    await vi.waitFor(() => {
      expect(writeText).toHaveBeenCalledTimes(2);
    });
    expect(writeText).toHaveBeenLastCalledWith(buildRemoveScript([CHROME, BASH]));
    expect(postedIds(mock)).toEqual([[CHROME.id, BASH.id]]);
  });

  it("copies what is checked at click time, filtered out rows included", async () => {
    stubRemove([CHROME, BASH]);
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    const bar = mount("selection-bar");
    setRowsChecked([CHROME.id], true);
    setFilter({ ...DEFAULT_FILTER, query: "bash" });
    expect(find(bar, ".selection-count").textContent).toBe("1 selected · Clear");
    click(copy(bar, "Copy remove commands"));
    await vi.waitFor(() => {
      expect(writeText).toHaveBeenCalledWith(buildRemoveScript([CHROME]));
    });
  });

  it("says so, and copies nothing, when the remove commands cannot be loaded", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(new Error("down")));
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    const bar = mount("selection-bar");
    setRowsChecked([CHROME.id], true);
    click(copy(bar, "Copy remove commands"));
    await vi.waitFor(() => {
      expect(copy(bar, "Copy remove commands").nextElementSibling?.textContent).toBe("Could not load the remove commands");
    });
    expect(writeText).not.toHaveBeenCalled();
  });
});
