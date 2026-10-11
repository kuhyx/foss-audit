/**
 * The whole view state, encoded in the URL query string.
 *
 * Same posture as awesome-mcp-explorer: only non-default values are written, so
 * a pristine view has a clean URL, and unknown or malformed params are dropped
 * rather than throwing. A hand-edited link degrades to a sensible view.
 *
 *   view=table|wins     which tab (summary when absent)
 *   q=...               search
 *   v=nonfree,foss      verdicts        src=aur,steam   sources
 *   kind=explicit|dependency           orphan / own / loose / dangling / alt / altinst = yes|no
 *   sort=name | sort=-name             column id, `-` for descending
 *   sel=<item id>       the row whose detail panel is open
 */
import type { FilterState, Kind, Tri } from "./filter.ts";

import { DEFAULT_FILTER } from "./filter.ts";
import { SOURCES, VERDICTS } from "./schema.ts";

export const VIEWS = ["summary", "table", "wins"] as const;
export type View = (typeof VIEWS)[number];

export interface SortState {
  readonly desc: boolean;
  readonly id: string;
}

export interface UrlState {
  readonly filter: FilterState;
  readonly selected: null | string;
  readonly sort: null | SortState;
  readonly view: View;
}

export const DEFAULT_STATE: UrlState = {
  filter: DEFAULT_FILTER,
  selected: null,
  sort: null,
  view: "summary",
};

const TRIS: readonly Tri[] = ["any", "no", "yes"];
const KINDS: readonly Kind[] = ["any", "dependency", "explicit"];

function oneOf<T extends string>(
  raw: null | string,
  vocabulary: readonly T[],
  fallback: T,
): T {
  return vocabulary.find((v) => v === raw) ?? fallback;
}

function listOf<T extends string>(raw: null | string, vocabulary: readonly T[]): T[] {
  if (raw === null || raw === "") return [];
  const wanted = new Set(raw.split(","));
  return vocabulary.filter((v) => wanted.has(v));
}

function decodeSort(raw: null | string): null | SortState {
  if (raw === null || ["", "-"].includes(raw)) return null;
  return raw.startsWith("-")
    ? { desc: true, id: raw.slice(1) }
    : { desc: false, id: raw };
}

export function decodeState(search: string): UrlState {
  const parameters = new URLSearchParams(search);
  return {
    filter: {
      altInstalled: oneOf(parameters.get("altinst"), TRIS, "any"),
      dangling: oneOf(parameters.get("dangling"), TRIS, "any"),
      hasAlt: oneOf(parameters.get("alt"), TRIS, "any"),
      kind: oneOf(parameters.get("kind"), KINDS, "any"),
      loose: oneOf(parameters.get("loose"), TRIS, "any"),
      orphan: oneOf(parameters.get("orphan"), TRIS, "any"),
      own: oneOf(parameters.get("own"), TRIS, "any"),
      query: parameters.get("q") ?? "",
      sources: listOf(parameters.get("src"), SOURCES),
      verdicts: listOf(parameters.get("v"), VERDICTS),
    },
    selected: parameters.get("sel"),
    sort: decodeSort(parameters.get("sort")),
    view: oneOf(parameters.get("view"), VIEWS, "summary"),
  };
}

export function encodeState(state: UrlState): string {
  const parameters = new URLSearchParams();
  const { filter } = state;
  if (state.view !== "summary") parameters.set("view", state.view);
  if (filter.query !== "") parameters.set("q", filter.query);
  if (filter.verdicts.length > 0) parameters.set("v", filter.verdicts.join(","));
  if (filter.sources.length > 0) parameters.set("src", filter.sources.join(","));
  if (filter.kind !== "any") parameters.set("kind", filter.kind);
  if (filter.orphan !== "any") parameters.set("orphan", filter.orphan);
  if (filter.own !== "any") parameters.set("own", filter.own);
  if (filter.loose !== "any") parameters.set("loose", filter.loose);
  if (filter.dangling !== "any") parameters.set("dangling", filter.dangling);
  if (filter.hasAlt !== "any") parameters.set("alt", filter.hasAlt);
  if (filter.altInstalled !== "any") parameters.set("altinst", filter.altInstalled);
  if (state.sort !== null) {
    parameters.set("sort", `${state.sort.desc ? "-" : ""}${state.sort.id}`);
  }
  if (state.selected !== null) parameters.set("sel", state.selected);
  // Commas are this format's separator and never occur inside a member, so
  // they stay literal: `v=nonfree,foss` reads better than `v=nonfree%2Cfoss`.
  return parameters.toString().replaceAll("%2C", ",");
}
