/**
 * Top bar: what was scanned and when, global search, and Rescan.
 */
import type { Ref } from "react";

import type { Scan, ScanProgress } from "../lib/schema.ts";

import { numberFormat } from "../lib/verdict.ts";
import { HeaderProgress } from "./scan-progress.tsx";

export interface AppHeaderProps {
  readonly onQuery: (query: string) => void;
  readonly onRescan: () => void;
  readonly progress: null | ScanProgress;
  readonly query: string;
  readonly refreshing: boolean;
  readonly scan: Scan;
  readonly searchRef: Ref<HTMLInputElement>;
}

function formatGeneratedAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("en-GB", {
    dateStyle: "medium",
    timeStyle: "medium",
  });
}

export function AppHeader({
  onQuery,
  onRescan,
  progress,
  query,
  refreshing,
  scan,
  searchRef,
}: AppHeaderProps): React.JSX.Element {
  return (
    <header className="topbar">
      <h1>FOSS audit</h1>
      <p className="scan-meta">
        <span>
          <span className="muted">host</span> {scan.host}
        </span>
        <span>
          <span className="muted">scanned</span>{" "}
          <time dateTime={scan.generatedAt}>{formatGeneratedAt(scan.generatedAt)}</time>
        </span>
        <span>
          <span className="muted">took</span> {numberFormat.format(scan.durationMs)} ms
        </span>
      </p>
      {refreshing && <HeaderProgress generatedAt={scan.generatedAt} progress={progress} />}
      <input
        aria-label="Search name or id (typos ok)"
        className="search"
        onChange={(event): void => {
          onQuery(event.target.value);
        }}
        placeholder="Search name or id, typos ok  (/)"
        ref={searchRef}
        type="search"
        value={query}
      />
      <button
        aria-busy={refreshing}
        className="btn btn-primary"
        disabled={refreshing}
        onClick={onRescan}
        type="button"
      >
        {refreshing ? "Rescanning…" : "Rescan"}
      </button>
    </header>
  );
}
