/**
 * Geometry for the per-source 100%-stacked bars.
 *
 * 100%-stacked rather than absolute: pacman holds ~2,500 items and cargo 2,
 * so on a shared absolute axis every source but two would be a sliver. The
 * absolute total is printed at each bar's end instead, and the proportion is
 * what the bar shows.
 */
import type { Item, Source, Verdict } from "./schema.ts";

import { VERDICTS } from "./schema.ts";

export interface Segment {
  readonly count: number;
  readonly verdict: Verdict;
  readonly width: number;
  readonly x: number;
}

export interface SourceRow {
  readonly counts: ReadonlyMap<Verdict, number>;
  readonly source: Source;
  readonly total: number;
}

/**
 * Smallest drawn segment, before the 2px gap. One package out of 2,525 would
 * otherwise be a 0.3px mark nobody can see, hover or click.
 */
export const MIN_SEGMENT = 6;

/**
 * Surface-coloured gap between touching segments (dataviz mark spec).
 */
export const SEGMENT_GAP = 2;

export function sourceRows(items: readonly Item[]): SourceRow[] {
  const bySource = new Map<Source, Map<Verdict, number>>();
  for (const item of items) {
    const counts = bySource.get(item.source) ?? new Map<Verdict, number>();
    counts.set(item.verdict, (counts.get(item.verdict) ?? 0) + 1);
    bySource.set(item.source, counts);
  }
  return [...bySource]
    .map(([source, counts]) => {
      return {
        counts,
        source,
        total: counts.values().reduce((sum, n) => sum + n, 0),
      };
    })
    .toSorted((a, b) => b.total - a.total || a.source.localeCompare(b.source));
}

/**
 * Lays one row's verdicts out across `width` pixels.
 *
 * Segments under MIN_SEGMENT are raised to it and the space comes out of the
 * others in proportion, so the bar still spans exactly `width`. Exact counts
 * stay available in the tooltip and the table; the bar is for proportion.
 */
export function layoutSegments(row: SourceRow, width: number): Segment[] {
  const present: { count: number; verdict: Verdict }[] = [];
  for (const verdict of VERDICTS) {
    const count = row.counts.get(verdict) ?? 0;
    if (count > 0) present.push({ count, verdict });
  }
  const raw = (count: number): number => (count / row.total) * width;
  const small = present.filter((s) => raw(s.count) < MIN_SEGMENT);
  const smallCount = small.reduce((sum, s) => sum + s.count, 0);
  const largeTotal = row.total - smallCount;
  const largeWidth = width - small.length * MIN_SEGMENT;

  let x = 0;
  return present.map(({ count, verdict }) => {
    const isSmall = raw(count) < MIN_SEGMENT;
    const segmentWidth =
      isSmall || largeTotal === 0 ? MIN_SEGMENT : (count / largeTotal) * largeWidth;
    const segment = { count, verdict, width: segmentWidth, x };
    x += segmentWidth;
    return segment;
  });
}

/**
 * A rect with only its right-hand corners rounded: the data end is rounded,
 * the baseline end stays square (dataviz mark spec).
 */
export function roundedEndPath(
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
): string {
  const r = Math.min(radius, width / 2, height / 2);
  const right = x + width;
  return [
    `M${x},${y}`,
    `H${right - r}`,
    `Q${right},${y} ${right},${y + r}`,
    `V${y + height - r}`,
    `Q${right},${y + height} ${right - r},${y + height}`,
    `H${x}`,
    "Z",
  ].join(" ");
}
