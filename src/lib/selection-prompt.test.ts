import { CHROME, FIRMWARE, ITEMS, makeItem, PARTIAL, STEAM_GAME, UNRAR } from "../test/fixtures.ts";
import { buildBulkPrompt } from "./claude-prompt.ts";
import { buildSelectionPrompt, groupItems } from "./selection-prompt.ts";

const BASH = makeItem();
const CHROME_BETA = { ...CHROME, id: "aur:google-chrome-beta", name: "google-chrome-beta" };

function maven(artifact: string, group = "com.google.android.gms") {
  return makeItem({ name: `${group}:${artifact}`, removeCommand: null, source: "maven-cache", verdict: "nonfree" });
}

function npm(name: string) {
  return makeItem({ name, source: "npm-cache", verdict: "nonfree" });
}

function headings(text: string): string[] {
  return text.split("\n").filter((line) => line.startsWith("### "));
}

describe("groupItems", () => {
  it("groups by shared curated alternative first, then namespace, else alone", () => {
    const gmsBase = maven("play-services-base");
    const gmsAds = maven("play-services-ads");
    const firebase = maven("firebase-core", "com.google.firebase");
    const groups = groupItems([CHROME, gmsBase, npm("@sentry/core"), CHROME_BETA, gmsAds, firebase, npm("@sentry/node"), UNRAR]);
    expect(groups.map((group) => [group.label, group.items.map((item) => item.name)])).toEqual([
      ["shared alternative Chromium, Firefox", ["google-chrome", "google-chrome-beta"]],
      ["namespace com.google.android.gms", ["com.google.android.gms:play-services-base", "com.google.android.gms:play-services-ads"]],
      ["namespace @sentry", ["@sentry/core", "@sentry/node"]],
      ["com.google.firebase:firebase-core", ["com.google.firebase:firebase-core"]],
      ["unrar", ["unrar"]],
    ]);
  });

  it("does not group by an alternative only one item has, or one with no names", () => {
    const unnamed = { ...UNRAR, alternative: { ...UNRAR.alternative!, names: [] } };
    const unnamed2 = { ...unnamed, id: "pacman:unrar2", name: "unrar2" };
    expect(groupItems([CHROME, unnamed, unnamed2]).map((group) => group.items.length)).toEqual([1, 1, 1]);
  });
});

describe("buildSelectionPrompt", () => {
  const prompt = buildSelectionPrompt([CHROME, BASH, CHROME_BETA]);

  it("is a backlog note that counts what to replace and what is already FOSS", () => {
    expect(prompt.split("\n", 1)[0]).toBe("Work through 3 selected items: 2 to replace, 1 already FOSS");
    for (const heading of ["## what", "## where", "## must", "## done", "## verify", "## known"]) {
      expect(prompt).toContain(heading);
    }
  });

  it("puts the gate once per group and keeps research, suggest, install", () => {
    expect(headings(prompt)).toEqual([
      "### Group 1 of 1: shared alternative Chromium, Firefox (2 items)",
      "### already FOSS: confirm it is still used; if not, print its remove command",
    ]);
    expect(prompt).toMatch(/one group at a time/u);
    expect(prompt).toMatch(/whole group/u);
    expect(prompt).toMatch(/0\. research/u);
    expect(prompt).toMatch(/2\. install/u);
    expect(prompt).toContain("#### google-chrome (`aur:google-chrome`): research, suggest, install");
  });

  it("lists FOSS items with their facts but no research or install steps", () => {
    const foss = prompt.slice(prompt.indexOf("### already FOSS"));
    expect(foss).toContain("#### bash (`pacman:bash`)\n");
    expect(foss).toContain("- id: `pacman:bash`, source: pacman, version: 5.2.0-1");
    expect(foss).toContain("- remove command: `sudo pacman -Rns bash` (do not run it)");
    expect(foss).not.toMatch(/research|install it/u);
  });

  it("carries every fact line, plus removeVia when it is set", () => {
    const text = buildSelectionPrompt([{ ...UNRAR, removeVia: "~/src/sufler via torch" }, PARTIAL]);
    expect(text).toContain("- required by: file-roller");
    expect(text).toContain("- licence: custom:unrar");
    expect(text).toContain("- remove command: `sudo pacman -Rns unrar` (do not run it)\n- remove via: ~/src/sufler via torch");
    expect(text).toContain("#### unar (`pacman:unar`): research, suggest, install");
    expect(text.match(/remove via:/gu)).toHaveLength(1);
  });

  it("keeps the must-not rules", () => {
    expect(prompt).toMatch(/must not: remove, disable or uninstall any of them/u);
    expect(prompt).toMatch(/must not: install anything for a group before I have picked/u);
  });

  it("marks research-only items inside a group", () => {
    const text = buildSelectionPrompt([STEAM_GAME, FIRMWARE]);
    expect(text).toContain("#### Some Game (`steam:Some Game`): research only");
    expect(text).toContain("### Group 2 of 2: linux-firmware");
    expect(text.split("\n", 1)[0]).toBe("Work through 2 selected items: 2 to replace, 0 already FOSS");
    expect(text).not.toContain("### already FOSS");
  });

  it("drops the replace steps when only FOSS items are selected", () => {
    const text = buildSelectionPrompt([BASH]);
    expect(text).toContain("### already FOSS");
    expect(text).not.toMatch(/0\. research|### Group/u);
    expect(text).toMatch(/must not: remove, disable or uninstall any of them/u);
  });
});

describe("the summary view's bulk prompt", () => {
  it("still covers only the non-FOSS items", () => {
    const text = buildBulkPrompt(ITEMS);
    expect(text).not.toContain("already FOSS");
    expect(text).not.toContain("(`pacman:bash`)");
  });
});
