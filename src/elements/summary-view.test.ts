import { screen, within } from "@testing-library/dom";
import userEvent from "@testing-library/user-event";

import "./summary-view.ts";
import { store } from "../client/store.ts";
import { mount, resetDocument, showScan } from "../test/elements.ts";
import { ITEMS, makeScan } from "../test/fixtures.ts";
import { postedIds, stubRemove } from "../test/remove-stub.ts";

// The chart sizes itself from a ResizeObserver; report a real width at once.
class WideObserver {
  readonly #callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.#callback = callback;
  }
  disconnect(): void {
    // Nothing to release.
  }
  observe(): void {
    this.#callback([{ contentRect: { width: 900 } } as ResizeObserverEntry], this as unknown as ResizeObserver);
  }
}

function fire(target: Element, type: string, init: KeyboardEventInit = {}): void {
  const event = type === "keydown" ? new KeyboardEvent(type, { bubbles: true, ...init }) : new Event(type);
  target.dispatchEvent(event);
}

function urlParameters(): URLSearchParams {
  return new URLSearchParams(globalThis.location.search);
}

beforeEach(() => {
  resetDocument();
  vi.stubGlobal("ResizeObserver", WideObserver);
});

describe("summary-view", () => {
  it("shows the headline split and verdict tiles that sum to the scan", () => {
    showScan("summary");
    mount("summary-view");
    expect(screen.getByText("44.4% free")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "4 free" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "5 not free" })).toBeInTheDocument();
    expect(screen.getByTestId("count-nonfree")).toHaveTextContent("5");
    expect(screen.getByTestId("count-foss")).toHaveTextContent("3");
    const values = [...document.querySelectorAll(".summary .tiles .tile-value")];
    expect(values.reduce((sum, value) => sum + Number(value.textContent), 0)).toBe(ITEMS.length);
  });

  it("counts the whole scan, not the filtered table", () => {
    showScan("summary");
    store.set({ url: { ...store.getState().url, filter: { ...store.getState().url.filter, query: "chrome" } } });
    mount("summary-view");
    expect(screen.getByTestId("count-nonfree")).toHaveTextContent("5");
  });

  it("renders nothing outside the summary view and clears itself on leaving it", () => {
    showScan("table");
    const element = mount("summary-view");
    expect(element).toBeEmptyDOMElement();
    showScan("summary");
    expect(element.querySelector(".summary")).not.toBeNull();
    showScan("wins");
    expect(element).toBeEmptyDOMElement();
  });

  it("renders nothing while the scan is loading", () => {
    store.set({ url: { ...store.getState().url, view: "summary" } });
    expect(mount("summary-view")).toBeEmptyDOMElement();
  });

  it("drills into the table from tiles and the headline", async () => {
    const user = userEvent.setup();
    showScan("summary");
    mount("summary-view");
    await user.click(screen.getByRole("button", { name: /^Non-free/u }));
    expect(store.getState().url).toMatchObject({ filter: { sources: [], verdicts: ["nonfree"] }, view: "table" });
    expect(urlParameters().get("view")).toBe("table");
    showScan("summary");
    await user.click(screen.getByRole("button", { name: "5 not free" }));
    expect(store.getState().url.filter.verdicts).toEqual(["nonfree"]);
    showScan("summary");
    await user.click(screen.getByRole("button", { name: "4 free" }));
    expect(store.getState().url.filter.verdicts).toEqual(["foss", "foss-partial"]);
  });

  it("drills from a source label, a segment click and a segment Enter/Space", async () => {
    const user = userEvent.setup();
    showScan("summary");
    mount("summary-view");
    await user.click(screen.getByRole("button", { name: "steam" }));
    expect(store.getState().url.filter).toMatchObject({ sources: ["steam"], verdicts: [] });
    showScan("summary");
    await user.click(screen.getByRole("button", { name: /^pacman, Non-free: 2 of 5/u }));
    expect(store.getState().url.filter).toMatchObject({ sources: ["pacman"], verdicts: ["nonfree"] });
    for (const key of ["x", "Enter", " "]) {
      showScan("summary");
      fire(screen.getByRole("button", { name: /^pacman, FOSS: 2 of 5/u }), "keydown", { key });
      expect(store.getState().url.view).toBe(key === "x" ? "summary" : "table");
    }
  });

  it("draws the chart as SVG: a legend entry per verdict, only each bar's last segment rounded", () => {
    showScan("summary");
    mount("summary-view");
    expect(document.querySelectorAll(".chart svg").length).toBeGreaterThan(0);
    expect(screen.getByRole("list", { name: "Legend" }).children).toHaveLength(3);
    const pacman = screen.getByRole("group", { name: "pacman by verdict" });
    expect(pacman.getAttribute("width")).toBe(String(900 - 112 - 64 - 16));
    const paths = [...pacman.querySelectorAll("path")].map((p) => p.getAttribute("d") ?? "");
    expect(paths.at(-1)).toContain("Q");
    expect(paths.slice(0, -1).every((d) => !d.includes("Q"))).toBe(true);
  });

  it("shows a tooltip on hover and focus, hides it on leave and blur", () => {
    showScan("summary");
    mount("summary-view");
    const segment = screen.getByRole("button", { name: /^pacman, FOSS: 2 of 5/u });
    fire(segment, "mouseenter");
    expect(screen.getByRole("status")).toHaveTextContent("2 of 5 · 40%");
    fire(segment, "mouseleave");
    expect(screen.queryByRole("status")).toBeNull();
    fire(segment, "focus");
    expect(within(screen.getByRole("status")).getByText("pacman")).toBeInTheDocument();
    fire(segment, "blur");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("copies one Claude prompt covering every non-FOSS item", async () => {
    const user = userEvent.setup();
    const mock = stubRemove(ITEMS);
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    showScan("summary");
    mount("summary-view");
    expect(mock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Copy Claude prompt for all 6" }));
    await screen.findByText("Copied");
    expect(postedIds(mock)[0]).toHaveLength(6);
    expect(writeText).toHaveBeenCalledWith(expect.stringMatching(/^Replace 6 non-FOSS items with FOSS alternatives\n/u));
  });

  it("copes with an empty scan", () => {
    showScan("summary", makeScan({ items: [] }));
    mount("summary-view");
    expect(screen.getByText("0% free")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Copy Claude prompt/u })).toBeNull();
  });

  it("keeps its DOM when an unrelated slice changes", () => {
    showScan("summary");
    const element = mount("summary-view");
    const before = element.querySelector(".summary");
    store.set({ helpOpen: true });
    expect(element.querySelector(".summary")).toBe(before);
  });
});
