/**
 * The table's filters: verdict and source multi-selects as toggle chips, and
 * the four boolean facets as any/yes/no segmented controls.
 *
 * Chip counts are computed over the whole scan, not the current result, so a
 * chip never shows 0 merely because another chip in the same group is on.
 */
import type { FilterState, Kind, Tri } from "../lib/filter.ts";
import type { Item } from "../lib/schema.ts";

import { DEFAULT_FILTER, isFilterActive, toggleMember } from "../lib/filter.ts";
import { SOURCES, VERDICTS } from "../lib/schema.ts";
import { countBy, numberFormat, VERDICT_COLORS, VERDICT_LABELS } from "../lib/verdict.ts";

export interface FilterBarProps {
  readonly filter: FilterState;
  readonly items: readonly Item[];
  readonly onChange: (next: FilterState) => void;
  readonly shown: number;
}

interface SegmentedProps<T extends string> {
  readonly label: string;
  readonly onChange: (value: T) => void;
  readonly options: readonly (readonly [T, string])[];
  readonly value: T;
}

function Segmented<T extends string>({
  label,
  onChange,
  options,
  value,
}: SegmentedProps<T>): React.JSX.Element {
  return (
    <div aria-label={label} className="segmented" role="group">
      <span className="facet-label">{label}</span>
      {options.map(([option, text]) => {
        return (
          <button
            aria-pressed={option === value}
            className="seg"
            key={option}
            onClick={(): void => {
              onChange(option);
            }}
            type="button"
          >
            {text}
          </button>
        );
      })}
    </div>
  );
}

const TRI_OPTIONS: readonly (readonly [Tri, string])[] = [
  ["any", "Any"],
  ["yes", "Yes"],
  ["no", "No"],
];

const KIND_OPTIONS: readonly (readonly [Kind, string])[] = [
  ["any", "Any"],
  ["explicit", "Explicit"],
  ["dependency", "Dependency"],
];

export function FilterBar({ filter, items, onChange, shown }: FilterBarProps): React.JSX.Element {
  const verdictCounts = countBy(items, (item) => item.verdict);
  const sourceCounts = countBy(items, (item) => item.source);
  // Only sources this scan found, in vocabulary order, with their counts.
  const presentSources = [...sourceCounts].toSorted(
    ([a], [b]) => SOURCES.indexOf(a) - SOURCES.indexOf(b),
  );

  return (
    <div className="filters">
      <div aria-label="Verdict" className="chips" role="group">
        <span className="facet-label">Verdict</span>
        {VERDICTS.map((verdict) => {
          return (
            <button
              aria-pressed={filter.verdicts.includes(verdict)}
              className="chip"
              key={verdict}
              onClick={(): void => {
                onChange({ ...filter, verdicts: toggleMember(filter.verdicts, verdict, VERDICTS) });
              }}
              type="button"
            >
              <span aria-hidden="true" className="dot" style={{ background: VERDICT_COLORS[verdict] }} />
              {VERDICT_LABELS[verdict]}
              <span className="chip-count">{numberFormat.format(verdictCounts.get(verdict) ?? 0)}</span>
            </button>
          );
        })}
      </div>
      <div aria-label="Source" className="chips" role="group">
        <span className="facet-label">Source</span>
        {presentSources.map(([source, count]) => {
          return (
            <button
              aria-pressed={filter.sources.includes(source)}
              className="chip"
              key={source}
              onClick={(): void => {
                onChange({ ...filter, sources: toggleMember(filter.sources, source, SOURCES) });
              }}
              type="button"
            >
              {source}
              <span className="chip-count">{numberFormat.format(count)}</span>
            </button>
          );
        })}
      </div>
      <div className="facet-row">
        <Segmented
          label="Installed as"
          onChange={(kind): void => {
            onChange({ ...filter, kind });
          }}
          options={KIND_OPTIONS}
          value={filter.kind}
        />
        <Segmented
          label="Orphan"
          onChange={(orphan): void => {
            onChange({ ...filter, orphan });
          }}
          options={TRI_OPTIONS}
          value={filter.orphan}
        />
        <Segmented
          label="Own code"
          onChange={(own): void => {
            onChange({ ...filter, own });
          }}
          options={TRI_OPTIONS}
          value={filter.own}
        />
        <Segmented
          label="Untracked file"
          onChange={(loose): void => {
            onChange({ ...filter, loose });
          }}
          options={TRI_OPTIONS}
          value={filter.loose}
        />
        <Segmented
          label="Has alternative"
          onChange={(hasAlt): void => {
            onChange({ ...filter, hasAlt });
          }}
          options={TRI_OPTIONS}
          value={filter.hasAlt}
        />
        <Segmented
          label="Alternative installed"
          onChange={(altInstalled): void => {
            onChange({ ...filter, altInstalled });
          }}
          options={TRI_OPTIONS}
          value={filter.altInstalled}
        />
        <p aria-live="polite" className="result-count">
          <strong>{numberFormat.format(shown)}</strong>{" "}
          <span className="muted">of {numberFormat.format(items.length)} items</span>
        </p>
        <button
          className="btn"
          disabled={!isFilterActive(filter)}
          onClick={(): void => {
            onChange(DEFAULT_FILTER);
          }}
          type="button"
        >
          Reset filters
        </button>
      </div>
    </div>
  );
}
