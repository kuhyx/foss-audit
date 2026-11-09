import type { Column } from "../lib/columns.ts";
import type { Item } from "../lib/schema.ts";
import type { HeaderCheck } from "../lib/selection.ts";
import type { SortState } from "../lib/url-state.ts";

import { COLUMNS } from "../lib/columns.ts";
import { ROW_HEIGHT } from "../lib/virtual.ts";
import { html } from "./dom.ts";
import { verdictBadge } from "./verdict-badge.ts";

const ARIA_SORT = { asc: "ascending", desc: "descending" } as const;
const SORT_MARK = { asc: "▲", desc: "▼" } as const;

const BADGES: readonly (readonly ["dangling" | "loose" | "own", string, string])[] = [
  ["own", "own", "kuhy's own code"],
  ["loose", "loose", "in ~/.local/bin, no repo or package tracks it"],
  ["dangling", "dead", "a .desktop launcher whose Exec target no longer exists"],
];

function nameCell(item: Item): (Node | string)[] {
  const cell: (Node | string)[] = [item.name];
  for (const [flag, label, title] of BADGES) {
    if (item[flag]) cell.push(" ", html("span", { class: "badge badge-own", title }, label));
  }
  return cell;
}

function cellContent(column: Column, item: Item): (Node | string)[] {
  if (column.id === "name") return nameCell(item);
  return [column.id === "verdict" ? verdictBadge(item.verdict) : column.text(item)];
}

export function buildHeaderCheckbox(): HTMLInputElement {
  return html("input", { "aria-label": "Select all shown", class: "check", type: "checkbox" });
}

export function buildHeader(headerCheckbox: HTMLInputElement): HTMLElement {
  const columns = COLUMNS.map((column) => {
    const mark = html("span", { "aria-hidden": "true", class: "sort-mark" });
    const button = html("button", { class: "th-button", "data-column": column.id, type: "button" }, column.header, mark);
    return html("div", { "aria-sort": "none", class: "th", role: "columnheader" }, button);
  });
  const check = html("div", { class: "th th-check", role: "columnheader" }, headerCheckbox);
  return html("div", { class: "thead", role: "rowgroup" }, html("div", { class: "tr", role: "row" }, check, ...columns));
}

function directionOf(sort: null | SortState, id: string | undefined): "asc" | "desc" | null {
  if (sort === null || sort.id !== id) return null;
  return sort.desc ? "desc" : "asc";
}

export function showSort(header: HTMLElement, sort: null | SortState): void {
  for (const button of header.querySelectorAll<HTMLElement>(".th-button")) {
    const direction = directionOf(sort, button.dataset.column);
    button.parentElement?.setAttribute("aria-sort", direction === null ? "none" : ARIA_SORT[direction]);
    const mark = button.querySelector(".sort-mark");
    if (mark !== null) mark.textContent = direction === null ? "" : SORT_MARK[direction];
  }
}

export function showHeaderCheck(box: HTMLInputElement, state: HeaderCheck): void {
  box.checked = state === "all";
  box.indeterminate = state === "some";
}

export function buildRow(item: Item, index: number): HTMLElement {
  const check = html("input", { "aria-label": `Select ${item.name}`, class: "check", tabindex: -1, type: "checkbox" });
  const cells = COLUMNS.map((column) => html("div", { class: "td", role: "cell" }, ...cellContent(column, item)));
  const row = html(
    "div",
    { "aria-rowindex": index + 2, class: "tr row", "data-id": item.id, role: "row", tabindex: -1 },
    html("div", { class: "td td-check", role: "cell" }, check),
    ...cells,
  );
  row.style.transform = `translateY(${index * ROW_HEIGHT}px)`;
  return row;
}

export interface RowState {
  readonly isActive: boolean;
  readonly isChecked: boolean;
  readonly isSelected: boolean;
}

export function showRow(row: HTMLElement, state: RowState): void {
  row.setAttribute("aria-selected", String(state.isSelected));
  row.tabIndex = state.isActive ? 0 : -1;
  const box = row.querySelector<HTMLInputElement>("input.check");
  if (box !== null) box.checked = state.isChecked;
}

export function buildEmpty(): HTMLElement {
  return html(
    "div",
    { class: "table-empty" },
    html("p", {}, "No items match these filters."),
    html("p", { class: "muted" }, "Reset the filters or clear the search to see everything."),
  );
}
