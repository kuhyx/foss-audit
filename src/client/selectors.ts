import type { Item } from "../lib/schema.ts";
import type { View } from "../lib/url-state.ts";
import type { AppState } from "./store.ts";

import { applyFilter } from "../lib/filter.ts";
import { isEasyWin } from "../lib/verdict.ts";

const NONE: readonly Item[] = [];
const NO_MESSAGES: readonly string[] = [];

// Two-slot memo on input identity: a listener asks for the new state and then the previous one (hasChanged), and both must hit.
function memoize<A extends readonly unknown[], R>(compute: (...inputs: A) => R): (...inputs: A) => R {
  const slots: { readonly inputs: A; readonly result: R }[] = [];
  return (...inputs: A): R => {
    const hit = slots.find((slot) => slot.inputs.length === inputs.length && slot.inputs.every((value, index) => value === inputs[index]));
    if (hit !== undefined) return hit.result;
    const result = compute(...inputs);
    slots.splice(0, slots.length, { inputs, result }, ...slots.slice(0, 1));
    return result;
  };
}

export function selectItems(state: AppState): readonly Item[] {
  return state.scan.kind === "ready" ? state.scan.scan.items : NONE;
}

const filtered = memoize((items: readonly Item[], filter: AppState["url"]["filter"]) => applyFilter(items, filter));

export function selectResults(state: AppState): readonly Item[] {
  return filtered(selectItems(state), state.url.filter);
}

const winners = memoize((items: readonly Item[]) => items.filter((item) => isEasyWin(item)));

export function selectWins(state: AppState): readonly Item[] {
  return winners(selectItems(state));
}

const found = memoize((items: readonly Item[], id: null | string) => items.find((item) => item.id === id) ?? null);

export function selectSelectedItem(state: AppState): Item | null {
  return found(selectItems(state), state.url.selected);
}

const checked = memoize((items: readonly Item[], ids: ReadonlySet<string>) => items.filter((item) => ids.has(item.id)));

// From the whole scan, not the results: rows a filter hides stay selected.
export function selectCheckedItems(state: AppState): readonly Item[] {
  return checked(selectItems(state), state.selection.ids);
}

const counts = memoize(
  (all: readonly Item[], shown: readonly Item[], wins: readonly Item[]): Readonly<Record<View, number>> => {
    return {
      summary: all.length,
      table: shown.length,
      wins: wins.length,
    };
  },
);

export function selectTabCounts(state: AppState): Readonly<Record<View, number>> {
  return counts(selectItems(state), selectResults(state), selectWins(state));
}

// Dismissing stores this key; a new scan or a new rescan error changes it and the banner returns.
export function bannerKey(state: AppState): string {
  return state.scan.kind === "ready" ? `${state.scan.scan.generatedAt}|${state.scan.refreshError ?? ""}` : "";
}

const messages = memoize((scan: AppState["scan"]): readonly string[] => {
  return scan.kind === "ready"
    ? [
        ...scan.scan.errors.map((error) => `${error.source}: ${error.message}`),
        ...(scan.refreshError === null ? [] : [`Rescan failed: ${scan.refreshError}`]),
      ]
    : NO_MESSAGES;
},
);

export function selectBannerMessages(state: AppState): readonly string[] {
  return state.dismissedErrorKey === bannerKey(state) ? NO_MESSAGES : messages(state.scan);
}
