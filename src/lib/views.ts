/**
 * The views and keyboard shortcuts, as data.
 *
 * One source for the app (tab labels, the `?` sheet) and the prerendered docs
 * pages in src/lib/site, so the static description cannot drift from the UI.
 */
import type { View } from "./url-state.ts";

export const VIEW_LABELS: Readonly<Record<View, string>> = {
  summary: "Summary",
  table: "All items",
  wins: "Easy wins",
};

export const VIEW_HINTS: Readonly<Record<View, string>> = {
  summary:
    "Headline free / not-free split and a stacked bar per source; click a bar to open the table filtered to it",
  table:
    "Every installed item with search, verdict, source and flag filters, sortable columns and a detail panel",
  wins: "Non-free items whose drop-in or good FOSS alternative is already installed, with a copyable remove command",
};

export const SHORTCUTS: readonly (readonly [string, string])[] = [
  ["/", "focus search"],
  ["↑ ↓", "move the selected row (table focused)"],
  ["PgUp PgDn", "scroll the table"],
  ["Enter", "activate the focused tile, bar or button"],
  ["Esc", "close this, then the detail panel, then leave search"],
  ["?", "this help"],
];
