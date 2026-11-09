/**
 * The one store behind every widget; the element contract is in
 * DOCS-ui-contract.md. State is immutable and slices keep their identity.
 *
 * Elements read only through the store (StoreElement subscribes while
 * connected) and write only through actions.ts. Compare slices with `===`;
 * take derived data from selectors.ts. An element renders only while its
 * view is active and owns exactly the DOM listed in the contract.
 */
import type { Scan, ScanProgress } from "../lib/schema.ts";
import type { SelectionState } from "../lib/selection.ts";
import type { UrlState } from "../lib/url-state.ts";

import { EMPTY_SELECTION } from "../lib/selection.ts";
import { DEFAULT_STATE } from "../lib/url-state.ts";

export type ScanState =
  | { readonly kind: "error"; readonly message: string }
  | { readonly kind: "loading" }
  | {
      readonly kind: "ready";
      readonly refreshError: null | string;
      readonly refreshing: boolean;
      readonly scan: Scan;
    };

export interface AppState {
  readonly dismissedErrorKey: null | string;
  readonly helpOpen: boolean;
  readonly progress: null | ScanProgress;
  readonly scan: ScanState;
  readonly selection: SelectionState;
  readonly url: UrlState;
}

export type Listener = (state: AppState, previous: AppState) => void;

export interface Store {
  getState: () => AppState;
  set: (patch: Partial<AppState>) => void;
  subscribe: (listener: Listener) => () => void;
}

export function initialState(): AppState {
  return {
    dismissedErrorKey: null,
    helpOpen: false,
    progress: null,
    scan: { kind: "loading" },
    selection: EMPTY_SELECTION,
    url: DEFAULT_STATE,
  };
}

export function createStore(initial: AppState = initialState()): Store {
  let state = initial;
  const listeners = new Set<Listener>();
  const queue: (readonly [AppState, AppState])[] = [];
  let isDraining = false;

  // A listener may dispatch: its update is queued, so states arrive in order.
  function drain(): void {
    if (isDraining) return;
    isDraining = true;
    try {
      for (const [state, previous] of queue) {
        for (const listener of listeners) listener(state, previous);
      }
    } finally {
      queue.length = 0;
      isDraining = false;
    }
  }

  return {
    getState: () => state,
    set(patch): void {
      const previous = state;
      const next = { ...previous, ...patch };
      const isSame = (Object.keys(patch) as (keyof AppState)[]).every((key) => previous[key] === next[key]);
      if (isSame) return;
      state = next;
      queue.push([next, previous]);
      drain();
    },
    subscribe(listener): () => void {
      listeners.add(listener);
      return (): void => {
        listeners.delete(listener);
      };
    },
  };
}

export const store: Store = createStore();

export function resetStore(): void {
  store.set(initialState());
}
