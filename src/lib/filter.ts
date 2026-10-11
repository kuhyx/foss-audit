/**
 * Filter + search over scan items.
 *
 * Filtering happens here, before rows reach TanStack Table, which only sorts.
 * Keeping the predicate a plain function makes it the single definition used
 * by the table, the result count and the summary's click-through links.
 */
import { fuzzyMatch } from "@kuhyx/web-ui";

import type { Item, Source, Verdict } from "./schema.ts";

/**
 * A boolean facet: unset, or required true/false.
 */
export type Tri = "any" | "no" | "yes";

export type Kind = "any" | "dependency" | "explicit";

export interface FilterState {
  readonly altInstalled: Tri;
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
 * Fuzzy search over name, licence and alternative names.
 *
 * `reason` is deliberately not searched: it is a long free-text sentence, and
 * a subsequence match over it is almost always true ("chrome" matched 20 xorg
 * packages through their evidence strings).
 *
 * Each field is matched on its own. A subsequence match over one concatenated
 * string would let a query span two fields ("chrgpl" matching "chrome" +
 * "GPL"), which looks like a bug to anyone reading the result.
 */
export function matchesQuery(item: Item, query: string): boolean {
  const q = query.trim();
  const fields = [
    item.name,
    item.license,
    ...(item.alternative?.names ?? []),
  ];
  // fuzzyMatch("") is true, so an empty query matches every item.
  return fields.some((field) => fuzzyMatch(q, field));
}

export function passesFilter(item: Item, filter: FilterState): boolean {
  const alt = item.alternative;
  const hasAlt = alt !== null && alt.names.length > 0;
  return (
    (filter.verdicts.length === 0 || filter.verdicts.includes(item.verdict)) &&
    (filter.sources.length === 0 || filter.sources.includes(item.source)) &&
    passesKind(filter.kind, item.explicit) &&
    passesTri(filter.orphan, item.orphan) &&
    passesTri(filter.own, item.own) &&
    passesTri(filter.loose, item.loose) &&
    passesTri(filter.hasAlt, hasAlt) &&
    passesTri(filter.altInstalled, (alt?.installed.length ?? 0) > 0) &&
    matchesQuery(item, filter.query)
  );
}

export function applyFilter(
  items: readonly Item[],
  filter: FilterState,
): Item[] {
  return items.filter((item) => passesFilter(item, filter));
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
