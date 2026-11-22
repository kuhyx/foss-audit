/**
 * The fit and effort ranks the backend numbers (`fitRank`, `effortRank`):
 * 1 = heaviest (worst fit, most effort) ... N = lightest, no ties. Pure
 * helpers for the spoken labels; nothing here is painted.
 */
import type { Item } from "./schema.ts";

import { EFFORT_LABELS, FIT_LABELS } from "./verdict.ts";

export type RankKind = "effort" | "fit";

export interface RankTotals {
  readonly effort: number;
  readonly fit: number;
}

/**
 * N of "rank k of N": the backend numbers 1..N without gaps, so the highest
 * rank present is the count.
 */
export function rankTotals(items: readonly Item[]): RankTotals {
  let effort = 0;
  let fit = 0;
  for (const item of items) {
    effort = Math.max(effort, item.effortRank ?? 0);
    fit = Math.max(fit, item.fitRank ?? 0);
  }
  return { effort, fit };
}

export function rankPlace(rank: number, total: number): string {
  return `rank ${String(rank)} of ${String(total)}`;
}

function meaning(kind: RankKind, item: Item): string {
  const alt = item.alternative;
  if (kind === "fit") return `Fit: ${FIT_LABELS[alt?.fit ?? "none"]}`;
  return `Effort: ${alt?.effort == null ? "unknown" : EFFORT_LABELS[alt.effort]}`;
}

// The warning glyph's spoken name.
export function unrankedLabel(kind: RankKind): string {
  return `${kind === "fit" ? "Fit" : "Effort"}: not ranked yet`;
}

/**
 * The spoken name of a rank cell: "Fit: Good, rank 3 of 15". Null when the
 * item has no rank in that column.
 */
export function rankLabel(kind: RankKind, item: Item, totals: RankTotals): null | string {
  const rank = kind === "fit" ? item.fitRank : item.effortRank;
  return rank === null ? null : `${meaning(kind, item)}, ${rankPlace(rank, totals[kind])}`;
}
