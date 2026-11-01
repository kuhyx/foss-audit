/**
 * Hand-written test data. Never the recorded fixtures/scan.sample.json: that
 * is a real machine's package list and stays out of the repo.
 */
import type { Alternative, Item, Scan, ScanProgress } from "../lib/schema.ts";

export function makeAlternative(overrides: Partial<Alternative> = {}): Alternative {
  return {
    effort: null,
    effortReason: "",
    fit: "drop-in",
    installed: [],
    lockIn: "",
    names: ["Chromium"],
    ...overrides,
  };
}

export function makeItem(overrides: Partial<Item> = {}): Item {
  const name = overrides.name ?? "bash";
  const source = overrides.source ?? "pacman";
  return {
    alternative: null,
    dangling: false,
    explicit: true,
    id: `${source}:${name}`,
    license: "GPL-3.0-or-later",
    loose: false,
    name,
    orphan: false,
    own: false,
    reason: "GPL-3.0-or-later",
    removeCommand: `sudo pacman -Rns ${name}`,
    removeVia: "",
    requiredBy: [],
    source,
    url: null,
    verdict: "foss",
    version: "5.2.0-1",
    ...overrides,
  };
}

// google-chrome: a non-free AUR package whose drop-in alternative is installed.
export const CHROME = makeItem({
  alternative: makeAlternative({
    effort: "XL",
    effortReason: "a browser",
    installed: ["ungoogled-chromium-bin"],
    lockIn: "Google Sync",
    names: ["Chromium", "Firefox"],
  }),
  license: "custom:chrome",
  name: "google-chrome",
  reason: "custom:chrome",
  source: "aur",
  url: "https://www.google.com/chrome",
  verdict: "nonfree",
});

// unrar: non-free, good alternative installed, but something still needs it.
export const UNRAR = makeItem({
  alternative: makeAlternative({ fit: "good", installed: ["libarchive"], names: ["libarchive"] }),
  explicit: false,
  license: "custom:unrar",
  name: "unrar",
  requiredBy: ["file-roller"],
  verdict: "nonfree",
});

// A Steam app: reverse dependencies are not tracked for this source.
export const STEAM_GAME = makeItem({
  alternative: makeAlternative({ fit: "good", installed: ["0ad"], names: ["0 A.D."] }),
  license: "",
  name: "Some Game",
  reason: "Steam app",
  removeCommand: "steam steam://uninstall/1",
  source: "steam",
  verdict: "nonfree",
  version: null,
});

export const FIRMWARE = makeItem({ name: "linux-firmware", reason: "firmware blob", verdict: "nonfree" });
export const OWN_SCRIPT = makeItem({ name: "backup.sh", own: true, removeCommand: null, source: "local-bin" });
export const ORPHAN_LIB = makeItem({ explicit: false, name: "libfoo", orphan: true });
export const PARTIAL = makeItem({ name: "unar", verdict: "foss-partial" });
export const MYSTERY = makeItem({ license: "", loose: true, name: "mystery", reason: "no license found", source: "opt", verdict: "nonfree" });
export const DEAD_LAUNCHER = makeItem({
  dangling: true,
  license: "",
  name: "rpcs3",
  reason: "launcher without target: /opt/rpcs3/usr/bin/rpcs3",
  removeCommand: "rm '/home/kuhy/.local/share/applications/rpcs3.desktop'",
  source: "desktop",
  verdict: "nonfree",
});

export const ITEMS: readonly Item[] = [
  makeItem(),
  CHROME,
  UNRAR,
  STEAM_GAME,
  FIRMWARE,
  OWN_SCRIPT,
  ORPHAN_LIB,
  PARTIAL,
  MYSTERY,
];

export function makeScan(overrides: Partial<Scan> = {}): Scan {
  return {
    durationMs: 1234,
    errors: [],
    generatedAt: "2026-10-11T14:02:11Z",
    host: "testhost",
    items: [...ITEMS],
    scanning: false,
    ...overrides,
  };
}

export function makeProgress(overrides: Partial<ScanProgress> = {}): ScanProgress {
  return {
    error: null,
    generatedAt: null,
    itemsFound: 0,
    running: [],
    scanning: true,
    sourcesDone: 0,
    sourcesTotal: 26,
    ...overrides,
  };
}
