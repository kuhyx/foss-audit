import type { Item } from "../lib/schema.ts";
import type { UrlState } from "../lib/url-state.ts";

import { store } from "../client/store.ts";
import { DEFAULT_STATE } from "../lib/url-state.ts";
import { makeScan } from "./fixtures.ts";

export function showTable(items: readonly Item[], url: Partial<UrlState> = {}): void {
  const scan = makeScan({ items: [...items] });
  store.set({
    scan: { kind: "ready", refreshError: null, refreshing: false, scan },
    url: { ...DEFAULT_STATE, view: "table", ...url },
  });
}

export function mount(tag: string): HTMLElement {
  const element = document.createElement(tag);
  document.body.append(element);
  return element;
}

// Typed like querySelector: the caller names the element type it expects.
// eslint-disable-next-line @typescript-eslint/no-unnecessary-type-parameters
export function find<T extends Element = HTMLElement>(root: ParentNode, selector: string): T {
  const found = root.querySelector<T>(selector);
  if (found === null) throw new Error(`no ${selector}`);
  return found;
}

export function click(element: Element, init: MouseEventInit = {}): void {
  element.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, ...init }));
}

export function press(element: Element, key: string, init: KeyboardEventInit = {}): void {
  element.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key, ...init }));
}
