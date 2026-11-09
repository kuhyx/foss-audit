export type Child = Node | null | number | string | undefined;

export type Attributes = Readonly<Record<string, boolean | null | number | string | undefined>>;

// Builds an element. Children are text nodes or nodes, never HTML, so values cannot inject markup.
export function html<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attributes: Attributes = {},
  ...children: readonly Child[]
): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (value === undefined || value === null || value === false) continue;
    element.setAttribute(name, value === true ? "" : String(value));
  }
  for (const child of children) {
    if (child === undefined || child === null) continue;
    element.append(typeof child === "object" ? child : String(child));
  }
  return element;
}
