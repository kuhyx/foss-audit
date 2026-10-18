import { CHROME, FIRMWARE, ITEMS, makeAlternative, OWN_SCRIPT, PARTIAL, STEAM_GAME, UNRAR } from "../test/fixtures.ts";
import { buildBulkPrompt, buildItemPrompt, isPromptCandidate, isResearchOnly } from "./claude-prompt.ts";

describe("isPromptCandidate", () => {
  it("takes every item that is not plain FOSS", () => {
    expect(isPromptCandidate(CHROME)).toBe(true);
    expect(isPromptCandidate(PARTIAL)).toBe(true);
    expect(isPromptCandidate(OWN_SCRIPT)).toBe(false);
  });
});

describe("isResearchOnly", () => {
  it("stops firmware and Steam library items after the suggestion step", () => {
    expect(isResearchOnly({ ...FIRMWARE, reason: "firmware blob: amdgpu" })).toBe(true);
    expect(isResearchOnly(STEAM_GAME)).toBe(true);
    expect(isResearchOnly(CHROME)).toBe(false);
  });
});

describe("buildItemPrompt", () => {
  const prompt = buildItemPrompt(CHROME);

  it("is a backlog note: imperative title plus every labelled section", () => {
    expect(prompt.split("\n", 1)[0]).toBe("Replace google-chrome with a FOSS alternative");
    for (const heading of ["## what", "## where", "## known", "## must", "## done", "## verify"]) {
      expect(prompt).toContain(heading);
    }
  });

  it("carries the scan facts so the session does not have to rescan", () => {
    expect(prompt).toContain("`aur:google-chrome`");
    expect(prompt).toContain("custom:chrome");
    expect(prompt).toContain("https://www.google.com/chrome");
    expect(prompt).toContain("Chromium");
    expect(prompt).toContain("ungoogled-chromium-bin");
    expect(prompt).toContain("Google Sync");
    expect(prompt).toContain("`sudo pacman -Rns google-chrome` (do not run it)");
    expect(prompt).toContain("required by: nothing\n");
  });

  it("has the three steps, stops for a choice, and never removes the original", () => {
    expect(prompt).toMatch(/0\. research/u);
    expect(prompt).toMatch(/1\. suggest/u);
    expect(prompt).toMatch(/2\. install/u);
    expect(prompt).toMatch(/stop and ask me which one to install/u);
    expect(prompt).toMatch(/must not: remove, disable or uninstall google-chrome/u);
    expect(prompt).toContain("data/curated.json");
  });

  it("names dependants and says when there is no curated entry", () => {
    const text = buildItemPrompt({ ...UNRAR, alternative: null, license: "", url: null });
    expect(text).toContain("required by: file-roller");
    expect(buildItemPrompt(STEAM_GAME)).toContain("required by: not tracked for steam");
    expect(text).toContain("curated alternatives: none yet");
    expect(text).toContain("licence: none found");
    expect(text).toContain("homepage: unknown");
  });

  it("lists curated names with their fit even when none is installed", () => {
    const text = buildItemPrompt({ ...CHROME, alternative: makeAlternative({ effort: "M", installed: [], names: [] }) });
    expect(text).toContain("curated alternatives: none named (fit: Drop-in, build-it effort: M");
    expect(text).not.toContain("already installed");
  });

  it("drops the install step for research-only items", () => {
    const text = buildItemPrompt(STEAM_GAME);
    expect(text.split("\n", 1)[0]).toBe("Research FOSS alternatives to Some Game");
    expect(text).not.toMatch(/2\. install/u);
    expect(text).toMatch(/research only/u);
  });

  it("handles a missing remove command and version", () => {
    const text = buildItemPrompt({ ...CHROME, removeCommand: null, version: null });
    expect(text).toContain("remove command: none known\n");
    expect(text).toContain("version: unknown");
  });
});

describe("buildBulkPrompt", () => {
  it("covers every candidate once and skips FOSS items", () => {
    const candidates = ITEMS.filter(isPromptCandidate);
    const text = buildBulkPrompt(ITEMS);
    expect(text.split("\n", 1)[0]).toBe(`Replace ${String(candidates.length)} non-FOSS items with FOSS alternatives`);
    for (const item of candidates) {
      expect(text).toContain(`### ${item.name} (\`${item.id}\`)`);
    }
    expect(text).not.toContain(`(\`${OWN_SCRIPT.id}\`)`);
    expect(text).toMatch(/one item at a time/u);
    expect(text).toMatch(/must not: remove, disable or uninstall any of them/u);
  });
});
