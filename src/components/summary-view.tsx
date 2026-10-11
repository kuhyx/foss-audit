/**
 * Summary: the free/not-free headline, one tile per verdict, and the
 * per-source chart. Every number is a link into the filtered table.
 */
import type { Item, Source, Verdict } from "../lib/schema.ts";

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
import { SourceChart } from "./source-chart.tsx";

export interface SummaryViewProps {
  readonly items: readonly Item[];
  readonly onDrill: (verdicts: readonly Verdict[], sources: readonly Source[]) => void;
}

/**
 * One decimal for the hero: at ~98% the integer rounding hides the very
 * difference (97.6 vs 98.4) a rescan after a cleanup is meant to show.
 */
function heroPercent(part: number, whole: number): string {
  return whole === 0 ? "0%" : `${((part / whole) * 100).toFixed(1)}%`;
}

export function SummaryView({ items, onDrill }: SummaryViewProps): React.JSX.Element {
  const total = items.length;
  const counts = countBy(items, (item) => item.verdict);
  const free = items.filter((item) => FREE_VERDICTS.has(item.verdict)).length;
  const notFree = total - free;
  const rows = sourceRows(items);

  return (
    <div className="summary">
      <section aria-label="Headline" className="headline card">
        <p className="hero">{heroPercent(free, total)} free</p>
        <p className="headline-text">
          <button
            className="link"
            onClick={(): void => {
              onDrill([...FREE_VERDICTS], []);
            }}
            type="button"
          >
            {numberFormat.format(free)} free
          </button>{" "}
          <span className="muted">(FOSS and partly-FOSS)</span> versus{" "}
          <button
            className="link"
            onClick={(): void => {
              onDrill(NOT_FREE_VERDICTS, []);
            }}
            type="button"
          >
            {numberFormat.format(notFree)} not free
          </button>{" "}
          <span className="muted">(non-free, incl. firmware blobs and unlicensed)</span>, out of{" "}
          {numberFormat.format(total)} installed items.
        </p>
      </section>

      <ul aria-label="Items per verdict" className="tiles">
        {VERDICTS.map((verdict) => {
          const count = counts.get(verdict) ?? 0;
          return (
            <li key={verdict}>
              <button
                className="tile"
                data-verdict={verdict}
                onClick={(): void => {
                  onDrill([verdict], []);
                }}
                title={VERDICT_HINTS[verdict]}
                type="button"
              >
                <span className="tile-label">
                  <span
                    aria-hidden="true"
                    className="dot"
                    style={{ background: VERDICT_COLORS[verdict] }}
                  />
                  {VERDICT_LABELS[verdict]}
                </span>
                <span className="tile-value" data-testid={`count-${verdict}`}>
                  {numberFormat.format(count)}
                </span>
                <span className="tile-pct">{percent(count, total)}</span>
              </button>
            </li>
          );
        })}
      </ul>

      <section aria-labelledby="by-source" className="card">
        <h2 id="by-source">Verdicts by source</h2>
        <p className="muted caption">
          Each bar is one source at 100%; the number is its item count. Click a
          segment or source to open those items in the table.
        </p>
        <SourceChart
          onDrill={(source, verdict): void => {
            onDrill(verdict === null ? [] : [verdict], [source]);
          }}
          rows={rows}
        />
      </section>
    </div>
  );
}
