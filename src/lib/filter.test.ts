import type { FilterState } from "./filter.ts";

import {
  CHROME,
  ITEMS,
  makeAlternative,
  makeItem,
  MYSTERY,
  ORPHAN_LIB,
  STEAM_GAME,
  UNRAR,
} from "../test/fixtures.ts";
import {
  applyFilter,
  DEFAULT_FILTER,
  isFilterActive,
  matchesQuery,
  passesFilter,
  toggleMember,
} from "./filter.ts";

function names(filter: Partial<FilterState>): string[] {
  return applyFilter(ITEMS, { ...DEFAULT_FILTER, ...filter }).map((item) => item.name);
}

describe("matchesQuery", () => {
  it("matches everything for an empty or blank query", () => {
    expect(matchesQuery(CHROME, "")).toBe(true);
    expect(matchesQuery(CHROME, ' '.repeat(3))).toBe(true);
  });

  it("fuzzy-matches the name, licence and alternative names", () => {
    expect(matchesQuery(CHROME, "gchrm")).toBe(true);
    expect(matchesQuery(CHROME, "custom:ch")).toBe(true);
    expect(matchesQuery(CHROME, "firefox")).toBe(true);
  });

  it("does not search the free-text reason", () => {
    const item = makeItem({ license: "MIT", name: "xorgproto", reason: "certainly harmless outright mostly evidence" });
    expect(matchesQuery(item, "chrome")).toBe(false);
  });

  it("does not let a match span two fields", () => {
    expect(matchesQuery(CHROME, "chromecustom")).toBe(false);
  });

  it("is false for an item without an alternative when nothing matches", () => {
    expect(matchesQuery(MYSTERY, "zzz")).toBe(false);
  });
});

describe("passesFilter / applyFilter", () => {
  it("passes everything with the default filter", () => {
    expect(names({})).toHaveLength(ITEMS.length);
  });

  it("filters by verdict and source (multi-select is OR within a group)", () => {
    expect(names({ verdicts: ["nonfree"] })).toEqual(["google-chrome", "unrar", "Some Game"]);
    expect(names({ sources: ["aur", "steam"] })).toEqual(["google-chrome", "Some Game"]);
    expect(names({ sources: ["pacman"], verdicts: ["nonfree"] })).toEqual(["unrar"]);
  });

  it("filters explicit vs dependency", () => {
    expect(names({ kind: "dependency" })).toEqual(["unrar", "libfoo"]);
    expect(names({ kind: "explicit" })).not.toContain("unrar");
  });

  it("filters orphans", () => {
    expect(names({ orphan: "yes" })).toEqual([ORPHAN_LIB.name]);
    expect(names({ orphan: "no" })).not.toContain(ORPHAN_LIB.name);
  });

  it("treats an alternative with no names as no alternative", () => {
    const empty = makeItem({ alternative: makeAlternative({ names: [] }), name: "redist" });
    const filter = { ...DEFAULT_FILTER, hasAlt: "yes" as const };
    expect(passesFilter(empty, filter)).toBe(false);
    expect(passesFilter(CHROME, filter)).toBe(true);
    expect(passesFilter(empty, { ...DEFAULT_FILTER, hasAlt: "no" })).toBe(true);
  });

  it("filters on an alternative being installed", () => {
    expect(names({ altInstalled: "yes" })).toEqual([CHROME.name, UNRAR.name, STEAM_GAME.name]);
    expect(names({ altInstalled: "no" })).not.toContain(CHROME.name);
  });

  it("combines the search with the facets", () => {
    expect(names({ query: "unrar", verdicts: ["nonfree"] })).toEqual(["unrar"]);
  });
});

describe("isFilterActive", () => {
  it("is false only for the default filter", () => {
    expect(isFilterActive(DEFAULT_FILTER)).toBe(false);
    const variants: Partial<FilterState>[] = [
      { query: "x" },
      { verdicts: ["foss"] },
      { sources: ["aur"] },
      { kind: "explicit" },
      { orphan: "yes" },
      { hasAlt: "no" },
      { altInstalled: "yes" },
    ];
    for (const variant of variants) {
      expect(isFilterActive({ ...DEFAULT_FILTER, ...variant })).toBe(true);
    }
  });
});

describe("toggleMember", () => {
  const vocabulary = ["a", "b", "c"] as const;

  it("adds a member in vocabulary order", () => {
    expect(toggleMember(["c"], "a", vocabulary)).toEqual(["a", "c"]);
  });

  it("removes a present member", () => {
    expect(toggleMember(["a", "c"], "a", vocabulary)).toEqual(["c"]);
  });
});
