import type { FilterState } from "./filter.ts";

import {
  CHROME,
  DEAD_LAUNCHER,
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

const FIREBASE_COMMON = makeItem({
  id: "maven-cache:com.google.firebase:firebase-common",
  license: "Apache-2.0",
  name: "firebase-common",
  source: "maven-cache",
});
// Every letter of "firebase", in order, only across the licence.
const QEMU = makeItem({
  license: "BSD-2-Clause BSD-2-Clause-Patent BSD-3-Clause CC0-1.0 FSFAP GPL-1.0-or-later GPL-2.0-only GPL-2.0-only WITH Linux-syscall-note GPL-2.0-only WITH Linux-syscall-note OR BSD-2-Clause GPL-2.0-only WITH Linux-syscall-note OR BSD-3-Clause",
  name: "qemu-audio-alsa",
});

function names(filter: Partial<FilterState>): string[] {
  return applyFilter(ITEMS, { ...DEFAULT_FILTER, ...filter }).map((item) => item.name);
}

describe("matchesQuery", () => {
  it("matches everything for an empty or blank query", () => {
    expect(matchesQuery(CHROME, "")).toBe(true);
    expect(matchesQuery(CHROME, ' '.repeat(3))).toBe(true);
  });

  it("matches a case-insensitive substring of the name or the id", () => {
    expect(matchesQuery(FIREBASE_COMMON, "firebase")).toBe(true);
    expect(matchesQuery(FIREBASE_COMMON, "FIREBASE-Common")).toBe(true);
    expect(matchesQuery(FIREBASE_COMMON, "maven-cache:com.google")).toBe(true);
    expect(matchesQuery(CHROME, "aur:goo")).toBe(true);
  });

  it("tolerates typos in the name or the id", () => {
    expect(matchesQuery(FIREBASE_COMMON, "firbase")).toBe(true);
    expect(matchesQuery(FIREBASE_COMMON, "firebsae")).toBe(true);
  });

  it("does not search the licence or the alternative names", () => {
    expect(matchesQuery(CHROME, "custom:ch")).toBe(false);
    expect(matchesQuery(CHROME, "firefox")).toBe(false);
  });

  it("does not match letters scattered in order across the licence", () => {
    expect(matchesQuery(QEMU, "firebase")).toBe(false);
  });

  it("does not search the free-text reason", () => {
    const item = makeItem({ license: "MIT", name: "xorgproto", reason: "certainly harmless outright mostly evidence" });
    expect(matchesQuery(item, "chrome")).toBe(false);
  });

  it("is false when nothing matches", () => {
    expect(matchesQuery(MYSTERY, "zzz")).toBe(false);
  });
});

describe("passesFilter / applyFilter", () => {
  it("passes everything with the default filter", () => {
    expect(names({})).toHaveLength(ITEMS.length);
  });

  it("filters by verdict and source (multi-select is OR within a group)", () => {
    expect(names({ verdicts: ["nonfree"] })).toEqual(["google-chrome", "unrar", "Some Game", "linux-firmware", "mystery"]);
    expect(names({ sources: ["aur", "steam"] })).toEqual(["google-chrome", "Some Game"]);
    expect(names({ sources: ["pacman"], verdicts: ["nonfree"] })).toEqual(["unrar", "linux-firmware"]);
  });

  it("filters explicit vs dependency", () => {
    expect(names({ kind: "dependency" })).toEqual(["unrar", "libfoo"]);
    expect(names({ kind: "explicit" })).not.toContain("unrar");
  });

  it("filters orphans", () => {
    expect(names({ orphan: "yes" })).toEqual([ORPHAN_LIB.name]);
    expect(names({ orphan: "no" })).not.toContain(ORPHAN_LIB.name);
  });

  it("filters untracked files", () => {
    expect(names({ loose: "yes" })).toEqual(["mystery"]);
    expect(names({ loose: "no" })).not.toContain("mystery");
  });

  it("filters dead launchers", () => {
    const all = [...ITEMS, DEAD_LAUNCHER];
    const pick = (dangling: "no" | "yes"): string[] =>
      applyFilter(all, { ...DEFAULT_FILTER, dangling }).map((item) => item.name);
    expect(pick("yes")).toEqual(["rpcs3"]);
    expect(pick("no")).not.toContain("rpcs3");
  });

  it("filters own code", () => {
    expect(names({ own: "yes" })).toEqual(["backup.sh"]);
    expect(names({ own: "no" })).not.toContain("backup.sh");
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

  it("shows typo hits only when nothing matches exactly", () => {
    const typo = makeItem({ name: "firbase-tools" });
    const exact = makeItem({ name: "firebase-tools" });
    const all = [typo, QEMU, FIREBASE_COMMON, exact];
    const search = (query: string): string[] =>
      applyFilter(all, { ...DEFAULT_FILTER, query }).map((item) => item.name);
    expect(search("firebase")).toEqual(["firebase-common", "firebase-tools"]);
    expect(search("firxbase")).toEqual(["firbase-tools", "firebase-common", "firebase-tools"]);
  });

  it("ranks typo hits on the first letter before the rest", () => {
    const airbase = makeItem({ name: "airbase" });
    const found = applyFilter([airbase, FIREBASE_COMMON], { ...DEFAULT_FILTER, query: "firbase" });
    expect(found.map((item) => item.name)).toEqual(["firebase-common", "airbase"]);
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
      { own: "yes" },
      { loose: "yes" },
      { dangling: "yes" },
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
