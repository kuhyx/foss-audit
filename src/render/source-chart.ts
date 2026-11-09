/**
 * Per-source x verdict as 100%-stacked SVG bars, drawn in device pixels so
 * the 2px gaps and 4px ends stay exact. Segments and labels drill on click
 * or Enter/Space; hover or focus shows the exact count.
 */
import type { Source, Verdict } from "../lib/schema.ts";
import type { Segment, SourceRow } from "../lib/stack.ts";

import { VERDICTS } from "../lib/schema.ts";
import { layoutSegments, roundedEndPath, SEGMENT_GAP } from "../lib/stack.ts";
import { numberFormat, percent, VERDICT_COLORS, VERDICT_LABELS } from "../lib/verdict.ts";
import { html } from "./dom.ts";

export interface SourceChartOptions {
  readonly onDrill: (source: Source, verdict: null | Verdict) => void;
  readonly rows: readonly SourceRow[];
}

const BAR = 18;
const ROW = 32;
const RADIUS = 4;
const LABEL_W = 112;
const TOTAL_W = 64;
const COLUMN_GAP = 8;
const TOOLTIP_HALF = 110;
const SVG_NS = "http://www.w3.org/2000/svg";

interface Frame {
  readonly barWidth: number;
  readonly grid: HTMLElement;
  readonly onDrill: SourceChartOptions["onDrill"];
  readonly width: number;
}

interface Placed {
  readonly drawn: number;
  readonly isLast: boolean;
  readonly row: SourceRow;
  readonly rowIndex: number;
  readonly segment: Segment;
}

function svg<K extends keyof SVGElementTagNameMap>(
  tag: K,
  attributes: Readonly<Record<string, number | string>>,
): SVGElementTagNameMap[K] {
  const element = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, String(value));
  return element;
}

function swatch(verdict: Verdict): HTMLElement {
  const element = html("span", { "aria-hidden": "true", class: "swatch" });
  element.style.background = VERDICT_COLORS[verdict];
  return element;
}

function legend(): HTMLElement {
  return html(
    "ul",
    { "aria-label": "Legend", class: "legend" },
    ...VERDICTS.map((verdict) => html("li", {}, swatch(verdict), VERDICT_LABELS[verdict])),
  );
}

function tooltip(row: SourceRow, segment: Segment, left: number, top: number): HTMLElement {
  const title = html(
    "span",
    { class: "tooltip-title" },
    swatch(segment.verdict),
    html("span", {}, html("strong", {}, row.source), ` · ${VERDICT_LABELS[segment.verdict]}`),
  );
  const value = html(
    "span",
    { class: "tooltip-value" },
    `${numberFormat.format(segment.count)} of ${numberFormat.format(row.total)} · ${percent(segment.count, row.total)}`,
  );
  const element = html("div", { class: "tooltip", role: "status" }, title, value);
  element.style.left = `${left}px`;
  element.style.top = `${top}px`;
  return element;
}

function segmentPath(placed: Placed, frame: Frame): SVGPathElement {
  const { drawn, isLast, row, rowIndex, segment } = placed;
  const y = (ROW - BAR) / 2;
  const count = `${numberFormat.format(segment.count)} of ${numberFormat.format(row.total)}`;
  const path = svg("path", {
    "aria-label": `${row.source}, ${VERDICT_LABELS[segment.verdict]}: ${count} (${percent(segment.count, row.total)})`,
    class: "segment",
    d: isLast ? roundedEndPath(segment.x, y, drawn, BAR, RADIUS) : `M${segment.x},${y} h${drawn} v${BAR} h${-drawn} Z`,
    fill: VERDICT_COLORS[segment.verdict],
    role: "button",
    tabindex: 0,
  });
  const hide = (): void => {
    frame.grid.querySelector(".tooltip")?.remove();
  };
  const show = (): void => {
    hide();
    // Clamped so a sliver's tooltip at either end stays inside the card.
    const centre = LABEL_W + COLUMN_GAP + segment.x + drawn / 2;
    const left = Math.min(Math.max(centre, TOOLTIP_HALF), frame.width - TOOLTIP_HALF);
    frame.grid.append(tooltip(row, segment, left, (rowIndex + 1) * ROW));
  };
  const drill = (): void => {
    frame.onDrill(row.source, segment.verdict);
  };
  path.addEventListener("mouseenter", show);
  path.addEventListener("focus", show);
  path.addEventListener("mouseleave", hide);
  path.addEventListener("blur", hide);
  path.addEventListener("click", drill);
  path.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    drill();
  });
  return path;
}

function chartRow(row: SourceRow, rowIndex: number, frame: Frame): HTMLElement {
  const segments = layoutSegments(row, frame.barWidth);
  const lastIndex = segments.length - 1;
  const bars = svg("svg", { "aria-label": `${row.source} by verdict`, height: ROW, role: "group", width: frame.barWidth });
  for (const [index, segment] of segments.entries()) {
    const isLast = index === lastIndex;
    const drawn = Math.max(1, segment.width - (isLast ? 0 : SEGMENT_GAP));
    bars.append(segmentPath({ drawn, isLast, row, rowIndex, segment }, frame));
  }
  const label = html("button", { class: "chart-label", type: "button" }, row.source);
  label.addEventListener("click", () => {
    frame.onDrill(row.source, null);
  });
  const total = html("span", { class: "chart-total" }, numberFormat.format(row.total));
  const element = html("div", { class: "chart-row" }, label, bars, total);
  element.style.height = `${ROW}px`;
  return element;
}

// Fills `chart` (legend + bars) for its content `width`; call again on every width change.
export function drawSourceChart(chart: HTMLElement, options: SourceChartOptions, width: number): void {
  const barWidth = Math.max(0, width - LABEL_W - TOTAL_W - 2 * COLUMN_GAP);
  const grid = html("div", { class: "chart-rows" });
  grid.style.gridTemplateColumns = `${LABEL_W}px ${barWidth}px ${TOTAL_W}px`;
  const frame: Frame = { barWidth, grid, onDrill: options.onDrill, width };
  grid.append(...options.rows.map((row, index) => chartRow(row, index, frame)));
  chart.replaceChildren(legend(), grid);
}

export function renderSourceChart(options: SourceChartOptions, width: number): HTMLElement {
  const chart = html("div", { class: "chart" });
  drawSourceChart(chart, options, width);
  return chart;
}
