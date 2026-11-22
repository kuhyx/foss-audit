import type { Column } from "../lib/columns.ts";
import type { Item } from "../lib/schema.ts";
import type { HeaderCheck } from "../lib/selection.ts";
import type { SortState } from "../lib/url-state.ts";

import { COLUMNS } from "../lib/columns.ts";
import { type RankKind, rankLabel, type RankTotals, unrankedLabel } from "../lib/rank.ts";
import { isToReplace } from "../lib/verdict.ts";
import { ROW_HEIGHT } from "../lib/virtual.ts";
import { html } from "./dom.ts";
import { glyph, GLYPH, type GlyphName, named, rankMark } from "./glyph.ts";
import { verdictBadge } from "./verdict-badge.ts";

const ARIA_SORT = { asc: "ascending", desc: "descending" } as const;
const SORT_MARK = { asc: "▲", desc: "▼" } as const;

// Header glyph per column id (COLUMNS); the header word is the button's spoken name.
const HEADER_GLYPHS: Readonly<Record<string, GlyphName>> = {
  alternative: "alternative",
  effort: "effort",
  fit: "fit",
  installed: "installed",
  kind: "kind",
  license: "license",
  name: "name",
  orphan: "orphan",
  requiredBy: "requiredBy",
  source: "source",
  verdict: "verdict",
  version: "version",
};

const BADGES: readonly (readonly ["dangling" | "loose" | "own", string])[] = [
  ["own", "kuhy's own code"],
  ["loose", "in ~/.local/bin, no repo or package tracks it"],
  ["dangling", "a .desktop launcher whose Exec target no longer exists"],
];

function nameCell(item: Item): (Node | string)[] {
  const cell: (Node | string)[] = [item.name];
  for (const [flag, spoken] of BADGES) {
    if (item[flag]) cell.push(" ", named(flag, spoken, "badge badge-own"));
  }
  return cell;
}

// The rank number, or the warning glyph for an unranked item; FOSS rows and rows without rank fields stay empty.
function rankCell(kind: RankKind, item: Item, totals: RankTotals): Node | null {
  if (!isToReplace(item)) return null;
  if (item.unranked) return named("warning", unrankedLabel(kind));
  const rank = kind === "fit" ? item.fitRank : item.effortRank;
  const spoken = rankLabel(kind, item, totals);
  return rank === null || spoken === null ? null : rankMark(rank, spoken, item.rankReason);
}

function textNode(text: string): Node | null {
  return text === "" ? null : document.createTextNode(text);
}

// On a to-replace row an empty answer is painted ("none": ∅ ✕ 0); FOSS rows keep their empty cells.
function noneCell(column: Column, item: Item): Node | null {
  const alt = item.alternative;
  const isReplace = isToReplace(item);
  switch (column.id) {
    case "alternative": {
      return isReplace && (alt?.names.length ?? 0) === 0 ? named("empty", "No alternative") : textNode(column.text(item));
    }
    case "installed": {
      return isReplace && (alt?.installed.length ?? 0) === 0 ? named("empty", "Nothing installed") : textNode(column.text(item));
    }
    case "orphan": {
      if (item.orphan) return named("orphan", "orphan");
      return isReplace ? glyph(GLYPH.no, "not an orphan") : null;
    }
    default: {
      // requiredBy: the only other column that gets here.
      return textNode(isReplace ? String(item.requiredBy.length) : column.text(item));
    }
  }
}

// Enum cells are glyphs (spoken as the old word); names, versions, licences and alternatives are content.
function glyphCell(column: Column, item: Item, totals: RankTotals): Node | null {
  switch (column.id) {
    case "effort": {
      return rankCell("effort", item, totals);
    }
    case "fit": {
      return rankCell("fit", item, totals);
    }
    case "kind": {
      return named(item.explicit ? "explicit" : "dependency", column.text(item));
    }
    case "verdict": {
      return verdictBadge(item.verdict);
    }
    default: {
      return noneCell(column, item);
    }
  }
}

const GLYPH_COLUMNS: ReadonlySet<string> = new Set([
  "alternative",
  "effort",
  "fit",
  "installed",
  "kind",
  "orphan",
  "requiredBy",
  "verdict",
]);

function cellContent(column: Column, item: Item, totals: RankTotals): (Node | string)[] {
  if (column.id === "name") return nameCell(item);
  if (!GLYPH_COLUMNS.has(column.id)) return [column.text(item)];
  const node = glyphCell(column, item, totals);
  return node === null ? [] : [node];
}

export function buildHeaderCheckbox(): HTMLInputElement {
  return html("input", { "aria-label": "Select all shown", class: "check", type: "checkbox" });
}

export function buildHeader(headerCheckbox: HTMLInputElement): HTMLElement {
  const columns = COLUMNS.map((column) => {
    const mark = html("span", { "aria-hidden": "true", class: "sort-mark" });
    const symbol = html("span", { "aria-hidden": "true", class: "icon" }, GLYPH[HEADER_GLYPHS[column.id] ?? "name"]);
    const button = html("button", { "aria-label": column.header, class: "th-button", "data-column": column.id, type: "button" }, symbol, mark);
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

export function buildRow(item: Item, index: number, totals: RankTotals): HTMLElement {
  const check = html("input", { "aria-label": `Select ${item.name}`, class: "check", tabindex: -1, type: "checkbox" });
  const cells = COLUMNS.map((column) => html("div", { class: "td", role: "cell" }, ...cellContent(column, item, totals)));
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
    html(
      "p",
      { "aria-label": "No items match these filters. Reset the filters or clear the search to see everything.", class: "large-empty-icon muted", role: "img" },
      GLYPH.empty,
    ),
  );
}
