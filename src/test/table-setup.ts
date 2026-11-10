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

/**
 * What a screen reader says for `node`: text, with every role="img" glyph read
 * as its aria-label and aria-hidden parts skipped. Space-joined, trimmed.
 */
export function spoken(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? "";
  if (!(node instanceof Element) || node.getAttribute("aria-hidden") === "true") return "";
  if (node.getAttribute("role") === "img") return ` ${node.getAttribute("aria-label") ?? ""} `;
  return [...node.childNodes].map((child) => spoken(child)).join("").replaceAll(/\s+/gu, " ").trim();
}

// The words painted inside `node` (2+ letter runs), for "no visible words" checks.
export function paintedWords(node: Element): string[] {
  const words: string[] = [];
  const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
  for (let text = walker.nextNode(); text !== null; text = walker.nextNode()) {
    // aria-hidden only silences a node; it still paints, so it counts here.
    if (text.parentElement?.closest(".sr-only") != null) continue;
    words.push(...(text.textContent?.match(/[A-Za-z]{2,}/gu) ?? []));
  }
  return words;
}

export function click(element: Element, init: MouseEventInit = {}): void {
  element.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, ...init }));
}

export function press(element: Element, key: string, init: KeyboardEventInit = {}): void {
  element.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key, ...init }));
}
