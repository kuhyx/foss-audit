/**
 * Per-source x verdict, as 100%-stacked horizontal bars in hand-rolled SVG.
 *
 * Every segment is a focusable button (Enter/Space or click) that jumps to the
 * table filtered to that source and verdict; the source label does the same
 * for the whole source. Hover or focus shows the exact count.
 */
import { useState } from "react";

import type { Source, Verdict } from "../lib/schema.ts";
import type { SourceRow } from "../lib/stack.ts";

import { useElementWidth } from "../hooks/use-element-width.ts";
import { VERDICTS } from "../lib/schema.ts";
import { layoutSegments, roundedEndPath, SEGMENT_GAP } from "../lib/stack.ts";
import { numberFormat, percent, VERDICT_COLORS, VERDICT_LABELS } from "../lib/verdict.ts";

export interface SourceChartProps {
  readonly onDrill: (source: Source, verdict: null | Verdict) => void;
  readonly rows: readonly SourceRow[];
}

interface Hover {
  readonly count: number;
  readonly left: number;
  readonly row: SourceRow;
  readonly top: number;
  readonly verdict: Verdict;
}

// Bar thickness: under the 24px cap, so the row's leftover is air.
const BAR = 18;
const ROW = 32;
const RADIUS = 4;
const LABEL_W = 112;
const TOTAL_W = 64;
const COLUMN_GAP = 8;
// Half the widest tooltip, for clamping it inside the chart.
const TOOLTIP_HALF = 110;

function isActivation(event: React.KeyboardEvent): boolean {
  return event.key === "Enter" || event.key === " ";
}

export function SourceChart({ onDrill, rows }: SourceChartProps): React.JSX.Element {
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const [hover, setHover] = useState<Hover | null>(null);
  const width = useElementWidth(container);
  const barWidth = Math.max(0, width - LABEL_W - TOTAL_W - 2 * COLUMN_GAP);

  return (
    <div className="chart" ref={setContainer}>
      <ul aria-label="Legend" className="legend">
        {VERDICTS.map((verdict) => {
          return (
            <li key={verdict}>
              <span
                aria-hidden="true"
                className="swatch"
                style={{ background: VERDICT_COLORS[verdict] }}
              />
              {VERDICT_LABELS[verdict]}
            </li>
          );
        })}
      </ul>
      <div
        className="chart-rows"
        style={{ gridTemplateColumns: `${LABEL_W}px ${barWidth}px ${TOTAL_W}px` }}
      >
        {rows.map((row, rowIndex) => {
          const segments = layoutSegments(row, barWidth);
          const lastIndex = segments.length - 1;
          return (
            <div className="chart-row" key={row.source} style={{ height: ROW }}>
              <button
                className="chart-label"
                onClick={(): void => {
                  onDrill(row.source, null);
                }}
                type="button"
              >
                {row.source}
              </button>
              <svg aria-label={`${row.source} by verdict`} height={ROW} role="group" width={barWidth}>
                {segments.map((segment, index) => {
                  const drawn = Math.max(1, segment.width - (index === lastIndex ? 0 : SEGMENT_GAP));
                  const y = (ROW - BAR) / 2;
                  const label = `${row.source}, ${VERDICT_LABELS[segment.verdict]}: ${numberFormat.format(segment.count)} of ${numberFormat.format(row.total)} (${percent(segment.count, row.total)})`;
                  const show = (): void => {
                    setHover({
                      count: segment.count,
                      // Clamped so a tooltip for a sliver at either end of the bar
                      // stays inside the card instead of overflowing it.
                      left: Math.min(
                        Math.max(LABEL_W + COLUMN_GAP + segment.x + drawn / 2, TOOLTIP_HALF),
                        width - TOOLTIP_HALF,
                      ),
                      row,
                      top: (rowIndex + 1) * ROW,
                      verdict: segment.verdict,
                    });
                  };
                  return (
                    <path
                      aria-label={label}
                      className="segment"
                      d={
                        index === lastIndex
                          ? roundedEndPath(segment.x, y, drawn, BAR, RADIUS)
                          : `M${segment.x},${y} h${drawn} v${BAR} h${-drawn} Z`
                      }
                      fill={VERDICT_COLORS[segment.verdict]}
                      key={segment.verdict}
                      onBlur={(): void => {
                        setHover(null);
                      }}
                      onClick={(): void => {
                        onDrill(row.source, segment.verdict);
                      }}
                      onFocus={show}
                      onKeyDown={(event): void => {
                        if (!isActivation(event)) return;
                        event.preventDefault();
                        onDrill(row.source, segment.verdict);
                      }}
                      onMouseEnter={show}
                      onMouseLeave={(): void => {
                        setHover(null);
                      }}
                      role="button"
                      tabIndex={0}
                    />
                  );
                })}
              </svg>
              <span className="chart-total">{numberFormat.format(row.total)}</span>
            </div>
          );
        })}
        {hover === null ? null : (
          <div
            className="tooltip"
            role="status"
            style={{ left: hover.left, top: hover.top }}
          >
            <span className="tooltip-title">
              <span
                aria-hidden="true"
                className="swatch"
                style={{ background: VERDICT_COLORS[hover.verdict] }}
              />
              <span>
                <strong>{hover.row.source}</strong> · {VERDICT_LABELS[hover.verdict]}
              </span>
            </span>
            <span className="tooltip-value">
              {numberFormat.format(hover.count)} of {numberFormat.format(hover.row.total)} ·{" "}
              {percent(hover.count, hover.row.total)}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
