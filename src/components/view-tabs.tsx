/**
 * The three views as a nav row. Plain buttons rather than an ARIA tablist:
 * each switch is a URL change (Back returns to the previous view), which is
 * navigation, not a tab-panel swap.
 */
import type { View } from "../lib/url-state.ts";

import { numberFormat } from "../lib/verdict.ts";
import { VIEW_LABELS } from "../lib/views.ts";

export interface ViewTabsProps {
  readonly counts: Readonly<Record<View, number>>;
  readonly onSelect: (view: View) => void;
  readonly view: View;
}

const ORDER: readonly View[] = ["summary", "table", "wins"];

export function ViewTabs({ counts, onSelect, view }: ViewTabsProps): React.JSX.Element {
  return (
    <nav aria-label="Views" className="tabs">
      {ORDER.map((v) => {
        return (
          <button
            aria-current={v === view ? "page" : undefined}
            className="tab"
            key={v}
            onClick={(): void => {
              onSelect(v);
            }}
            type="button"
          >
            {VIEW_LABELS[v]}
            <span className="tab-count">{numberFormat.format(counts[v])}</span>
          </button>
        );
      })}
    </nav>
  );
}
