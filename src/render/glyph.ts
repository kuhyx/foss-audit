/**
 * The UI's picture vocabulary (textgate: nothing kuhy sees is a word unless he
 * asked). Every symbol here is painted; its old wording lives on only as the
 * spoken name (`aria-label` on role="img"), never as a tooltip.
 *
 * One symbol per meaning across views: the table header, the detail panel
 * field and the filter facet for the same thing all use the same glyph.
 */
import type { Effort, Fit, Verdict } from "../lib/schema.ts";
import type { View } from "../lib/url-state.ts";

import { EFFORT_LABELS, FIT_LABELS, VERDICT_COLORS, VERDICT_LABELS } from "../lib/verdict.ts";
import { html } from "./dom.ts";

export const GLYPH = {
  alternative: "🌿",
  any: "∗",
  claude: "✦",
  close: "✕",
  copy: "⧉",
  dangling: "💀",
  dependency: "⧉",
  effort: "⚒",
  empty: "∅",
  explicit: "⚙",
  filters: "☰",
  fit: "🎯",
  free: "●◐",
  installed: "📦",
  kind: "↩",
  license: "📄",
  loose: "📎",
  name: "🏷",
  no: "✕",
  orphan: "🏝",
  own: "👤",
  remove: "🗑",
  requiredBy: "🔗",
  rescan: "⟳",
  reset: "↺",
  source: "🗃",
  total: "Σ",
  verdict: "⚖",
  version: "🔖",
  warning: "⚠",
  yes: "✓",
} as const;

export type GlyphName = keyof typeof GLYPH;

export const VIEW_GLYPHS: Readonly<Record<View, string>> = { summary: "📊", table: "▦", wins: "⚡" };

// Fullness is freeness: the shape carries the verdict without its colour.
export const VERDICT_SHAPES: Readonly<Record<Verdict, string>> = {
  foss: "●",
  "foss-partial": "◐",
  nonfree: "○",
};

// Filled bars out of three (fit) or four (effort): more filled = better fit / more work.
const FIT_BARS: Readonly<Record<Fit, string>> = { "drop-in": "▮▮▮", good: "▮▮▯", none: "▯▯▯", partial: "▮▯▯" };
const EFFORT_BARS: Readonly<Record<Effort, string>> = { L: "▮▮▮▯", M: "▮▮▯▯", S: "▮▯▯▯", XL: "▮▮▮▮" };

// A painted symbol with a spoken-only name.
export function glyph(symbol: string, spoken: string, cssClass = "icon"): HTMLElement {
  return html("span", { "aria-label": spoken, class: cssClass, role: "img" }, symbol);
}

// A named glyph from GLYPH.
export function named(name: GlyphName, spoken: string, cssClass = "icon"): HTMLElement {
  return glyph(GLYPH[name], spoken, cssClass);
}

// Verdict as shape + colour, spoken as its label.
export function verdictMark(verdict: Verdict): HTMLElement {
  const mark = glyph(VERDICT_SHAPES[verdict], VERDICT_LABELS[verdict], "verdict-mark");
  mark.dataset.verdict = verdict;
  mark.style.color = VERDICT_COLORS[verdict];
  return mark;
}

export function fitMark(fit: Fit): HTMLElement {
  return glyph(FIT_BARS[fit], `Fit: ${FIT_LABELS[fit]}`, "bars");
}

export function effortMark(effort: Effort): HTMLElement {
  return glyph(EFFORT_BARS[effort], `Effort: ${EFFORT_LABELS[effort]}`, "bars");
}

// ✓ or ✕, spoken as the full statement.
export function yesNoMark(isYes: boolean, spoken: string): HTMLElement {
  return named(isYes ? "yes" : "no", isYes ? `yes: ${spoken}` : "no");
}
