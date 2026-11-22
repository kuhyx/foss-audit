/**
Row and header lookups shared by the items-table test files.
*/
import { makeItem } from "./fixtures.ts";
import { find, spoken } from "./table-setup.ts";

export const NAME = 1;
export const FIT = 10;
export const LETTERS = ["d", "a", "e", "c", "b"].map((name) => makeItem({ name }));

export function rows(root: ParentNode): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(".tr.row")];
}

export function column(root: ParentNode, index: number): string[] {
  return rows(root).map((row) => spoken(row.querySelectorAll(".td")[index] ?? document.createTextNode("")));
}

export function box(root: ParentNode, name: string): HTMLInputElement {
  return find<HTMLInputElement>(root, `input[aria-label="Select ${name}"]`);
}

export function header(root: ParentNode): HTMLInputElement {
  return find<HTMLInputElement>(root, 'input[aria-label="Select all shown"]');
}

export function head(root: ParentNode, label: string): HTMLElement {
  const found = [...root.querySelectorAll<HTMLElement>(".th-button")].find((button) => button.getAttribute("aria-label") === label);
  if (found === undefined) throw new Error(`no ${label} header`);
  return found;
}

export function stubScrollTop(scroller: HTMLElement): { top: number } {
  const position = { top: 0 };
  Object.defineProperty(scroller, "scrollTop", {
    configurable: true,
    get: () => position.top,
    set: (value: number) => {
      position.top = value;
    },
  });
  return position;
}
