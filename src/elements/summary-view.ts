/**
 * Summary: the free/not-free headline, one tile per verdict and the
 * per-source chart, over the whole scan. Every number drills into the table.
 */
import type { AppState } from "../client/store.ts";
import type { Item, Verdict } from "../lib/schema.ts";

import { drill } from "../client/actions.ts";
import { observeWidth } from "../client/observe-width.ts";
import { withRemoves } from "../client/remove-api.ts";
import { selectItems } from "../client/selectors.ts";
import { define, hasChanged, StoreElement } from "../client/store-element.ts";
import { buildBulkPrompt, isPromptCandidate } from "../lib/claude-prompt.ts";
import { VERDICTS } from "../lib/schema.ts";
import { sourceRows } from "../lib/stack.ts";
import {
  countBy,
  FREE_VERDICTS,
  NOT_FREE_VERDICTS,
  numberFormat,
  percent,
  VERDICT_COLORS,
  VERDICT_HINTS,
  VERDICT_LABELS,
} from "../lib/verdict.ts";
import { buildButton } from "../render/command.ts";
import { html } from "../render/dom.ts";
import { drawSourceChart, renderSourceChart } from "../render/source-chart.ts";

// One decimal: at ~98% integer rounding hides the change a cleanup rescan should show.
function heroPercent(part: number, whole: number): string {
  return whole === 0 ? "0%" : `${((part / whole) * 100).toFixed(1)}%`;
}

function drillButton(text: string, verdicts: readonly Verdict[]): HTMLButtonElement {
  const button = html("button", { class: "link", type: "button" }, text);
  button.addEventListener("click", () => {
    drill(verdicts, []);
  });
  return button;
}

function promptButton(items: readonly Item[]): HTMLElement | null {
  const candidates = items.filter((item) => isPromptCandidate(item));
  if (candidates.length === 0) return null;
  const button = buildButton(
    async (): Promise<string> => buildBulkPrompt(await withRemoves(candidates)),
    `⧉ ${numberFormat.format(candidates.length)}`,
    `Copy Claude prompt for all ${numberFormat.format(candidates.length)}`,
  );
  return html("p", { class: "headline-text" }, button);
}

function headline(items: readonly Item[]): HTMLElement {
  const total = items.length;
  const free = items.filter((item) => FREE_VERDICTS.has(item.verdict)).length;
  const split = html(
    "p",
    { class: "headline-text" },
    drillButton(`${numberFormat.format(free)} free`, [...FREE_VERDICTS]),
    " ",
    html("span", { class: "muted" }, "(FOSS and partly-FOSS)"),
    " versus ",
    drillButton(`${numberFormat.format(total - free)} not free`, NOT_FREE_VERDICTS),
    " ",
    html("span", { class: "muted" }, "(non-free, incl. firmware blobs and unlicensed)"),
    `, out of ${numberFormat.format(total)} installed items.`,
  );
  const hero = html("p", { class: "hero" }, `${heroPercent(free, total)} free`);
  return html("section", { "aria-label": "Headline", class: "headline card" }, hero, split, promptButton(items));
}

function tile(verdict: Verdict, count: number, total: number): HTMLElement {
  const dot = html("span", { "aria-hidden": "true", class: "dot" });
  dot.style.background = VERDICT_COLORS[verdict];
  const button = html(
    "button",
    { class: "tile", "data-verdict": verdict, title: VERDICT_HINTS[verdict], type: "button" },
    html("span", { class: "tile-label" }, dot, VERDICT_LABELS[verdict]),
    html("span", { class: "tile-value", "data-testid": `count-${verdict}` }, numberFormat.format(count)),
    html("span", { class: "tile-pct" }, percent(count, total)),
  );
  button.addEventListener("click", () => {
    drill([verdict], []);
  });
  return html("li", {}, button);
}

function tiles(items: readonly Item[]): HTMLElement {
  const counts = countBy(items, (item) => item.verdict);
  return html(
    "ul",
    { "aria-label": "Items per verdict", class: "tiles" },
    ...VERDICTS.map((verdict) => tile(verdict, counts.get(verdict) ?? 0, items.length)),
  );
}

export class SummaryView extends StoreElement {
  #stopWidth: (() => void) | null = null;

  #render(items: readonly Item[]): void {
    this.teardown();
    const options = {
      onDrill: (source: Item["source"], verdict: null | Verdict): void => {
        drill(verdict === null ? [] : [verdict], [source]);
      },
      rows: sourceRows(items),
    };
    const chart = renderSourceChart(options, 0);
    const caption = html(
      "p",
      { class: "muted caption" },
      "Each bar is one source at 100%; the number is its item count. Click a segment or source to open those items in the table.",
    );
    const bySource = html(
      "section",
      { "aria-labelledby": "by-source", class: "card" },
      html("h2", { "aria-label": "Verdicts by source", id: "by-source" }, html("span", { "aria-hidden": "true", class: "icon" }, "⚙")),
      caption,
      chart,
    );
    this.replaceChildren(html("div", { class: "summary" }, headline(items), tiles(items), bySource));
    this.#stopWidth = observeWidth(chart, (width) => {
      drawSourceChart(chart, options, width);
    });
  }

  protected override teardown(): void {
    this.#stopWidth?.();
    this.#stopWidth = null;
    super.teardown();
  }

  protected override update(state: AppState, previous: AppState | null): void {
    if (!hasChanged(state, previous, (s) => s.url.view, (s) => s.scan.kind, selectItems)) return;
    if (state.url.view === "summary" && state.scan.kind === "ready") this.#render(selectItems(state));
    else this.teardown();
  }
}

define("summary-view", SummaryView);
