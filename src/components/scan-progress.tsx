import { useEffect, useState } from "react";

import type { RunningSource, ScanProgress } from "../lib/schema.ts";

import { formatAge } from "../lib/age.ts";

function runningLabel({ done, source, total }: RunningSource): string {
  return total === null ? `${source} ${done}` : `${source} ${done}/${total}`;
}

function percent({ sourcesDone, sourcesTotal }: ScanProgress): number {
  return sourcesTotal > 0 ? Math.min(100, (sourcesDone / sourcesTotal) * 100) : 0;
}

function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => {
      setNow(Date.now());
    }, 1000);
    return (): void => {
      clearInterval(timer);
    };
  }, []);
  return now;
}

function Bar({ progress }: { readonly progress: ScanProgress }): React.JSX.Element {
  return (
    <div
      aria-label="Sources scanned"
      aria-valuemax={progress.sourcesTotal}
      aria-valuemin={0}
      aria-valuenow={progress.sourcesDone}
      className="scan-bar"
      role="progressbar"
    >
      <span style={{ width: `${percent(progress)}%` }} />
    </div>
  );
}

export function LoadingProgress({
  progress,
}: {
  readonly progress: null | ScanProgress;
}): null | React.JSX.Element {
  if (progress === null) return null;
  return (
    <div className="scan-live-loading">
      <Bar progress={progress} />
      <p className="scan-nums">
        <span>
          {progress.sourcesDone}/{progress.sourcesTotal}
        </span>
        <span>{progress.itemsFound} items</span>
      </p>
      <ul className="scan-running">
        {progress.running.map((source) => {
          return (
            <li key={source.source}>{runningLabel(source)}</li>
          );
        })}
      </ul>
    </div>
  );
}

export function HeaderProgress({
  generatedAt,
  progress,
}: {
  readonly generatedAt: string;
  readonly progress: null | ScanProgress;
}): React.JSX.Element {
  const age = formatAge(generatedAt, useNow());
  return (
    <p className="scan-live">
      {progress !== null && (
        <>
          <Bar progress={progress} />
          <span aria-label="Rescan progress" className="scan-live-text">
            {[`${progress.sourcesDone}/${progress.sourcesTotal}`, ...progress.running.map((source) => runningLabel(source))].join(" · ")}
          </span>
        </>
      )}
      {age !== "" && <span aria-label="Scan age">{age}</span>}
    </p>
  );
}
