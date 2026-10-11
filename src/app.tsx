/**
 * The app shell: owns nothing but wiring.
 *
 * View, filters, sort and the open row live in the URL (hooks/use-url-state);
 * the scan lives in hooks/use-scan. Everything else is derived per render.
 */
import { useDeferredValue, useRef, useState } from "react";

import type { FilterState } from "./lib/filter.ts";
import type { Source, Verdict } from "./lib/schema.ts";
import type { View } from "./lib/url-state.ts";

import { AppHeader } from "./components/app-header.tsx";
import { DetailPanel } from "./components/detail-panel.tsx";
import { EasyWins } from "./components/easy-wins.tsx";
import { ErrorBanner } from "./components/error-banner.tsx";
import { FilterBar } from "./components/filter-bar.tsx";
import { HelpOverlay } from "./components/help-overlay.tsx";
import { ItemsTable } from "./components/items-table.tsx";
import { SummaryView } from "./components/summary-view.tsx";
import { ViewTabs } from "./components/view-tabs.tsx";
import { useKeyboard } from "./hooks/use-keyboard.ts";
import { useScan } from "./hooks/use-scan.ts";
import { updateState, useUrlState } from "./hooks/use-url-state.ts";
import { applyFilter, DEFAULT_FILTER } from "./lib/filter.ts";
import { isEasyWin } from "./lib/verdict.ts";

function setFilter(filter: FilterState): void {
  updateState((s) => ({ ...s, filter }));
}

function select(id: string): void {
  updateState((s) => ({ ...s, selected: id }));
}

function drill(verdicts: readonly Verdict[], sources: readonly Source[]): void {
  updateState(
    (s) => {
      return {
        ...s,
        filter: { ...DEFAULT_FILTER, sources, verdicts },
        selected: null,
        view: "table",
      };
    },
    { push: true },
  );
}

export function App(): React.JSX.Element {
  const { rescan, state } = useScan();
  const url = useUrlState();
  const [showHelp, setShowHelp] = useState(false);
  const [dismissed, setDismissed] = useState<null | string>(null);
  const searchReference = useRef<HTMLInputElement>(null);

  useKeyboard({
    onEscape: (): void => {
      if (showHelp) setShowHelp(false);
      else if (url.selected === null) searchReference.current?.blur();
      else updateState((s) => ({ ...s, selected: null }));
    },
    onFocusSearch: (): void => {
      searchReference.current?.focus();
    },
    onToggleHelp: (): void => {
      setShowHelp((open) => !open);
    },
  });

  // Search runs over ~3,100 rows per keystroke; deferring keeps typing smooth.
  const deferredFilter = useDeferredValue(url.filter);

  if (state.kind === "loading") {
    return <main className="app-msg">Scanning installed programs…</main>;
  }
  if (state.kind === "error") {
    return (
      <main className="app-msg">
        <p>Could not load the scan: {state.message}</p>
        <p className="muted">
          Is the backend running? Start everything with <code>./run.sh</code>.
        </p>
      </main>
    );
  }

  const { scan } = state;
  const results = applyFilter(scan.items, deferredFilter);
  const wins = scan.items.filter((item) => isEasyWin(item));
  const selectedItem = scan.items.find((item) => item.id === url.selected) ?? null;

  const errorKey = `${scan.generatedAt}|${state.refreshError ?? ""}`;
  const messages = [
    ...scan.errors.map((error) => `${error.source}: ${error.message}`),
    ...(state.refreshError === null ? [] : [`Rescan failed: ${state.refreshError}`]),
  ];

  return (
    <div className="app">
      <AppHeader
        onQuery={(query): void => {
          updateState((s) => {
            return {
              ...s,
              filter: { ...s.filter, query },
              view: "table",
            };
          });
        }}
        onRescan={rescan}
        query={url.filter.query}
        refreshing={state.refreshing}
        scan={scan}
        searchRef={searchReference}
      />
      <ErrorBanner
        messages={dismissed === errorKey ? [] : messages}
        onDismiss={(): void => {
          setDismissed(errorKey);
        }}
      />
      <ViewTabs
        counts={{ summary: scan.items.length, table: results.length, wins: wins.length }}
        onSelect={(view: View): void => {
          updateState((s) => ({ ...s, view }), { push: true });
        }}
        view={url.view}
      />
      <div className="body">
        <main className="content">
          {url.view === "summary" && <SummaryView items={scan.items} onDrill={drill} />}
          {url.view === "table" && (
            <>
              <FilterBar filter={url.filter} items={scan.items} onChange={setFilter} shown={results.length} />
              <ItemsTable
                items={results}
                onSelect={select}
                onSort={(sort): void => {
                  updateState((s) => ({ ...s, sort }));
                }}
                selected={url.selected}
                sort={url.sort}
              />
            </>
          )}
          {url.view === "wins" && <EasyWins items={wins} onSelect={select} selected={url.selected} />}
        </main>
        {selectedItem !== null && url.view !== "summary" && (
          <DetailPanel
            item={selectedItem}
            onClose={(): void => {
              updateState((s) => ({ ...s, selected: null }));
            }}
          />
        )}
      </div>
      {showHelp && (
        <HelpOverlay
          onClose={(): void => {
            setShowHelp(false);
          }}
        />
      )}
    </div>
  );
}
