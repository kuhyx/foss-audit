import type { AppState } from "../client/store.ts";
import type { FilterState } from "../lib/filter.ts";
import type { Item, Source, Verdict } from "../lib/schema.ts";

import { setFilter } from "../client/actions.ts";
import { selectItems, selectResults } from "../client/selectors.ts";
import { define, hasChanged, StoreElement } from "../client/store-element.ts";
import { DEFAULT_FILTER, isFilterActive, toggleMember } from "../lib/filter.ts";
import { SOURCES, VERDICTS } from "../lib/schema.ts";
import { countBy, numberFormat, VERDICT_COLORS, VERDICT_LABELS } from "../lib/verdict.ts";
import { html } from "../render/dom.ts";

type Facet = "altInstalled" | "dangling" | "hasAlt" | "kind" | "loose" | "orphan" | "own";
type Options = readonly (readonly [string, string])[];

// Visible option/facet labels are drawn as symbols; the old words live on as
// aria-label (spoken) while the option *values* stay unchanged.
const SYMBOL: Readonly<Record<string, string>> = {
  "Alternative installed": "✓",
  Any: "☰",
  "Dead launcher": "✕",
  Dependency: "⧉",
  Explicit: "⚙",
  Filters: "☰",
  "Has alternative": "⧉",
  "Installed as": "⚙",
  No: "✕",
  Orphan: "🗑",
  "Own code": "✓",
  "Reset filters": "⟳",
  Source: "⚙",
  "Untracked file": "▲",
  Verdict: "⚙",
  Yes: "✓",
};

const TRI: Options = [["any", "Any"], ["yes", "Yes"], ["no", "No"]];
const KIND: Options = [["any", "Any"], ["explicit", "Explicit"], ["dependency", "Dependency"]];

const FACETS: readonly (readonly [Facet, string, Options])[] = [
  ["kind", "Installed as", KIND],
  ["orphan", "Orphan", TRI],
  ["own", "Own code", TRI],
  ["loose", "Untracked file", TRI],
  ["dangling", "Dead launcher", TRI],
  ["hasAlt", "Has alternative", TRI],
  ["altInstalled", "Alternative installed", TRI],
];

interface Bar {
  readonly count: Text;
  readonly reset: HTMLButtonElement;
  readonly root: HTMLElement;
  readonly total: Text;
}

function icon(label: string): HTMLElement {
  return html("span", { "aria-hidden": "true", class: "icon" }, SYMBOL[label] ?? label);
}

function chip(group: string, value: string, count: number, ...label: readonly (Node | string)[]): HTMLButtonElement {
  return html(
    "button",
    { "aria-pressed": "false", class: "chip", "data-group": group, "data-value": value, type: "button" },
    ...label,
    html("span", { class: "chip-count" }, numberFormat.format(count)),
  );
}

function verdictChip(verdict: Verdict, count: number): HTMLButtonElement {
  const dot = html("span", { "aria-hidden": "true", class: "dot" });
  dot.style.background = VERDICT_COLORS[verdict];
  return chip("verdicts", verdict, count, dot, VERDICT_LABELS[verdict]);
}

function group(label: string, ...buttons: readonly HTMLElement[]): HTMLElement {
  return html("div", { "aria-label": label, class: "chips", role: "group" }, html("span", { class: "facet-label" }, icon(label)), ...buttons);
}

function segmented(facet: Facet, label: string, options: Options): HTMLElement {
  const buttons = options.map(([value, text]) =>
    html("button", { "aria-pressed": "false", class: "seg", "data-facet": facet, "data-value": value, type: "button" }, icon(text)),
  );
  return html("div", { "aria-label": label, class: "segmented", role: "group" }, html("span", { class: "facet-label" }, icon(label)), ...buttons);
}

function pressed(root: ParentNode, selector: string, isOn: (button: HTMLElement) => boolean): void {
  for (const button of root.querySelectorAll<HTMLElement>(selector)) button.setAttribute("aria-pressed", String(isOn(button)));
}

function build(items: readonly Item[]): Bar {
  const verdictCounts = countBy(items, (item) => item.verdict);
  const present = [...countBy(items, (item) => item.source)].toSorted(([a], [b]) => SOURCES.indexOf(a) - SOURCES.indexOf(b));
  const count = document.createTextNode("");
  const total = document.createTextNode("");
  const reset = html("button", { "aria-label": "Reset filters", class: "btn", "data-reset": true, type: "button" }, icon("Reset filters"));
  const toggle = html("button", { "aria-expanded": "false", "aria-label": "Filters", class: "btn filter-toggle", type: "button" }, icon("Filters"));
  const result = html("p", { "aria-live": "polite", class: "result-count" }, html("strong", {}, count), " ", html("span", { class: "muted" }, "of ", total, " items"));
  const row = html("div", { class: "facet-row" }, toggle, ...FACETS.map(([facet, label, options]) => segmented(facet, label, options)), result, reset);
  const root = html(
    "div",
    { class: "filters", "data-collapsed": "true" },
    group("Verdict", ...VERDICTS.map((verdict) => verdictChip(verdict, verdictCounts.get(verdict) ?? 0))),
    group("Source", ...present.map(([source, n]) => chip("sources", source, n, source))),
    row,
  );
  toggle.addEventListener("click", () => {
    const isCollapsed = root.dataset.collapsed === "true";
    root.dataset.collapsed = String(!isCollapsed);
    toggle.setAttribute("aria-expanded", String(isCollapsed));
  });
  return { count, reset, root, total };
}

function onClick(event: MouseEvent, filter: FilterState): void {
  const button = event.target instanceof Element ? event.target.closest<HTMLElement>("button") : null;
  if (button === null) return;
  const value = button.dataset.value ?? "";
  const { facet, group: chipGroup, reset } = button.dataset;
  if (reset !== undefined) setFilter(DEFAULT_FILTER);
  else if (chipGroup === "verdicts") setFilter({ ...filter, verdicts: toggleMember(filter.verdicts, value as Verdict, VERDICTS) });
  else if (chipGroup === "sources") setFilter({ ...filter, sources: toggleMember(filter.sources, value as Source, SOURCES) });
  else if (facet !== undefined) setFilter({ ...filter, [facet]: value });
}

export class FilterBar extends StoreElement {
  #bar: Bar | null = null;
  #items: null | readonly Item[] = null;
  #latest: AppState | null = null;

  protected override teardown(): void {
    this.#bar = null;
    this.#items = null;
    super.teardown();
  }

  protected override update(state: AppState, previous: AppState | null): void {
    this.#latest = state;
    if (state.url.view !== "table" || state.scan.kind !== "ready") {
      if (this.#bar !== null) this.teardown();
      return;
    }
    const items = selectItems(state);
    if (this.#bar !== null && items === this.#items && !hasChanged(state, previous, (s) => s.url.filter, selectResults)) return;
    if (this.#bar === null || items !== this.#items) {
      this.#items = items;
      this.#bar = build(items);
      this.#bar.root.addEventListener("click", (event) => {
        if (this.#latest !== null) onClick(event, this.#latest.url.filter);
      });
      this.replaceChildren(this.#bar.root);
    }
    const { filter } = state.url;
    const { count, reset, root, total } = this.#bar;
    pressed(root, "[data-group=verdicts]", (button) => filter.verdicts.includes(button.dataset.value as Verdict));
    pressed(root, "[data-group=sources]", (button) => filter.sources.includes(button.dataset.value as Source));
    pressed(root, "[data-facet]", (button) => filter[button.dataset.facet as Facet] === button.dataset.value);
    count.data = numberFormat.format(selectResults(state).length);
    total.data = numberFormat.format(items.length);
    reset.disabled = !isFilterActive(filter);
  }
}

define("filter-bar", FilterBar);
