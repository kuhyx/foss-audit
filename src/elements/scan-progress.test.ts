import { screen } from "@testing-library/dom";
import { readFileSync } from "node:fs";

import "./scan-progress.ts";
import { store } from "../client/store.ts";
import { mount, resetDocument } from "../test/elements.ts";
import { makeProgress, makeScan } from "../test/fixtures.ts";

const RUNNING = [
  { done: 3400, source: "npm-cache", total: 12_000 },
  { done: 57, source: "pip-cache", total: null },
];

function loading(progress = makeProgress()): HTMLElement {
  const element = mount("scan-progress", { variant: "loading" });
  store.set({ progress });
  return element;
}

function refreshing(generatedAt = "2026-10-11T14:00:00Z"): void {
  store.set({ scan: { kind: "ready", refreshError: null, refreshing: true, scan: makeScan({ generatedAt }) } });
}

function fill(): HTMLElement | null {
  return screen.getByRole("progressbar").querySelector("span");
}

beforeEach(() => {
  resetDocument();
});

describe("scan-progress variant=loading", () => {
  it("renders nothing before the first progress reply", () => {
    expect(mount("scan-progress", { variant: "loading" })).toBeEmptyDOMElement();
  });

  it("shows the bar, the step N/M, the item count and each running source", () => {
    loading(makeProgress({ itemsFound: 9120, running: RUNNING, sourcesDone: 14 }));
    const bar = screen.getByRole("progressbar", { name: "Sources scanned" });
    expect(bar).toHaveAttribute("aria-valuenow", "14");
    expect(bar).toHaveAttribute("aria-valuemax", "26");
    expect(document.querySelector(".scan-live-loading")).not.toBeNull();
    expect(screen.getByText("14/26")).toBeInTheDocument();
    expect(screen.getByLabelText("9120 items")).toHaveTextContent("Σ 9120");
    expect(screen.getByText("npm-cache 3400/12000")).toBeInTheDocument();
    expect(screen.getByText("pip-cache 57")).toBeInTheDocument();
  });

  it("follows each progress reply and clears once the scan is ready", () => {
    const element = loading(makeProgress({ sourcesDone: 1 }));
    store.set({ progress: makeProgress({ sourcesDone: 2 }) });
    expect(screen.getByText("2/26")).toBeInTheDocument();
    store.set({ scan: { kind: "ready", refreshError: null, refreshing: false, scan: makeScan() } });
    expect(element).toBeEmptyDOMElement();
  });

  it("hides a running source until it has counted something or knows its total", () => {
    loading(
      makeProgress({
        running: [
          { done: 0, source: "npm-cache", total: null },
          { done: 0, source: "user-app", total: 40 },
          { done: 5, source: "pip-cache", total: null },
        ],
      }),
    );
    expect(screen.queryByText("npm-cache 0")).toBeNull();
    expect(screen.getByText("user-app 0/40")).toBeInTheDocument();
    expect(screen.getByText("pip-cache 5")).toBeInTheDocument();
  });

  it("keeps the running list's own fixed-height box, empty or full, so nothing moves", () => {
    loading(makeProgress({ running: [] }));
    expect(screen.getByRole("list")).toHaveClass("scan-running");
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
    store.set({ progress: makeProgress({ running: RUNNING }) });
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("reserves a fixed height for the running list in the stylesheet", () => {
    const progressCss = readFileSync("src/styles/progress.css", "utf8");
    expect(/\.scan-running\s*\{[^}]*(?<![-\w])height:/u.exec(progressCss)).not.toBeNull();
  });

  it.each([
    [13, 26, "50%"],
    [0, 0, "0%"],
    [30, 26, "100%"],
  ])("fills the bar for %i of %i sources to %s", (sourcesDone, sourcesTotal, width) => {
    loading(makeProgress({ sourcesDone, sourcesTotal }));
    expect(fill()).toHaveStyle({ width });
  });
});

describe("scan-progress variant=header", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-11T14:05:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders nothing unless a rescan is running", () => {
    const element = mount("scan-progress", { variant: "header" });
    store.set({ scan: { kind: "ready", refreshError: null, refreshing: false, scan: makeScan() } });
    expect(element).toBeEmptyDOMElement();
  });

  it("shows the counts, the running sources and the age of the shown scan", () => {
    mount("scan-progress", { variant: "header" });
    refreshing();
    store.set({ progress: makeProgress({ running: RUNNING.slice(0, 1), sourcesDone: 14 }) });
    expect(document.querySelector("p.scan-live")).not.toBeNull();
    expect(screen.getByLabelText("Rescan progress")).toHaveTextContent(/^14\/26$/u);
    expect(screen.getByLabelText("Scan age")).toHaveTextContent("5m");
  });

  it("leaves a running source out until it has counted something", () => {
    mount("scan-progress", { variant: "header" });
    refreshing();
    store.set({ progress: makeProgress({ running: [{ done: 0, source: "npm-cache", total: null }, ...RUNNING.slice(1)] }) });
    expect(screen.getByLabelText("Rescan progress")).toHaveTextContent(/^0\/26$/u);
  });

  it("shows only the age before the first progress reply and keeps it current", () => {
    mount("scan-progress", { variant: "header" });
    refreshing();
    expect(screen.queryByLabelText("Rescan progress")).toBeNull();
    expect(screen.getByLabelText("Scan age")).toHaveTextContent("5m");
    vi.advanceTimersByTime(60_000);
    expect(screen.getByLabelText("Scan age")).toHaveTextContent("6m");
  });

  it("drops the age when the scan time does not parse", () => {
    mount("scan-progress", { variant: "header" });
    refreshing("garbage");
    store.set({ progress: makeProgress() });
    expect(screen.queryByLabelText("Scan age")).toBeNull();
  });

  it("stops its clock when the rescan ends or the element leaves", () => {
    const element = mount("scan-progress", { variant: "header" });
    refreshing();
    expect(vi.getTimerCount()).toBe(1);
    store.set({ scan: { kind: "ready", refreshError: null, refreshing: false, scan: makeScan() } });
    expect(vi.getTimerCount()).toBe(0);
    expect(element).toBeEmptyDOMElement();
    refreshing();
    element.remove();
    expect(vi.getTimerCount()).toBe(0);
  });
});
