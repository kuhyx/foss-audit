/**
 * Multi-select over the all-items table, as pure state transitions.
 *
 * The selection is a set of item ids, not row indices: it survives filter and
 * sort changes, so "filter com.google, select all, filter firebase, add more"
 * builds one selection. Ranges are taken in the order the caller passes,
 * which is the table's current sorted and filtered row order.
 */
export interface SelectionState {
  /**
  Last row clicked: where the next shift-click range starts.
  */
  readonly anchor: null | string;
  readonly ids: ReadonlySet<string>;
}

export const EMPTY_SELECTION: SelectionState = { anchor: null, ids: new Set() };

/**
Adds or removes `ids` and leaves every other id (including hidden ones) alone.
*/
export function setRows(state: SelectionState, ids: readonly string[], isOn: boolean): SelectionState {
  const next = new Set(state.ids);
  for (const id of ids) {
    if (isOn) next.add(id);
    else next.delete(id);
  }
  return { anchor: state.anchor, ids: next };
}

/**
 * A click (or Space) on one row. With shift and an anchor that is still shown,
 * every row from the anchor to `id` inclusive is selected (never deselected:
 * "filter, select all, filter again, shift-add more" must not drop rows that
 * were already in). Without shift or a visible anchor it is a plain toggle.
 * Either way `id` becomes the anchor.
 */
export function clickRow(
  state: SelectionState,
  id: string,
  order: readonly string[],
  isShift: boolean,
): SelectionState {
  const from = state.anchor === null ? -1 : order.indexOf(state.anchor);
  const to = order.indexOf(id);
  const next =
    isShift && from !== -1
      ? setRows(state, order.slice(Math.min(from, to), Math.max(from, to) + 1), true)
      : setRows(state, [id], !state.ids.has(id));
  return { ...next, anchor: id };
}

export type HeaderCheck = "all" | "none" | "some";

/**
How many of the shown rows are selected, for the header checkbox.
*/
export function headerCheck(ids: ReadonlySet<string>, shown: readonly string[]): HeaderCheck {
  const count = shown.filter((id) => ids.has(id)).length;
  if (count === 0) return "none";
  return count === shown.length ? "all" : "some";
}
