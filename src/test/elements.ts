/**
 * Helpers for the custom-element tests: mount into the document, put the
 * store in a known state, and give jsdom the `<dialog>` methods it lacks.
 */
import type { Scan } from "../lib/schema.ts";
import type { View } from "../lib/url-state.ts";

import { resetStore, store } from "../client/store.ts";
import { DEFAULT_STATE } from "../lib/url-state.ts";
import { makeScan } from "./fixtures.ts";

export function mount(tag: string, attributes: Readonly<Record<string, string>> = {}): HTMLElement {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
  document.body.append(element);
  return element;
}

// A ready scan shown in `view`, with `selected` open.
export function showScan(view: View, scan: Scan = makeScan(), selected: null | string = null): void {
  store.set({
    scan: { kind: "ready", refreshError: null, refreshing: false, scan },
    url: { ...DEFAULT_STATE, selected, view },
  });
}

export function resetDocument(): void {
  document.body.replaceChildren();
  globalThis.history.replaceState(null, "", "/");
  resetStore();
}

/**
 * jsdom (30.x) has HTMLDialogElement but no showModal/show/close. These keep
 * the `open` attribute and the `close` event as a browser would.
 */
export function stubDialog(): void {
  const prototype = HTMLDialogElement.prototype;
  prototype.showModal = function showModal(this: HTMLDialogElement): void {
    this.setAttribute("open", "");
  };
  prototype.close = function close(this: HTMLDialogElement): void {
    if (!this.hasAttribute("open")) return;
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}
