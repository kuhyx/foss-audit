/**
 * Column definitions of the all-items table. Every column sorts. A sortKey is
 * a string, a number (the Fit and Effort columns sort by the backend's rank,
 * 1 = heaviest), or undefined for "absent" (sort.ts keeps those last).
 */
import type { Item } from "./schema.ts";

import { VERDICTS } from "./schema.ts";
import { VERDICT_LABELS } from "./verdict.ts";

export type SortKey = number | string | undefined;

export interface Column {
  readonly header: string;
  readonly id: string;
  readonly sortKey: (item: Item) => SortKey;
  readonly text: (item: Item) => string;
}

function orUndefined(value: null | string): string | undefined {
  return value === null || value === "" ? undefined : value;
}

function rankText(rank: null | number): string {
  return rank === null ? "" : String(rank);
}

export const COLUMNS: readonly Column[] = [
  { header: "Name", id: "name", sortKey: (item) => item.name, text: (item) => item.name },
  {
    header: "Version",
    id: "version",
    sortKey: (item) => orUndefined(item.version),
    text: (item) => orUndefined(item.version) ?? "—",
  },
  { header: "Source", id: "source", sortKey: (item) => item.source, text: (item) => item.source },
  {
    header: "Verdict",
    id: "verdict",
    sortKey: (item) => VERDICTS.indexOf(item.verdict),
    text: (item) => VERDICT_LABELS[item.verdict],
  },
  {
    header: "Licence",
    id: "license",
    sortKey: (item) => orUndefined(item.license),
    text: (item) => orUndefined(item.license) ?? "—",
  },
  {
    header: "Installed as",
    id: "kind",
    sortKey: (item) => (item.explicit ? "explicit" : "dependency"),
    text: (item) => (item.explicit ? "explicit" : "dependency"),
  },
  {
    header: "Orphan",
    id: "orphan",
    sortKey: (item) => (item.orphan ? 1 : 0),
    text: (item) => (item.orphan ? "orphan" : ""),
  },
  {
    header: "Req. by",
    id: "requiredBy",
    sortKey: (item) => item.requiredBy.length,
    text: (item) => (item.requiredBy.length === 0 ? "" : String(item.requiredBy.length)),
  },
  {
    header: "Alternative",
    id: "alternative",
    sortKey: (item) => item.alternative?.names[0],
    text: (item) => item.alternative?.names[0] ?? "",
  },
  {
    header: "Fit",
    id: "fit",
    sortKey: (item) => item.fitRank ?? undefined,
    text: (item) => rankText(item.fitRank),
  },
  {
    header: "Effort",
    id: "effort",
    sortKey: (item) => item.effortRank ?? undefined,
    text: (item) => rankText(item.effortRank),
  },
  {
    header: "Alt. installed",
    id: "installed",
    sortKey: (item) => item.alternative?.installed.length,
    text: (item) => item.alternative?.installed.join(", ") ?? "",
  },
];

/**
CSS grid tracks: the selection checkbox, then one per column in COLUMNS order.
*/
export const COLUMN_TRACKS = [
  "2.5rem",
  "minmax(12rem, 1.4fr)",
  "minmax(8rem, 0.7fr)",
  "7rem",
  "9.5rem",
  "minmax(9rem, 1fr)",
  "7.5rem",
  "5.5rem",
  "6rem",
  "minmax(10rem, 1fr)",
  "5.5rem",
  "5.5rem",
  "minmax(9rem, 1fr)",
].join(" ");
