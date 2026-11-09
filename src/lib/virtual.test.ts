import { arrowTarget, OVERSCAN, ROW_HEIGHT, scrollTopToReveal, visibleRange } from "./virtual.ts";

describe("visibleRange", () => {
  it("mounts the viewport plus overscan from the top", () => {
    expect(visibleRange(0, 800, 1000)).toEqual({ end: 19 + OVERSCAN, start: 0 });
  });

  it("slides with the scroll position", () => {
    const top = 100 * ROW_HEIGHT;
    expect(visibleRange(top, 800, 1000)).toEqual({ end: 119 + OVERSCAN, start: 100 - OVERSCAN });
  });

  it("clamps to the row count, to zero rows and to a negative scroll", () => {
    expect(visibleRange(0, 800, 5)).toEqual({ end: 5, start: 0 });
    expect(visibleRange(0, 800, 0)).toEqual({ end: 0, start: 0 });
    expect(visibleRange(-50, 800, 100).start).toBe(0);
    expect(visibleRange(99_999, 800, 10)).toEqual({ end: 10, start: 10 });
  });

  it("copes with a viewport shorter than the header", () => {
    expect(visibleRange(0, 10, 100)).toEqual({ end: OVERSCAN, start: 0 });
  });
});

describe("scrollTopToReveal", () => {
  it("leaves the scroll alone when the row is already visible", () => {
    expect(scrollTopToReveal(3, 0, 800)).toBe(0);
  });

  it("scrolls up so the row sits right under the header", () => {
    expect(scrollTopToReveal(2, 400, 800)).toBe(2 * ROW_HEIGHT);
  });

  it("scrolls down just enough to show the whole row", () => {
    expect(scrollTopToReveal(30, 0, 800)).toBe(31 * ROW_HEIGHT - 760);
  });
});

describe("arrowTarget", () => {
  it("starts at an end when nothing is current", () => {
    expect(arrowTarget(-1, 5, "ArrowDown")).toBe(0);
    expect(arrowTarget(-1, 5, "ArrowUp")).toBe(4);
  });

  it("moves one row and clamps at both ends", () => {
    expect(arrowTarget(2, 5, "ArrowDown")).toBe(3);
    expect(arrowTarget(2, 5, "ArrowUp")).toBe(1);
    expect(arrowTarget(4, 5, "ArrowDown")).toBe(4);
    expect(arrowTarget(0, 5, "ArrowUp")).toBe(0);
  });
});
