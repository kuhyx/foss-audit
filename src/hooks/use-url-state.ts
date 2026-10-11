/**
 * View state stored in the URL query string.
 *
 * Hand-rolled over `useSyncExternalStore` and the History API, as in
 * awesome-mcp-explorer: a router would be the largest dependency here, and the
 * query string as source of truth means Back works, reload restores the view
 * and the address bar is always a shareable link.
 */
import { useSyncExternalStore } from "react";

import type { UrlState } from "../lib/url-state.ts";

import { decodeState, encodeState } from "../lib/url-state.ts";

function subscribe(onChange: () => void): () => void {
  globalThis.addEventListener("popstate", onChange);
  return (): void => {
    globalThis.removeEventListener("popstate", onChange);
  };
}

function getSearch(): string {
  return globalThis.location.search;
}

export interface UpdateOptions {
  /**
   * pushState instead of replaceState: for tab switches and summary
   * click-throughs, where Back should return to the previous view. Typing in
   * search stays on replaceState so it does not bury history in keystrokes.
   */
  readonly push?: boolean;
}

export type UpdateState = (
  patch: (current: UrlState) => UrlState,
  options?: UpdateOptions,
) => void;

/**
 * Writes a new state derived from the *current* URL, never from the value
 * captured at render time. Two updates from one handler (or a memoised
 * callback the React Compiler kept from an older render) therefore compose
 * instead of the second silently undoing the first.
 */
export const updateState: UpdateState = (patch, options = {}) => {
  const next = patch(decodeState(globalThis.location.search));
  const query = encodeState(next);
  const url = query === "" ? globalThis.location.pathname : `?${query}`;
  if (options.push === true) globalThis.history.pushState(null, "", url);
  else globalThis.history.replaceState(null, "", url);
  globalThis.dispatchEvent(new PopStateEvent("popstate"));
};

export function useUrlState(): UrlState {
  // No getServerSnapshot: this app never renders on a server.
  const search = useSyncExternalStore(subscribe, getSearch);
  return decodeState(search);
}
