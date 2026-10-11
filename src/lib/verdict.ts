/**
 * Domain vocabulary shared by every view: labels, colours, the free/not-free
 * split, and the "easy win" rule from DOCS-api-contract.md.
 */
import type { Fit, Item, Verdict } from "./schema.ts";

export const VERDICT_LABELS: Readonly<Record<Verdict, string>> = {
  blob: "Blob",
  foss: "FOSS",
  "foss-partial": "FOSS (partial)",
  nonfree: "Non-free",
  own: "Own code",
  unknown: "Unknown",
};

export const VERDICT_HINTS: Readonly<Record<Verdict, string>> = {
  blob: "Firmware, driver or microcode with no alternative on this hardware",
  foss: "OSI/FSF licence on the shipped thing",
  "foss-partial": "Free code with a non-free part (assets, weights, unRAR code)",
  nonfree: "Proprietary, freeware, EULA or source-available",
  own: "kuhy's own code",
  unknown: "No licence found anywhere",
};

/**
 * Verdict -> categorical ramp slot.
 *
 * The ramp is identity, not meaning (tokens.css forbids "green because good").
 * The slot order was chosen by running the dataviz palette validator over all
 * 720 orderings of the six slots, against both surfaces, for the order the
 * stacked bar draws them in (VERDICTS). This one keeps every adjacent pair
 * above a CVD dE of 14.8 in dark and light; the shared ramp in its own order
 * fails (cat-3 next to cat-4 is dE 5.1 under protanopia).
 */
export const VERDICT_COLORS: Readonly<Record<Verdict, string>> = {
  blob: "var(--cat-5)",
  foss: "var(--cat-1)",
  "foss-partial": "var(--cat-2)",
  nonfree: "var(--cat-3)",
  own: "var(--cat-6)",
  unknown: "var(--cat-4)",
};

/**
 * The headline's "free" side. foss-partial counts as free here by the
 * product's definition (free code, non-free parts).
 */
export const FREE_VERDICTS: ReadonlySet<Verdict> = new Set<Verdict>([
  "foss",
  "foss-partial",
  "own",
]);

export const NOT_FREE_VERDICTS: readonly Verdict[] = ["nonfree", "blob", "unknown"];

export const FIT_LABELS: Readonly<Record<Fit, string>> = {
  "drop-in": "Drop-in",
  good: "Good",
  none: "None",
  partial: "Partial",
};

export const EFFORT_LABELS = {
  L: "L · 1–6 months",
  M: "M · 1–4 weeks",
  S: "S · under a week",
  XL: "XL · infeasible",
} as const;

/**
 * `requiredBy` is filled from pacman's reverse dependencies only (the AUR
 * packages are pacman packages too); every other source reports `[]`. An
 * empty list therefore means "nothing depends on it" only for these two.
 * True means the source tracks dependants, not that it has any.
 */
export function hasTrackedDependants(item: Item): boolean {
  return item.source === "pacman" || item.source === "aur";
}

const EASY_FITS: ReadonlySet<Fit> = new Set<Fit>(["drop-in", "good"]);

/**
 * The contract's "easy win": not fully free, a drop-in or good alternative,
 * and at least one of those alternatives already installed.
 */
export function isEasyWin(item: Item): boolean {
  const alt = item.alternative;
  return (
    (item.verdict === "nonfree" || item.verdict === "foss-partial") &&
    alt !== null &&
    EASY_FITS.has(alt.fit) &&
    alt.installed.length > 0
  );
}

export function countBy<K extends string>(
  items: readonly Item[],
  key: (item: Item) => K,
): Map<K, number> {
  const counts = new Map<K, number>();
  for (const item of items) {
    const k = key(item);
    counts.set(k, (counts.get(k) ?? 0) + 1);
  }
  return counts;
}

export function percent(part: number, whole: number): string {
  if (whole === 0) return "0%";
  const value = (part / whole) * 100;
  // 1 of 3,138 is 0.03%: "0.0%" would read as "none at all".
  if (value > 0 && value < 0.1) return "<0.1%";
  return `${value < 10 && value > 0 ? value.toFixed(1) : value.toFixed(0)}%`;
}

export const numberFormat = new Intl.NumberFormat("en-US");
