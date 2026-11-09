/**
 * Filter + search over scan items.
 *
 * Filtering happens here, before rows reach the table, which only sorts (lib/sort.ts).
 * Keeping the predicate a plain function makes it the single definition used
 * by the table, the result count and the summary's click-through links.
 */
import type { Item, Source, Verdict } from "./schema.ts";

import { type CompiledQuery, compileQuery, type Rank } from "./fuzzy.ts";

/**
 * A boolean facet: unset, or required true/false.
 */
export type Tri = "any" | "no" | "yes";

export type Kind = "any" | "dependency" | "explicit";

export interface FilterState {
  readonly altInstalled: Tri;
  readonly dangling: Tri;
  readonly hasAlt: Tri;
  readonly kind: Kind;
  readonly loose: Tri;
  readonly orphan: Tri;
  readonly own: Tri;
  readonly query: string;
  readonly sources: readonly Source[];
  readonly verdicts: readonly Verdict[];
}

export const DEFAULT_FILTER: FilterState = {
  altInstalled: "any",
  dangling: "any",
  hasAlt: "any",
  kind: "any",
  loose: "any",
  orphan: "any",
  own: "any",
  query: "",
  sources: [],
  verdicts: [],
};

function passesTri(tri: Tri, isTrue: boolean): boolean {
  return tri === "any" || (tri === "yes") === isTrue;
}

function passesKind(kind: Kind, isExplicit: boolean): boolean {
  return kind === "any" || (kind === "explicit") === isExplicit;
}

/**
 * Typo-tolerant search over the name and the id only (see fuzzy.ts).
 *
 * Licence, alternative names and reason are deliberately not searched: long
 * strings make loose matches near-certain, and "select all shown" then picks
 * up rows that merely mention the query ("firebase" grabbed qemu packages
 * through their licence lists).
 */
function queryRank(item: Item, query: CompiledQuery): null | Rank {
  return query.rank([item.name, item.id]);
}

/**
 * One item on its own: true for an exact or a typo hit. `applyFilter` then
 * drops the typo hits whenever any row matches exactly.
 */
export function matchesQuery(item: Item, query: string): boolean {
  return queryRank(item, compileQuery(query)) !== null;
}

function passesFacets(item: Item, filter: FilterState): boolean {
  const alt = item.alternative;
  const hasAlt = alt !== null && alt.names.length > 0;
  return (
    (filter.verdicts.length === 0 || filter.verdicts.includes(item.verdict)) &&
    (filter.sources.length === 0 || filter.sources.includes(item.source)) &&
    passesKind(filter.kind, item.explicit) &&
    passesTri(filter.orphan, item.orphan) &&
    passesTri(filter.own, item.own) &&
    passesTri(filter.loose, item.loose) &&
    passesTri(filter.dangling, item.dangling) &&
    passesTri(filter.hasAlt, hasAlt) &&
    passesTri(filter.altInstalled, (alt?.installed.length ?? 0) > 0)
  );
}

export function passesFilter(item: Item, filter: FilterState): boolean {
  return passesFacets(item, filter) && matchesQuery(item, filter.query);
}

/**
 * The rows that pass. Typo hits are a fallback, shown only when no row has
 * the query as an exact substring: otherwise "firebase" would also list
 * "airbase" (2 edits away) and "select all shown" would grab it. Typo hits
 * whose matches start on each word's first letter come first. Scan order is
 * kept within a rank; the table re-sorts only when a column sort is set.
 */
export function applyFilter(
  items: readonly Item[],
  filter: FilterState,
): Item[] {
  const query = compileQuery(filter.query);
  // One bucket per rank (see fuzzy.ts Rank), each kept in scan order.
  const buckets: [Item[], Item[], Item[]] = [[], [], []];
  for (const item of items) {
    if (!passesFacets(item, filter)) continue;
    const rank = queryRank(item, query);
    if (rank !== null) buckets[rank].push(item);
  }
  const [exact, anchored, loose] = buckets;
  return exact.length > 0 ? exact : [...anchored, ...loose];
}

export function isFilterActive(filter: FilterState): boolean {
  return (
    filter.query !== "" ||
    filter.verdicts.length > 0 ||
    filter.sources.length > 0 ||
    filter.kind !== "any" ||
    filter.orphan !== "any" ||
    filter.own !== "any" ||
    filter.loose !== "any" ||
    filter.dangling !== "any" ||
    filter.hasAlt !== "any" ||
    filter.altInstalled !== "any"
  );
}

/**
 * Adds or removes one member of a multi-select, preserving vocabulary order.
 */
export function toggleMember<T extends string>(
  selected: readonly T[],
  value: T,
  vocabulary: readonly T[],
): T[] {
  const next = new Set(selected);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return vocabulary.filter((v) => next.has(v));
}
