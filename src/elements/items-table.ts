import type { AppState } from "../client/store.ts";
import type { Item } from "../lib/schema.ts";
import type { SortState } from "../lib/url-state.ts";
import type { ArrowKey, RowRange } from "../lib/virtual.ts";

import { clickRow, openItem, setRowsChecked, setSort } from "../client/actions.ts";
import { selectResults } from "../client/selectors.ts";
import { define, hasChanged, StoreElement } from "../client/store-element.ts";
import { elementAt } from "../lib/array.ts";
import { COLUMN_TRACKS } from "../lib/columns.ts";
import { headerCheck } from "../lib/selection.ts";
import { nextSort, sortItems } from "../lib/sort.ts";
import { arrowTarget, ROW_HEIGHT, scrollTopToReveal, visibleRange } from "../lib/virtual.ts";
import { html } from "../render/dom.ts";
import {
  buildEmpty,
  buildHeader,
  buildHeaderCheckbox,
  buildRow,
  showHeaderCheck,
  showRow,
  showSort,
} from "../render/table-rows.ts";

type Mode = "empty" | "none" | "table";

interface Table {
  readonly body: HTMLElement;
  readonly header: HTMLElement;
  readonly headerBox: HTMLInputElement;
  readonly observer: ResizeObserver;
  readonly scroller: HTMLElement;
}

function rowOf(target: EventTarget | null): HTMLElement | null {
  return target instanceof Element ? target.closest<HTMLElement>(".tr.row") : null;
}

function isArrow(key: string): key is ArrowKey {
  return key === "ArrowDown" || key === "ArrowUp";
}

export class ItemsTable extends StoreElement {
  #adopted: null | readonly Item[] = null;
  #index: null | { readonly id: string; readonly index: number; readonly order: readonly string[] } = null;
  #mode: Mode = "none";
  #nodes = new Map<number, HTMLElement>();
  #order: readonly string[] = [];
  #range: null | RowRange = null;
  #revealLater: null | number = null;
  #sorted: readonly Item[] = [];
  #sortedFrom: null | { readonly results: readonly Item[]; readonly sort: null | SortState } = null;
  #state: AppState | null = null;
  #table: null | Table = null;

  #adopt(table: Table, sorted: readonly Item[]): void {
    this.#adopted = sorted;
    this.#order = sorted.map((item) => item.id);
    this.#nodes.clear();
    this.#range = null;
    table.body.replaceChildren();
    table.body.style.height = `${sorted.length * ROW_HEIGHT}px`;
  }

  #build(): Table {
    const headerBox = buildHeaderCheckbox();
    const header = buildHeader(headerBox);
    const body = html("div", { class: "tbody", role: "rowgroup" });
    const scroller = html(
      "div",
      { "aria-label": "Installed items. Arrow keys move the selection.", class: "table-scroll", role: "table" },
      header,
      body,
    );
    scroller.style.setProperty("--tracks", COLUMN_TRACKS);
    scroller.addEventListener("scroll", () => {
      this.#renderRows(false);
    });
    scroller.addEventListener("click", (event) => {
      this.#onClick(event);
    });
    scroller.addEventListener("keydown", (event) => {
      this.#onKeyDown(event);
    });
    const observer = new ResizeObserver(() => {
      const later = this.#revealLater;
      if (later !== null && scroller.clientHeight > 0) {
        this.#revealLater = null;
        this.#reveal(later);
      }
      this.#renderRows(false);
    });
    observer.observe(scroller);
    this.replaceChildren(scroller);
    return { body, header, headerBox, observer, scroller };
  }

  #current(): AppState {
    if (this.#state === null) throw new Error("items-table has no state yet");
    return this.#state;
  }

  #focusRow(id: string): void {
    const index = this.#indexOf(id);
    if (index === -1) return;
    this.#reveal(index);
    this.#renderRows(true);
    this.#nodes.get(index)?.focus({ preventScroll: true });
  }

  #indexOf(id: string): number {
    if (this.#index?.id === id && this.#index.order === this.#order) return this.#index.index;
    const index = this.#order.indexOf(id);
    this.#index = { id, index, order: this.#order };
    return index;
  }

  #onClick(event: MouseEvent): void {
    const { target } = event;
    if (!(target instanceof HTMLElement)) return;
    const state = this.#current();
    const button = target.closest<HTMLElement>(".th-button");
    if (button !== null) {
      setSort(nextSort(state.url.sort, button.dataset.column ?? ""));
      return;
    }
    if (target.matches(".thead input.check")) {
      setRowsChecked(this.#order, headerCheck(state.selection.ids, this.#order) !== "all");
      return;
    }
    const row = rowOf(target);
    const id = row?.dataset.id;
    if (row === null || id === undefined) return;
    if (target.matches("input.check")) clickRow(id, this.#order, event.shiftKey);
    else openItem(id);
    row.focus({ preventScroll: true });
  }

  #onKeyDown(event: KeyboardEvent): void {
    const { target } = event;
    if (!(target instanceof HTMLElement) || !target.matches(".tr.row, .table-scroll")) return;
    const rowId = target.dataset.id;
    if (rowId !== undefined && event.key === " ") {
      event.preventDefault();
      clickRow(rowId, this.#order, event.shiftKey);
    } else if (rowId !== undefined && event.key === "Enter") {
      event.preventDefault();
      openItem(rowId);
    } else if (isArrow(event.key)) {
      event.preventDefault();
      this.#moveSelection(rowId ?? this.#current().url.selected, event.key);
    }
  }

  #moveSelection(from: null | string, key: ArrowKey): void {
    const current = from === null ? -1 : this.#indexOf(from);
    const id = elementAt(this.#order, arrowTarget(current, this.#order.length, key));
    openItem(id);
    this.#focusRow(id);
  }

  #renderRows(isForced: boolean): void {
    const table = this.#table;
    if (table === null) return;
    const { scroller } = table;
    const range = visibleRange(scroller.scrollTop, scroller.clientHeight, this.#sorted.length);
    if (!isForced && this.#range?.start === range.start && this.#range.end === range.end) return;
    this.#range = range;
    const state = this.#current();
    const { selected } = state.url;
    const selectedIndex = selected === null ? -1 : this.#indexOf(selected);
    const activeIndex = selectedIndex >= range.start && selectedIndex < range.end ? selectedIndex : range.start;
    this.#trim(range);
    let cursor = table.body.firstElementChild;
    for (let index = range.start; index < range.end; index += 1) {
      let node = this.#nodes.get(index);
      if (node === undefined) {
        node = buildRow(elementAt(this.#sorted, index), index);
        this.#nodes.set(index, node);
      }
      if (node === cursor) cursor = cursor.nextElementSibling;
      else table.body.insertBefore(node, cursor);
      const id = elementAt(this.#order, index);
      showRow(node, { isActive: index === activeIndex, isChecked: state.selection.ids.has(id), isSelected: index === selectedIndex });
    }
  }

  #trim(range: RowRange): void {
    for (const [index, node] of this.#nodes) {
      if (index >= range.start && index < range.end) continue;
      node.remove();
      this.#nodes.delete(index);
    }
  }

  // A hidden view has no height yet: the resize observer finishes the job once it is shown.
  #reveal(index: number): void {
    const scroller = this.#table?.scroller;
    if (scroller === undefined) return;
    if (scroller.clientHeight === 0) {
      this.#revealLater = index;
      return;
    }
    scroller.scrollTop = scrollTopToReveal(index, scroller.scrollTop, scroller.clientHeight);
  }

  #showEmpty(): void {
    this.#release();
    this.#mode = "empty";
    this.replaceChildren(buildEmpty());
  }

  #release(): void {
    this.#table?.observer.disconnect();
    this.#table = null;
    this.#nodes.clear();
    this.#range = null;
    this.#revealLater = null;
    this.#adopted = null;
    this.#order = [];
    this.#mode = "none";
  }

  #sortedFor(results: readonly Item[], sort: null | SortState): readonly Item[] {
    if (this.#sortedFrom?.results !== results || this.#sortedFrom.sort !== sort) {
      this.#sortedFrom = { results, sort };
      this.#sorted = sortItems(results, sort);
    }
    return this.#sorted;
  }

  protected override teardown(): void {
    this.#release();
    this.#sortedFrom = null;
    super.teardown();
  }

  protected override update(state: AppState, previous: AppState | null): void {
    this.#state = state;
    if (state.url.view !== "table" || state.scan.kind !== "ready") {
      if (this.#mode !== "none") this.teardown();
      return;
    }
    const watched = [selectResults, (s: AppState) => s.url.sort, (s: AppState) => s.url.selected, (s: AppState) => s.selection];
    if (this.#mode !== "none" && !hasChanged(state, previous, ...watched)) return;
    const sorted = this.#sortedFor(selectResults(state), state.url.sort);
    if (sorted.length === 0) {
      this.#showEmpty();
      return;
    }
    const isNew = this.#table === null;
    const table = this.#table ?? this.#build();
    this.#table = table;
    this.#mode = "table";
    if (this.#adopted !== sorted) this.#adopt(table, sorted);
    if (isNew || previous?.url.sort !== state.url.sort) showSort(table.header, state.url.sort);
    showHeaderCheck(table.headerBox, headerCheck(state.selection.ids, this.#order));
    const { selected } = state.url;
    const before = previous?.url.selected ?? null;
    if (selected !== null && (isNew || selected !== before)) this.#reveal(this.#indexOf(selected));
    this.#renderRows(true);
    if (selected === null && before !== null) this.#focusRow(before);
  }
}

define("items-table", ItemsTable);
