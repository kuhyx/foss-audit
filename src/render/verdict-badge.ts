import type { Verdict } from "../lib/schema.ts";

import { VERDICT_COLORS, VERDICT_HINTS, VERDICT_LABELS } from "../lib/verdict.ts";
import { html } from "./dom.ts";

// A colour dot plus its label: the dot carries identity, the text never wears the categorical colour.
export function verdictBadge(verdict: Verdict): HTMLElement {
  const dot = html("span", { "aria-hidden": "true", class: "dot" });
  dot.style.background = VERDICT_COLORS[verdict];
  return html("span", { class: "verdict", title: VERDICT_HINTS[verdict] }, dot, VERDICT_LABELS[verdict]);
}
