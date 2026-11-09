import type { SortKey } from "./columns.ts";
import type { Item } from "./schema.ts";
import type { SortState } from "./url-state.ts";

import { elementAt } from "./array.ts";
import { COLUMNS } from "./columns.ts";

export function nextSort(current: null | SortState, id: string): null | SortState {
  if (current?.id !== id) return { desc: false, id };
  return current.desc ? null : { desc: true, id };
}

function comparable(key: SortKey): SortKey {
  return typeof key === "string" ? key.toLowerCase() : key;
}

// Absent keys stay last in both directions; ties keep the scan order.
export function sortItems(items: readonly Item[], sort: null | SortState): readonly Item[] {
  const column = COLUMNS.find((candidate) => candidate.id === sort?.id);
  if (sort === null || column === undefined) return items;
  const keys = items.map((item) => comparable(column.sortKey(item)));
  const direction = sort.desc ? -1 : 1;
  const order = items.map((_, index) => index);
  order.sort((a, b) => {
    const keyA = keys[a];
    const keyB = keys[b];
    if (keyA === keyB) return a - b;
    if (keyA === undefined) return 1;
    if (keyB === undefined) return -1;
    return keyA > keyB ? direction : -direction;
  });
  return order.map((index) => elementAt(items, index));
}
