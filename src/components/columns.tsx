/**
 * Column definitions for the all-items table. Every column sorts.
 *
 * Each accessor returns a primitive sort key (a string, or a rank number for
 * the ordinal enums) and `undefined` for "absent", which `sortUndefined:
 * "last"` keeps at the bottom in both directions: a missing licence or
 * alternative is never the most interesting row.
 */
import {
  createColumnHelper,
  createSortedRowModel,
  rowSortingFeature,
  sortFn_basic,
  sortFn_text,
  tableFeatures,
} from "@tanstack/react-table";

import type { Item } from "../lib/schema.ts";

import { EFFORTS, FITS, VERDICTS } from "../lib/schema.ts";
import { FIT_LABELS } from "../lib/verdict.ts";
import { VerdictBadge } from "./verdict-badge.tsx";

export const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { basic: sortFn_basic, text: sortFn_text },
});

const helper = createColumnHelper<typeof features, Item>();

function orUndefined(value: null | string): string | undefined {
  return value === null || value === "" ? undefined : value;
}

function rankOf<T extends string>(vocabulary: readonly T[], value: null | T | undefined): number | undefined {
  return value === null || value === undefined ? undefined : vocabulary.indexOf(value);
}

const text = { sortFn: "text", sortUndefined: "last" } as const;
const ranked = { sortFn: "basic", sortUndefined: "last" } as const;

/**
 * CSS grid track per column, in column order. Kept beside the definitions so
 * adding a column cannot forget its width.
 */
export const COLUMN_TRACKS = [
  "minmax(12rem, 1.4fr)", // name
  "minmax(8rem, 0.7fr)", // version
  "7rem", // source
  "9.5rem", // verdict
  "minmax(9rem, 1fr)", // license
  "7.5rem", // kind
  "5.5rem", // orphan
  "6rem", // requiredBy
  "minmax(10rem, 1fr)", // alternative
  "5.5rem", // fit
  "5.5rem", // effort
  "minmax(9rem, 1fr)", // installed
].join(" ");

export const columns = helper.columns([
  helper.accessor((item) => item.name, {
    ...text,
    cell: (info) => {
      return (
        <>
          {info.getValue()}
          {info.row.original.own && (
            <>
              {" "}
              <span className="badge badge-own" title="kuhy's own code">own</span>
            </>
          )}
          {info.row.original.loose && (
            <>
              {" "}
              <span className="badge badge-own" title="in ~/.local/bin, no repo or package tracks it">loose</span>
            </>
          )}
        </>
      );
    },
    header: "Name",
    id: "name",
  }),
  helper.accessor((item) => orUndefined(item.version), {
    ...text,
    cell: (info) => info.getValue() ?? "—",
    header: "Version",
    id: "version",
  }),
  helper.accessor((item) => item.source, { ...text, header: "Source", id: "source" }),
  helper.accessor((item) => VERDICTS.indexOf(item.verdict), {
    ...ranked,
    cell: (info) => <VerdictBadge verdict={info.row.original.verdict} />,
    header: "Verdict",
    id: "verdict",
  }),
  helper.accessor((item) => orUndefined(item.license), {
    ...text,
    cell: (info) => info.getValue() ?? "—",
    header: "Licence",
    id: "license",
  }),
  helper.accessor((item) => (item.explicit ? "explicit" : "dependency"), {
    ...text,
    header: "Installed as",
    id: "kind",
  }),
  helper.accessor((item) => (item.orphan ? 1 : 0), {
    ...ranked,
    cell: (info) => (info.getValue() === 1 ? "orphan" : ""),
    header: "Orphan",
    id: "orphan",
  }),
  helper.accessor((item) => item.requiredBy.length, {
    ...ranked,
    cell: (info) => (info.getValue() === 0 ? "" : info.getValue()),
    header: "Req. by",
    id: "requiredBy",
  }),
  helper.accessor((item) => item.alternative?.names[0], {
    ...text,
    cell: (info) => info.getValue() ?? "",
    header: "Alternative",
    id: "alternative",
  }),
  helper.accessor((item) => rankOf(FITS, item.alternative?.fit), {
    ...ranked,
    cell: (info) => {
      const fit = info.row.original.alternative?.fit;
      return fit === undefined ? "" : FIT_LABELS[fit];
    },
    header: "Fit",
    id: "fit",
  }),
  helper.accessor((item) => rankOf(EFFORTS, item.alternative?.effort), {
    ...ranked,
    cell: (info) => info.row.original.alternative?.effort ?? "",
    header: "Effort",
    id: "effort",
  }),
  helper.accessor((item) => item.alternative?.installed.length, {
    ...ranked,
    cell: (info) => info.row.original.alternative?.installed.join(", ") ?? "",
    header: "Alt. installed",
    id: "installed",
  }),
]);
