/**
 * The all-items table: TanStack Table for sorting, TanStack Virtual for rows.
 *
 * Only the visible window of ~3,100 rows is mounted. The header sits inside
 * the same scroller (sticky) so it scrolls horizontally with the body when the
 * detail panel narrows the view below the columns' minimum width.
 *
 * Keyboard: the scroller is a focus stop. ArrowUp/ArrowDown move the selection
 * (opening the detail panel) and scroll it into view; PageUp/PageDown/Home/End
 * scroll natively because the focused element is the scroller itself.
 */
import type { SortingState, Updater } from "@tanstack/react-table";

import { FlexRender, functionalUpdate, useTable } from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useRef } from "react";

import type { Item } from "../lib/schema.ts";
import type { SortState } from "../lib/url-state.ts";

import { elementAt } from "../lib/array.ts";
import { COLUMN_TRACKS, columns, features } from "./columns.tsx";

export interface ItemsTableProps {
  readonly items: readonly Item[];
  readonly onSelect: (id: string) => void;
  readonly onSort: (sort: null | SortState) => void;
  readonly selected: null | string;
  readonly sort: null | SortState;
}

const ROW_HEIGHT = 40;

const ARIA_SORT = { asc: "ascending", desc: "descending" } as const;
const SORT_MARK = { asc: "▲", desc: "▼" } as const;

export function ItemsTable({
  items,
  onSelect,
  onSort,
  selected,
  sort,
}: ItemsTableProps): React.JSX.Element {
  // Opted out of the React Compiler. Both TanStack instances are stable
  // objects that mutate in place, and their reads (getRowModel,
  // getVirtualItems) are method calls the compiler cannot see as reactive.
  // Memoised against the stable instance, the first window renders correctly
  // and then goes stale on scroll, sort or filter.
  "use no memo";
  const scrollReference = useRef<HTMLDivElement>(null);
  const sorting: SortingState = sort === null ? [] : [{ desc: sort.desc, id: sort.id }];

  const table = useTable({
    columns,
    data: items,
    enableMultiSort: false,
    features,
    getRowId: (item) => item.id,
    onSortingChange: (updater: Updater<SortingState>): void => {
      const next = functionalUpdate(updater, sorting);
      const first = next[0];
      onSort(first === undefined ? null : { desc: first.desc, id: first.id });
    },
    sortDescFirst: false,
    state: { sorting },
  });

  const rows = table.getRowModel().rows;
  // The warning this silences says the compiler cannot memoise
  // useVirtualizer safely. That is exactly why this component carries
  // "use no memo" above; the directive is the fix the warning asks for.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: rows.length,
    estimateSize: () => ROW_HEIGHT,
    getScrollElement: () => scrollReference.current,
    overscan: 12,
    // The sticky header occupies the top of the scroller; without this,
    // scrollToIndex parks the target row underneath it.
    scrollPaddingStart: ROW_HEIGHT,
  });

  const selectedIndex = rows.findIndex((row) => row.original.id === selected);
  useEffect(() => {
    if (selectedIndex !== -1) virtualizer.scrollToIndex(selectedIndex, { align: "auto" });
  }, [selectedIndex, virtualizer]);

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>): void {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const isDown = event.key === "ArrowDown";
    // With nothing selected, Down starts at the first row and Up at the last.
    const unselectedTarget = isDown ? 0 : rows.length - 1;
    const delta = isDown ? 1 : -1;
    const index = selectedIndex === -1 ? unselectedTarget : selectedIndex + delta;
    const target = rows[Math.min(rows.length - 1, Math.max(0, index))];
    if (target !== undefined) onSelect(target.original.id);
  }

  if (rows.length === 0) {
    return (
      <div className="table-empty">
        <p>No items match these filters.</p>
        <p className="muted">Reset the filters or clear the search to see everything.</p>
      </div>
    );
  }

  return (
    <div
      aria-label="Installed items. Arrow keys move the selection."
      aria-rowcount={rows.length + 1}
      className="table-scroll"
      onKeyDown={onKeyDown}
      ref={scrollReference}
      role="table"
      style={{ "--tracks": COLUMN_TRACKS } as React.CSSProperties}
      tabIndex={0}
    >
      <div className="thead" role="rowgroup">
        {table.getHeaderGroups().map((group) => {
          return (
            <div className="tr" key={group.id} role="row">
              {group.headers.map((header) => {
                const direction = header.column.getIsSorted();
                return (
                  <div
                    aria-sort={direction === false ? "none" : ARIA_SORT[direction]}
                    className="th"
                    key={header.id}
                    role="columnheader"
                  >
                    <button
                      className="th-button"
                      onClick={header.column.getToggleSortingHandler()}
                      type="button"
                    >
                      <FlexRender header={header} />
                      <span aria-hidden="true" className="sort-mark">
                        {direction === false ? "" : SORT_MARK[direction]}
                      </span>
                    </button>
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
      <div className="tbody" role="rowgroup" style={{ height: virtualizer.getTotalSize() }}>
        {virtualizer.getVirtualItems().map((virtual) => {
          // elementAt, not a guard: the virtualizer only yields indices below
          // `count`, so an undefined check would be an unreachable branch.
          const row = elementAt(rows, virtual.index);
          const isSelected = row.original.id === selected;
          return (
            <div
              aria-rowindex={virtual.index + 2}
              aria-selected={isSelected}
              className="tr row"
              data-id={row.original.id}
              key={row.id}
              onClick={(): void => {
                onSelect(row.original.id);
              }}
              role="row"
              style={{ transform: `translateY(${virtual.start}px)` }}
            >
              {row.getAllCells().map((cell) => {
                return (
                  <div className="td" key={cell.id} role="cell">
                    <FlexRender cell={cell} />
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
