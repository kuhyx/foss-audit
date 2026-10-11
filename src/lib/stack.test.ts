import { ITEMS, makeItem } from "../test/fixtures.ts";
import { layoutSegments, MIN_SEGMENT, roundedEndPath, sourceRows } from "./stack.ts";

describe("sourceRows", () => {
  it("groups by source, largest first, ties by name", () => {
    const rows = sourceRows(ITEMS);
    expect(rows.map((row) => [row.source, row.total])).toEqual([
      ["pacman", 5],
      ["aur", 1],
      ["local-bin", 1],
      ["opt", 1],
      ["steam", 1],
    ]);
    expect(rows[0]?.counts.get("foss")).toBe(2);
  });
});

describe("layoutSegments", () => {
  it("spans the full width in verdict order, proportionally", () => {
    const items = [
      ...Array.from({ length: 3 }, (_, index) => makeItem({ name: `f${index}` })),
      makeItem({ name: "n", verdict: "nonfree" }),
    ];
    const [row] = sourceRows(items);
    const segments = layoutSegments(row!, 400);
    expect(segments.map((s) => [s.verdict, s.x, s.width])).toEqual([
      ["foss", 0, 300],
      ["nonfree", 300, 100],
    ]);
  });

  it("raises slivers to the minimum width and keeps the total", () => {
    const items = [
      ...Array.from({ length: 999 }, (_, index) => makeItem({ name: `f${index}` })),
      makeItem({ name: "b", verdict: "blob" }),
    ];
    const segments = layoutSegments(sourceRows(items)[0]!, 500);
    const blob = segments.find((s) => s.verdict === "blob");
    expect(blob?.width).toBe(MIN_SEGMENT);
    expect(segments.reduce((sum, s) => sum + s.width, 0)).toBeCloseTo(500);
  });

  it("gives every segment the minimum when all are slivers", () => {
    const [row] = sourceRows([makeItem()]);
    expect(layoutSegments(row!, 3)).toEqual([{ count: 1, verdict: "foss", width: MIN_SEGMENT, x: 0 }]);
  });
});

describe("roundedEndPath", () => {
  it("rounds only the right-hand end", () => {
    expect(roundedEndPath(0, 0, 100, 18, 4)).toBe(
      "M0,0 H96 Q100,0 100,4 V14 Q100,18 96,18 H0 Z",
    );
  });

  it("clamps the radius for tiny segments", () => {
    expect(roundedEndPath(10, 0, 4, 18, 4)).toBe("M10,0 H12 Q14,0 14,2 V16 Q14,18 12,18 H10 Z");
  });
});
