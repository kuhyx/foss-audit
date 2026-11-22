import { CHROME, DEAD_LAUNCHER, FIRMWARE, ITEMS, makeItem, MYSTERY, OWN_SCRIPT, STEAM_GAME } from "../test/fixtures.ts";
import { rankLabel, rankPlace, rankTotals, unrankedLabel } from "./rank.ts";
import { isToReplace } from "./verdict.ts";

describe("isToReplace", () => {
  it("is true for non-free and partly-FOSS items that are not kuhy's own", () => {
    expect(ITEMS.filter((item) => isToReplace(item)).map((item) => item.name)).toEqual([
      "google-chrome",
      "unrar",
      "Some Game",
      "linux-firmware",
      "unar",
      "mystery",
    ]);
    expect(isToReplace(makeItem({ own: true, verdict: "nonfree" }))).toBe(false);
    expect(isToReplace(OWN_SCRIPT)).toBe(false);
  });
});

describe("rankTotals", () => {
  it("is the highest rank present in each column", () => {
    expect(rankTotals(ITEMS)).toEqual({ effort: 4, fit: 4 });
    expect(rankTotals([])).toEqual({ effort: 0, fit: 0 });
    expect(rankTotals([makeItem({ effortRank: 7, fitRank: 2 }), makeItem({ effortRank: 3 })])).toEqual({ effort: 7, fit: 2 });
  });
});

describe("rankLabel", () => {
  const totals = { effort: 4, fit: 4 };

  it("speaks the meaning of the column and the place in the ranking", () => {
    expect(rankLabel("fit", CHROME, totals)).toBe("Fit: Drop-in, rank 2 of 4");
    expect(rankLabel("effort", CHROME, totals)).toBe("Effort: XL · infeasible, rank 2 of 4");
    expect(rankLabel("fit", FIRMWARE, totals)).toBe("Fit: None, rank 4 of 4");
    expect(rankLabel("effort", STEAM_GAME, totals)).toBe("Effort: unknown, rank 3 of 4");
  });

  it("is null without a rank", () => {
    expect(rankLabel("fit", DEAD_LAUNCHER, totals)).toBeNull();
    expect(rankLabel("effort", MYSTERY, totals)).toBeNull();
  });

  it("names the place and the warning glyph", () => {
    expect(rankPlace(3, 15)).toBe("rank 3 of 15");
    expect(unrankedLabel("fit")).toBe("Fit: not ranked yet");
    expect(unrankedLabel("effort")).toBe("Effort: not ranked yet");
  });
});
