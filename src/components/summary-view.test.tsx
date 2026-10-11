import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ITEMS } from "../test/fixtures.ts";
import { SummaryView } from "./summary-view.tsx";

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

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", WideObserver);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SummaryView", () => {
  it("shows the headline split and one tile per verdict", () => {
    render(<SummaryView items={ITEMS} onDrill={vi.fn()} />);
    expect(screen.getByText("44.4% free")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "4 free" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "5 not free" })).toBeInTheDocument();
    expect(screen.getByTestId("count-nonfree")).toHaveTextContent("5");
    expect(screen.getByTestId("count-foss")).toHaveTextContent("3");
    const sum = ["foss", "foss-partial", "nonfree"]
      .map((v) => Number(screen.getByTestId(`count-${v}`).textContent))
      .reduce((a, b) => a + b, 0);
    expect(sum).toBe(ITEMS.length);
  });

  it("drills into the table from tiles and the headline", async () => {
    const user = userEvent.setup();
    const onDrill = vi.fn();
    render(<SummaryView items={ITEMS} onDrill={onDrill} />);
    await user.click(screen.getByRole("button", { name: /^Non-free/u }));
    expect(onDrill).toHaveBeenLastCalledWith(["nonfree"], []);
    await user.click(screen.getByRole("button", { name: "5 not free" }));
    expect(onDrill).toHaveBeenLastCalledWith(["nonfree"], []);
    await user.click(screen.getByRole("button", { name: "4 free" }));
    expect(onDrill).toHaveBeenLastCalledWith(["foss", "foss-partial"], []);
  });

  it("drills from a source label, a segment click and a segment Enter/Space", async () => {
    const user = userEvent.setup();
    const onDrill = vi.fn();
    render(<SummaryView items={ITEMS} onDrill={onDrill} />);
    await user.click(screen.getByRole("button", { name: "steam" }));
    expect(onDrill).toHaveBeenLastCalledWith([], ["steam"]);

    const segment = screen.getByRole("button", { name: /^pacman, Non-free: 2 of 5/u });
    await user.click(segment);
    expect(onDrill).toHaveBeenLastCalledWith(["nonfree"], ["pacman"]);

    onDrill.mockClear();
    fireEvent.keyDown(segment, { key: "x" });
    expect(onDrill).not.toHaveBeenCalled();
    fireEvent.keyDown(segment, { key: "Enter" });
    fireEvent.keyDown(segment, { key: " " });
    expect(onDrill).toHaveBeenCalledTimes(2);
  });

  it("shows a tooltip on hover and focus, hides it on leave and blur", () => {
    render(<SummaryView items={ITEMS} onDrill={vi.fn()} />);
    const segment = screen.getByRole("button", { name: /^pacman, FOSS: 2 of 5/u });
    fireEvent.mouseEnter(segment);
    expect(screen.getByRole("status")).toHaveTextContent("2 of 5 · 40%");
    fireEvent.mouseLeave(segment);
    expect(screen.queryByRole("status")).toBeNull();
    fireEvent.focus(segment);
    expect(screen.getByRole("status")).toHaveTextContent("pacman");
    fireEvent.blur(segment);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("draws a legend entry per verdict and rounds only each bar's last segment", () => {
    render(<SummaryView items={ITEMS} onDrill={vi.fn()} />);
    expect(screen.getByRole("list", { name: "Legend" }).children).toHaveLength(3);
    const pacman = screen.getByRole("group", { name: "pacman by verdict" });
    const paths = [...pacman.querySelectorAll("path")].map((p) => p.getAttribute("d") ?? "");
    expect(paths.at(-1)).toContain("Q");
    expect(paths.slice(0, -1).every((d) => !d.includes("Q"))).toBe(true);
  });

  it("copes with an empty scan", () => {
    render(<SummaryView items={[]} onDrill={vi.fn()} />);
    expect(screen.getByText("0% free")).toBeInTheDocument();
  });
});
