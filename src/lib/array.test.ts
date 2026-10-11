import { elementAt } from "./array.ts";

describe("elementAt", () => {
  it("returns the element at a valid index", () => {
    expect(elementAt(["a", "b"], 1)).toBe("b");
  });

  it("throws on an out-of-range index", () => {
    expect(() => elementAt(["a"], 3)).toThrow(RangeError);
  });
});
