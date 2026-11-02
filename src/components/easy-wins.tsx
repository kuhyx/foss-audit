/**
 * Easy wins: non-free or partly-free items whose drop-in/good FOSS
 * alternative is already installed (the rule lives in lib/verdict.ts).
 *
 * The list is ordered so the cleanest removals come first: known to have no
 * dependants, then untracked sources, then still-needed; then fit and name.
 */
import type { RemoveFetch } from "../hooks/use-remove.ts";
import type { Item } from "../lib/schema.ts";

import { useRemoveInfos } from "../hooks/use-remove.ts";
import { FITS } from "../lib/schema.ts";
import { FIT_LABELS, hasTrackedDependants, numberFormat } from "../lib/verdict.ts";
import { CopyButton } from "./copy-button.tsx";
import { VerdictBadge } from "./verdict-badge.tsx";

export interface EasyWinsProps {
  readonly items: readonly Item[];
  readonly onSelect: (id: string) => void;
  readonly selected: null | string;
}

function fitRank(item: Item): number {
  return item.alternative === null ? FITS.length : FITS.indexOf(item.alternative.fit);
}

/**
 * 0: known to have no dependants; 1: dependants not tracked for this source;
 * 2: something still needs it.
 */
function dependantRank(item: Item): number {
  if (item.requiredBy.length > 0) return 2;
  return hasTrackedDependants(item) ? 0 : 1;
}

export function orderWins(items: readonly Item[]): Item[] {
  return items.toSorted((a, b) => {
    return (
      dependantRank(a) - dependantRank(b) ||
      fitRank(a) - fitRank(b) ||
      a.name.localeCompare(b.name)
    );
  });
}

function RemoveCell({ fetched, id }: { readonly fetched: RemoveFetch; readonly id: string }): React.JSX.Element {
  if (fetched.kind === "loading") return <span className="muted">Loading the remove command…</span>;
  return fetched.kind === "error" ? <span className="muted">Remove command unavailable: {fetched.message}</span> : <CopyButton command={fetched.infos.get(id)?.removeCommand ?? null} />;
}

export function EasyWins({ items, onSelect, selected }: EasyWinsProps): React.JSX.Element {
  const fetched = useRemoveInfos(items.map((item) => item.id));
  if (items.length === 0) {
    return (
      <div className="table-empty">
        <p>No easy wins right now.</p>
        <p className="muted">
          An easy win is a non-free or partly-free item whose drop-in or good
          FOSS alternative is already installed.
        </p>
      </div>
    );
  }

  return (
    <div className="wins-scroll">
      <p className="muted caption">
        {numberFormat.format(items.length)} non-free or partly-free items with a
        drop-in or good FOSS alternative that is already installed. Nothing here
        is removed for you: copy the command and run it yourself.
      </p>
      <ul className="wins">
        {orderWins(items).map((item) => {
          const alt = item.alternative;
          return (
            <li
              aria-current={item.id === selected ? "true" : undefined}
              className="win card"
              data-id={item.id}
              key={item.id}
            >
              <div className="win-head">
                <button
                  className="link win-name"
                  onClick={(): void => {
                    onSelect(item.id);
                  }}
                  type="button"
                >
                  {item.name}
                </button>
                <span className="muted">{item.source}</span>
                <VerdictBadge verdict={item.verdict} />
                {alt !== null && <span className="muted">fit: {FIT_LABELS[alt.fit]}</span>}
              </div>
              <p className="win-alt">
                <span className="badge badge-success">Already installed</span>{" "}
                {alt?.installed.join(", ")}
              </p>
              {!hasTrackedDependants(item) && (
                <p className="muted caption">
                  Dependants are not tracked for {item.source} items; check
                  before removing.
                </p>
              )}
              {item.requiredBy.length > 0 && (
                <p className="warning-line">
                  by {item.requiredBy.join(", ")}: removing it is not a
                  one-command job.
                </p>
              )}
              <RemoveCell fetched={fetched} id={item.id} />
            </li>
          );
        })}
      </ul>
    </div>
  );
}
