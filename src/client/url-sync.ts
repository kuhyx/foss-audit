import type { UrlState } from "../lib/url-state.ts";

import { decodeState } from "../lib/url-state.ts";
import { store } from "./store.ts";

// Decoding builds fresh objects; keep the old ones when nothing changed so slice-identity checks hold.
export function reuseUnchanged(previous: UrlState, next: UrlState): UrlState {
  const filter = JSON.stringify(previous.filter) === JSON.stringify(next.filter) ? previous.filter : next.filter;
  const sort = JSON.stringify(previous.sort) === JSON.stringify(next.sort) ? previous.sort : next.sort;
  return { ...next, filter, sort };
}

function sync(): void {
  store.set({ url: reuseUnchanged(store.getState().url, decodeState(globalThis.location.search)) });
}

// Returns stop(). Writes to the URL go through actions.navigate().
export function startUrlSync(): () => void {
  sync();
  globalThis.addEventListener("popstate", sync);
  return (): void => {
    globalThis.removeEventListener("popstate", sync);
  };
}
