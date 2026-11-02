import { act, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";

import { makeProgress } from "../test/fixtures.ts";
import { HeaderProgress, LoadingProgress } from "./scan-progress.tsx";

const RUNNING = [
  { done: 3400, source: "npm-cache", total: 12_000 },
  { done: 57, source: "pip-cache", total: null },
];

describe("LoadingProgress", () => {
  it("renders nothing before the first progress reply", () => {
    const { container } = render(<LoadingProgress progress={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the bar, the counts and each running source", () => {
    render(<LoadingProgress progress={makeProgress({ itemsFound: 9120, running: RUNNING, sourcesDone: 14 })} />);
    const bar = screen.getByRole("progressbar", { name: "Sources scanned" });
    expect(bar).toHaveAttribute("aria-valuenow", "14");
    expect(bar).toHaveAttribute("aria-valuemax", "26");
    expect(screen.getByText("14/26")).toBeInTheDocument();
    expect(screen.getByText("9120 items")).toBeInTheDocument();
    expect(screen.getByText("npm-cache 3400/12000")).toBeInTheDocument();
    expect(screen.getByText("pip-cache 57")).toBeInTheDocument();
  });

  it("hides a running source until it has counted something or knows its total", () => {
    const running = [
      { done: 0, source: "npm-cache", total: null },
      { done: 0, source: "user-app", total: 40 },
      { done: 5, source: "pip-cache", total: null },
    ];
    render(<LoadingProgress progress={makeProgress({ running })} />);
    expect(screen.queryByText("npm-cache 0")).toBeNull();
    expect(screen.getByText("user-app 0/40")).toBeInTheDocument();
    expect(screen.getByText("pip-cache 5")).toBeInTheDocument();
  });

  it("keeps the running list's own fixed-height box, empty or full, so nothing moves", () => {
    const { rerender } = render(<LoadingProgress progress={makeProgress({ running: [] })} />);
    expect(screen.getByRole("list")).toHaveClass("scan-running");
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
    rerender(<LoadingProgress progress={makeProgress({ running: RUNNING })} />);
    expect(screen.getByRole("list")).toHaveClass("scan-running");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("reserves a fixed height for the running list in the stylesheet", () => {
    // jsdom applies no stylesheet, so read the rule itself.
    const progressCss = readFileSync("src/styles/progress.css", "utf8");
    expect(/\.scan-running\s*\{[^}]*(?<![-\w])height:/.exec(progressCss)).not.toBeNull();
  });

  it("fills the bar in proportion to the sources done", () => {
    render(<LoadingProgress progress={makeProgress({ sourcesDone: 13 })} />);
    expect(screen.getByRole("progressbar").firstElementChild).toHaveStyle({ width: "50%" });
  });

  it("keeps the bar empty when the total is not known yet", () => {
    render(<LoadingProgress progress={makeProgress({ sourcesTotal: 0 })} />);
    expect(screen.getByRole("progressbar").firstElementChild).toHaveStyle({ width: "0%" });
  });

  it("never overfills the bar", () => {
    render(<LoadingProgress progress={makeProgress({ sourcesDone: 30 })} />);
    expect(screen.getByRole("progressbar").firstElementChild).toHaveStyle({ width: "100%" });
  });
});

describe("HeaderProgress", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-11T14:05:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the counts, the running sources and the age of the shown scan", () => {
    render(
      <HeaderProgress
        generatedAt="2026-10-11T14:00:00Z"
        progress={makeProgress({ running: RUNNING.slice(0, 1), sourcesDone: 14 })}
      />,
    );
    expect(screen.getByLabelText("Rescan progress")).toHaveTextContent("14/26 · npm-cache 3400/12000");
    expect(screen.getByLabelText("Scan age")).toHaveTextContent("5m");
  });

  it("leaves a running source out until it has counted something", () => {
    const running = [{ done: 0, source: "npm-cache", total: null }, ...RUNNING.slice(1)];
    render(<HeaderProgress generatedAt="2026-10-11T14:00:00Z" progress={makeProgress({ running })} />);
    expect(screen.getByLabelText("Rescan progress")).toHaveTextContent("0/26 · pip-cache 57");
  });

  it("keeps the age current as time passes", () => {
    render(<HeaderProgress generatedAt="2026-10-11T14:00:00Z" progress={null} />);
    expect(screen.getByLabelText("Scan age")).toHaveTextContent("5m");
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(screen.getByLabelText("Scan age")).toHaveTextContent("6m");
  });

  it("shows only the age before the first progress reply", () => {
    render(<HeaderProgress generatedAt="2026-10-11T14:00:00Z" progress={null} />);
    expect(screen.queryByLabelText("Rescan progress")).toBeNull();
    expect(screen.getByLabelText("Scan age")).toHaveTextContent("5m");
  });

  it("drops the age when the scan time does not parse", () => {
    render(<HeaderProgress generatedAt="garbage" progress={makeProgress()} />);
    expect(screen.queryByLabelText("Scan age")).toBeNull();
  });
});
