import { formatAge } from "./age.ts";

const NOW = Date.parse("2026-10-11T14:00:00Z");

describe("formatAge", () => {
  it.each([
    ["2026-10-11T13:59:59Z", "1s"],
    ["2026-10-11T13:59:15Z", "45s"],
    ["2026-10-11T13:56:00Z", "4m"],
    ["2026-10-11T11:00:00Z", "3h"],
    ["2026-10-09T14:00:00Z", "2d"],
  ])("%s is %s old", (iso, expected) => {
    expect(formatAge(iso, NOW)).toBe(expected);
  });

  it("clamps a timestamp in the future to 0s", () => {
    expect(formatAge("2026-10-11T14:00:05Z", NOW)).toBe("0s");
  });

  it("is empty for an unparseable timestamp", () => {
    expect(formatAge("garbage", NOW)).toBe("");
  });
});
