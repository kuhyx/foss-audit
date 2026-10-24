import { compileQuery, maxTypos } from "./fuzzy.ts";

const FIREBASE = ["firebase-common", "maven-cache:com.google.firebase:firebase-common"];

function rank(query: string, fields: readonly string[] = FIREBASE): null | number {
  return compileQuery(query).rank(fields);
}

describe("maxTypos", () => {
  it("allows no typo under 4 characters, one up to 7 and two from 8", () => {
    expect([1, 3, 4, 7, 8, 20].map((length) => maxTypos("x".repeat(length)))).toEqual([0, 0, 1, 1, 2, 2]);
  });
});

describe("compileQuery", () => {
  it("ranks every field set 0 for an empty or blank query", () => {
    expect(rank("")).toBe(0);
    expect(rank(" ".repeat(3), [])).toBe(0);
  });

  it("ranks a case-insensitive substring of any field 0", () => {
    expect(rank("FireBase")).toBe(0);
    expect(rank("maven-cache:com.google")).toBe(0);
    expect(rank("e:com")).toBe(0);
  });

  it("ranks a word match within the typo budget 1", () => {
    expect(rank("firbase")).toBe(1); // deletion
    expect(rank("firebsae")).toBe(1); // transposition = 2 edits, 8 chars
    expect(rank("firexase")).toBe(1); // substitution
    expect(rank("google firebase")).toBe(1); // words may sit apart
    expect(rank("common  google")).toBe(1);
  });

  it("ranks a typo hit 2 when a match starts off the word's first letter", () => {
    expect(rank("firbase", ["io.airlift:airbase"])).toBe(2);
    expect(rank("firbase", ["fx", "airbase"])).toBe(2); // the f leads nowhere
    expect(rank("firbase base", ["airbase"])).toBe(2);
    expect(rank("firbase")).toBe(1);
  });

  it("rejects a word over its typo budget", () => {
    expect(rank("fribsae")).toBeNull(); // 7 chars, 2+ edits
    expect(rank("fyrybasz")).toBeNull(); // 8 chars, 3 edits
    expect(rank("qzqz")).toBeNull(); // 4 chars, 3+ edits
    expect(rank("fbx")).toBeNull(); // short words need an exact hit
  });

  it("needs every word to match", () => {
    expect(rank("firebase zzzz")).toBeNull();
  });

  it("does not match letters that are merely in order", () => {
    const qemu = ["qemu-audio-alsa", "pacman:qemu-audio-alsa"];
    expect(rank("firebase", qemu)).toBeNull();
    expect(rank("firebase", ["BSD-2-Clause BSD-2-Clause-Patent BSD-3-Clause CC0-1.0 FSFAP GPL-1.0-or-later GPL-2.0-only GPL-2.0-only WITH Linux-syscall-note GPL-2.0-only WITH Linux-syscall-note OR BSD-2-Clause GPL-2.0-only WITH Linux-syscall-note OR BSD-3-Clause"])).toBeNull();
  });

  it("falls back to an exact hit for words longer than 32 characters", () => {
    const long = "a".repeat(40);
    expect(rank(`${long} x`, [`${long}-x`])).toBe(1);
    expect(rank(`${long.slice(1)}b x`, [`${long}-x`])).toBeNull();
  });

  it("matches non-ASCII characters", () => {
    expect(rank("zażółć", ["Zażółć gęślą"])).toBe(0);
    expect(rank("zażółx gęślą", ["Zażółć gęślą"])).toBe(1);
  });
});

describe("speed", () => {
  // Best of 5 after a warm-up: the gate is the matcher's cost, not the noise
  // of a CPU-capped, coverage-instrumented run sharing cores with 30 files.
  it("filters 13k items in well under 200 ms", () => {
    const fields = Array.from({ length: 13_000 }, (_, index) => {
      const name = `package-${index.toString(36)}-${"lib".repeat(index % 7)}`;
      return [name, `maven-cache:org.example.group${index % 97}:${name}`];
    });
    for (const query of ["firbase", "com.google firebase"]) {
      const compiled = compileQuery(query);
      const timings = Array.from({ length: 6 }, () => {
        const started = performance.now();
        expect(fields.filter((pair) => compiled.rank(pair) !== null)).toEqual([]);
        return performance.now() - started;
      });
      expect(Math.min(...timings.slice(1))).toBeLessThan(200);
    }
  });
});
