/**
 * The table's multi-selection, in memory only: not in the URL (it can be
 * thousands of ids) and not in localStorage (it is a working set, not a
 * preference). Owned by App so it outlives view switches and empty filters.
 */
import { useState } from "react";

import type { SelectionState } from "../lib/selection.ts";

import { clickRow, EMPTY_SELECTION, setRows } from "../lib/selection.ts";

export interface Selection {
  readonly clear: () => void;
  readonly click: (id: string, order: readonly string[], isShift: boolean) => void;
  readonly ids: ReadonlySet<string>;
  readonly set: (ids: readonly string[], isOn: boolean) => void;
}

export function useSelection(): Selection {
  const [state, setState] = useState<SelectionState>(EMPTY_SELECTION);
  return {
    clear: (): void => {
      setState(EMPTY_SELECTION);
    },
    click: (id, order, isShift): void => {
      setState((current) => clickRow(current, id, order, isShift));
    },
    ids: state.ids,
    set: (ids, isOn): void => {
      setState((current) => setRows(current, ids, isOn));
    },
  };
}
