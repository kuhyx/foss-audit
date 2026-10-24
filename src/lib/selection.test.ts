import { clickRow, EMPTY_SELECTION, headerCheck, setRows } from "./selection.ts";

const ORDER = ["a", "b", "c", "d", "e"];

function ids(state: { ids: ReadonlySet<string> }): string[] {
  return [...state.ids].toSorted((a, b) => a.localeCompare(b));
}

describe("clickRow", () => {
  it("toggles one row and makes it the anchor", () => {
    const on = clickRow(EMPTY_SELECTION, "b", ORDER, false);
    expect(ids(on)).toEqual(["b"]);
    expect(on.anchor).toBe("b");
    const off = clickRow(on, "b", ORDER, false);
    expect(ids(off)).toEqual([]);
    expect(off.anchor).toBe("b");
  });

  it("shift-selects the inclusive range from the anchor, in either direction", () => {
    const down = clickRow(clickRow(EMPTY_SELECTION, "b", ORDER, false), "d", ORDER, true);
    expect(ids(down)).toEqual(["b", "c", "d"]);
    expect(down.anchor).toBe("d");
    const up = clickRow(clickRow(EMPTY_SELECTION, "e", ORDER, false), "c", ORDER, true);
    expect(ids(up)).toEqual(["c", "d", "e"]);
  });

  it("follows the order it is given, not the order rows were added", () => {
    const sorted = ["e", "a", "c", "b", "d"];
    const state = clickRow(clickRow(EMPTY_SELECTION, "a", sorted, false), "b", sorted, true);
    expect(ids(state)).toEqual(["a", "b", "c"]);
  });

  it("always selects a shift range, even onto rows that are already selected", () => {
    const some = { anchor: "a", ids: new Set(["c", "hidden"]) };
    expect(ids(clickRow(some, "c", ORDER, true))).toEqual(["a", "b", "c", "hidden"]);
  });

  it("treats shift-click as a plain toggle without a visible anchor", () => {
    expect(ids(clickRow(EMPTY_SELECTION, "c", ORDER, true))).toEqual(["c"]);
    const hidden = { anchor: "z", ids: new Set(["z"]) };
    expect(ids(clickRow(hidden, "c", ORDER, true))).toEqual(["c", "z"]);
  });

  it("keeps ids outside the current order", () => {
    const state = clickRow({ anchor: null, ids: new Set(["hidden"]) }, "a", ORDER, false);
    expect(ids(state)).toEqual(["a", "hidden"]);
  });
});

describe("setRows", () => {
  it("adds or removes many ids and leaves the others alone", () => {
    const state = setRows({ anchor: "x", ids: new Set(["hidden"]) }, ["a", "b"], true);
    expect(ids(state)).toEqual(["a", "b", "hidden"]);
    expect(state.anchor).toBe("x");
    expect(ids(setRows(state, ["a", "hidden"], false))).toEqual(["b"]);
  });
});

describe("headerCheck", () => {
  it("is all, some or none of the shown rows", () => {
    expect(headerCheck(new Set(["a", "b"]), ["a", "b"])).toBe("all");
    expect(headerCheck(new Set(["a", "hidden"]), ["a", "b"])).toBe("some");
    expect(headerCheck(new Set(["hidden"]), ["a", "b"])).toBe("none");
    expect(headerCheck(new Set(["a"]), [])).toBe("none");
  });
});
