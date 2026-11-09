import type { AppState } from "./store.ts";

import { VIEWS } from "../lib/url-state.ts";
import { numberFormat } from "../lib/verdict.ts";
import { rescan, setQuery, setView } from "./actions.ts";
import { selectTabCounts } from "./selectors.ts";
import { hasChanged } from "./store-element.ts";
import { store } from "./store.ts";

function need(selector: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(selector);
  if (found === null) throw new Error(`pages/index.astro has no ${selector}`);
  return found;
}

export function searchInput(): HTMLInputElement {
  const found = need('input[aria-label^="Search"]');
  if (!(found instanceof HTMLInputElement)) throw new TypeError("the search box is not an <input>");
  return found;
}

function rescanButton(): HTMLButtonElement {
  const found = need("#rescan");
  if (!(found instanceof HTMLButtonElement)) throw new TypeError("#rescan is not a <button>");
  return found;
}

function formatGeneratedAt(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "medium" });
}

function setText(selector: string, text: string): void {
  need(selector).textContent = text;
}

function showScreen(state: AppState): void {
  const { kind } = state.scan;
  need("#app").hidden = kind !== "ready";
  need("#app-msg").hidden = kind === "ready";
  need("#msg-loading").hidden = kind !== "loading";
  need("#msg-error").hidden = kind !== "error";
  if (state.scan.kind === "error") setText("#msg-error-text", state.scan.message);
}

function showMeta(state: AppState): void {
  if (state.scan.kind !== "ready") return;
  const { scan } = state.scan;
  setText('[data-meta="host"]', scan.host);
  setText('[data-meta="scanned"]', formatGeneratedAt(scan.generatedAt));
  need('[data-meta="scanned"]').setAttribute("datetime", scan.generatedAt);
  setText('[data-meta="took"]', `${numberFormat.format(scan.durationMs)} ms`);
  const isRefreshing = state.scan.refreshing;
  const button = rescanButton();
  button.disabled = isRefreshing;
  button.setAttribute("aria-busy", String(isRefreshing));
  button.textContent = isRefreshing ? "Rescanning…" : "Rescan";
}

function showViews(state: AppState): void {
  const counts = selectTabCounts(state);
  for (const view of VIEWS) {
    const tab = need(`.tab[data-view="${view}"]`);
    // toggleAttribute cannot carry the value "page".
    // eslint-disable-next-line unicorn/prefer-toggle-attribute
    if (view === state.url.view) tab.setAttribute("aria-current", "page");
    else tab.removeAttribute("aria-current");
    need(`.tab[data-view="${view}"] .tab-count`).textContent = numberFormat.format(counts[view]);
    need(`.view[data-view="${view}"]`).hidden = view !== state.url.view;
  }
}

function showQuery(state: AppState): void {
  const input = searchInput();
  if (input.value !== state.url.filter.query) input.value = state.url.filter.query;
}

function update(state: AppState, previous: AppState | null): void {
  if (hasChanged(state, previous, (s) => s.scan.kind, (s) => s.scan.kind === "error" && s.scan.message)) showScreen(state);
  if (hasChanged(state, previous, (s) => s.scan)) showMeta(state);
  if (hasChanged(state, previous, (s) => selectTabCounts(s), (s) => s.url.view)) showViews(state);
  if (hasChanged(state, previous, (s) => s.url.filter.query)) showQuery(state);
}

// Wires the static header and tabs in pages/index.astro; swaps the homepage for the app. Returns stop().
export function startShell(): () => void {
  need("#home").hidden = true;
  const controller = new AbortController();
  const { signal } = controller;
  for (const view of VIEWS) {
    need(`.tab[data-view="${view}"]`).addEventListener("click", () => { setView(view); }, { signal });
  }
  const input = searchInput();
  input.addEventListener("input", () => { setQuery(input.value); }, { signal });
  need("#rescan").addEventListener("click", () => { rescan(); }, { signal });
  update(store.getState(), null);
  const unsubscribe = store.subscribe(update);
  return (): void => {
    unsubscribe();
    controller.abort();
  };
}
