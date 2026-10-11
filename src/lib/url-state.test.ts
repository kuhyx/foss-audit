import type { UrlState } from "./url-state.ts";

import { decodeState, DEFAULT_STATE, encodeState } from "./url-state.ts";

describe("URL state", () => {
  it("encodes the default state as an empty query", () => {
    expect(encodeState(DEFAULT_STATE)).toBe("");
    expect(decodeState("")).toEqual(DEFAULT_STATE);
  });

  it("round-trips every field", () => {
    const state: UrlState = {
      filter: {
        altInstalled: "yes",
        hasAlt: "no",
        kind: "dependency",
        loose: "no",
        orphan: "yes",
        own: "yes",
        query: "chrome & co",
        sources: ["aur", "steam"],
        verdicts: ["foss", "nonfree"],
      },
      selected: "aur:google-chrome",
      sort: { desc: true, id: "name" },
      view: "table",
    };
    const query = encodeState(state);
    expect(query).toContain("v=foss,nonfree");
    expect(query).toContain("sort=-name");
    expect(decodeState(`?${query}`)).toEqual(state);
  });

  it("writes an ascending sort without a dash", () => {
    const query = encodeState({ ...DEFAULT_STATE, sort: { desc: false, id: "fit" } });
    expect(query).toBe("sort=fit");
    expect(decodeState(query).sort).toEqual({ desc: false, id: "fit" });
  });

  it("drops unknown or malformed values instead of throwing", () => {
    const state = decodeState("?view=nope&v=nonfree,bogus&src=&kind=maybe&orphan=1&sort=-");
    expect(state.view).toBe("summary");
    expect(state.filter.verdicts).toEqual(["nonfree"]);
    expect(state.filter.sources).toEqual([]);
    expect(state.filter.kind).toBe("any");
    expect(state.filter.orphan).toBe("any");
    expect(state.sort).toBeNull();
  });

  it("ignores verdict values removed from the vocabulary (old links)", () => {
    expect(decodeState("?v=own,blob,unknown").filter.verdicts).toEqual([]);
    expect(decodeState("?v=blob,nonfree,own").filter.verdicts).toEqual(["nonfree"]);
    expect(decodeState("?own=maybe").filter.own).toBe("any");
    expect(decodeState("?loose=maybe").filter.loose).toBe("any");
  });

  it("treats an empty sort as no sort", () => {
    expect(decodeState("?sort=").sort).toBeNull();
  });

  it("keeps multi-select members in vocabulary order", () => {
    expect(decodeState("?v=nonfree,foss").filter.verdicts).toEqual(["foss", "nonfree"]);
  });
});
