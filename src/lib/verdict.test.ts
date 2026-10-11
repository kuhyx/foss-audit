import {
  CHROME,
  ITEMS,
  makeAlternative,
  makeItem,
  PARTIAL,
  STEAM_GAME,
  UNRAR,
} from "../test/fixtures.ts";
import { countBy, FREE_VERDICTS, hasTrackedDependants, isEasyWin, percent } from "./verdict.ts";

describe("isEasyWin", () => {
  it("accepts non-free with a drop-in or good alternative already installed", () => {
    expect(isEasyWin(CHROME)).toBe(true);
    expect(isEasyWin(UNRAR)).toBe(true);
  });

  it("accepts foss-partial items too", () => {
    const item = { ...PARTIAL, alternative: makeAlternative({ installed: ["7zip"] }) };
    expect(isEasyWin(item)).toBe(true);
  });

  it.each(["partial", "none"] as const)("excludes fit %s", (fit) => {
    expect(isEasyWin({ ...CHROME, alternative: makeAlternative({ fit, installed: ["x"] }) })).toBe(false);
  });

  it("excludes items whose alternative is not installed", () => {
    expect(isEasyWin({ ...CHROME, alternative: makeAlternative({ installed: [] }) })).toBe(false);
  });

  it("excludes items without an alternative (e.g. Proton after curation)", () => {
    expect(isEasyWin({ ...CHROME, alternative: null })).toBe(false);
  });

  it.each(["foss", "blob", "own", "unknown"] as const)("excludes verdict %s", (verdict) => {
    expect(isEasyWin({ ...CHROME, verdict })).toBe(false);
  });
});

describe("hasTrackedDependants", () => {
  it("is true only for pacman and AUR packages", () => {
    expect(hasTrackedDependants(UNRAR)).toBe(true);
    expect(hasTrackedDependants(CHROME)).toBe(true);
    expect(hasTrackedDependants(STEAM_GAME)).toBe(false);
  });
});

describe("summary math", () => {
  it("counts by key", () => {
    const counts = countBy(ITEMS, (item) => item.verdict);
    expect(Object.fromEntries(counts)).toEqual({
      blob: 1,
      foss: 2,
      "foss-partial": 1,
      nonfree: 3,
      own: 1,
      unknown: 1,
    });
    const total = counts.values().reduce((sum, n) => sum + n, 0);
    expect(total).toBe(ITEMS.length);
  });

  it("splits free (foss, own, foss-partial) from the rest", () => {
    const free = ITEMS.filter((item) => FREE_VERDICTS.has(item.verdict));
    expect(free).toHaveLength(4);
    expect(FREE_VERDICTS.has("nonfree")).toBe(false);
  });

  it("formats percentages", () => {
    expect(percent(1, 0)).toBe("0%");
    expect(percent(0, 10)).toBe("0%");
    expect(percent(1, 3138)).toBe("<0.1%");
    expect(percent(44, 3138)).toBe("1.4%");
    expect(percent(2968, 3138)).toBe("95%");
    expect(percent(1, 1)).toBe("100%");
  });

  it("counts an item without overrides as foss", () => {
    expect(makeItem().verdict).toBe("foss");
  });
});
