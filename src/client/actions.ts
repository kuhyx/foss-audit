/**
 * The only way widgets change state. See DOCS-ui-contract.md.
 */
import type { FilterState } from "../lib/filter.ts";
import type { Source, Verdict } from "../lib/schema.ts";
import type { SortState, UrlState, View } from "../lib/url-state.ts";

import { DEFAULT_FILTER } from "../lib/filter.ts";
import { clickRow as clickSelectionRow, EMPTY_SELECTION, setRows } from "../lib/selection.ts";
import { encodeState } from "../lib/url-state.ts";
import { refresh } from "./scan.ts";
import { bannerKey } from "./selectors.ts";
import { store } from "./store.ts";

export interface NavigateOptions {
  readonly push?: boolean;
}

// Patches the CURRENT URL state, so two updates from one handler compose.
export function navigate(patch: (current: UrlState) => UrlState, options: NavigateOptions = {}): void {
  const next = patch(store.getState().url);
  const query = encodeState(next);
  const url = query === "" ? globalThis.location.pathname : `?${query}`;
  if (options.push === true) globalThis.history.pushState(null, "", url);
  else globalThis.history.replaceState(null, "", url);
  store.set({ url: next });
}

export function setView(view: View): void {
  navigate((s) => ({ ...s, view }), { push: true });
}

export function setQuery(query: string): void {
  navigate((s) => ({ ...s, filter: { ...s.filter, query }, view: "table" }));
}

export function setFilter(filter: FilterState): void {
  navigate((s) => ({ ...s, filter }));
}

export function setSort(sort: null | SortState): void {
  navigate((s) => ({ ...s, sort }));
}

export function openItem(id: string): void {
  navigate((s) => ({ ...s, selected: id }));
}

export function closeItem(): void {
  navigate((s) => ({ ...s, selected: null }));
}

export function drill(verdicts: readonly Verdict[], sources: readonly Source[]): void {
  navigate((s) => ({ ...s, filter: { ...DEFAULT_FILTER, sources, verdicts }, selected: null, view: "table" }), {
    push: true,
  });
}

export function clickRow(id: string, order: readonly string[], isShift: boolean): void {
  store.set({ selection: clickSelectionRow(store.getState().selection, id, order, isShift) });
}

export function setRowsChecked(ids: readonly string[], isOn: boolean): void {
  store.set({ selection: setRows(store.getState().selection, ids, isOn) });
}

export function clearSelection(): void {
  store.set({ selection: EMPTY_SELECTION });
}

export function openHelp(): void {
  store.set({ helpOpen: true });
}

export function closeHelp(): void {
  store.set({ helpOpen: false });
}

export function toggleHelp(): void {
  store.set({ helpOpen: !store.getState().helpOpen });
}

export function dismissBanner(): void {
  store.set({ dismissedErrorKey: bannerKey(store.getState()) });
}

export function rescan(): void {
  refresh();
}
