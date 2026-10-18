/**
 * Domain vocabulary shared by every view: labels, colours, the free/not-free
 * split, and the "easy win" rule from DOCS-api-contract.md.
 */
import type { Fit, Item, Verdict } from "./schema.ts";

export const VERDICT_LABELS: Readonly<Record<Verdict, string>> = {
  foss: "FOSS",
  "foss-partial": "FOSS (partial)",
  nonfree: "Non-free",
};

export const VERDICT_HINTS: Readonly<Record<Verdict, string>> = {
  foss: "OSI/FSF licence on the shipped thing",
  "foss-partial": "Free code with a non-free part (assets, weights, unRAR code)",
  nonfree: "Proprietary, freeware, EULA, source-available, firmware blob or no licence found",
};

/**
 * Verdict -> categorical ramp slot.
 *
 * The ramp is identity, not meaning (tokens.css forbids "green because good").
 * Slots 1-3 keep the colours chosen when there were six verdicts (picked with
 * the dataviz palette validator for the stacked bar's VERDICTS order), so a
 * verdict does not change colour between releases.
 */
export const VERDICT_COLORS: Readonly<Record<Verdict, string>> = {
  foss: "var(--cat-1)",
  "foss-partial": "var(--cat-2)",
  nonfree: "var(--cat-3)",
};

/**
 * The headline's "free" side. foss-partial counts as free here by the
 * product's definition (free code, non-free parts).
 */
export const FREE_VERDICTS: ReadonlySet<Verdict> = new Set<Verdict>([
  "foss",
  "foss-partial",
]);

export const NOT_FREE_VERDICTS: readonly Verdict[] = ["nonfree"];

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
  return `${value.toFixed(value < 10 && value > 0 ? 1 : 0)}%`;
}

export const numberFormat = new Intl.NumberFormat("en-US");
