import type { Verdict } from "../lib/schema.ts";

import { VERDICT_HINTS } from "../lib/verdict.ts";
import { html } from "./dom.ts";
import { verdictMark } from "./glyph.ts";

// The verdict's shape + colour mark; the label and hint are spoken only (no words, no tooltip).
export function verdictBadge(verdict: Verdict): HTMLElement {
  return html("span", { "aria-description": VERDICT_HINTS[verdict], class: "verdict" }, verdictMark(verdict));
}
