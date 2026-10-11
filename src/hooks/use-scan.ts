/**
 * Loads `/api/scan` from the local backend, and rescans on demand.
 *
 * A rescan keeps the previous result on screen (with `refreshing` set) rather
 * than flashing back to a loading page: the old list is still accurate to
 * within seconds and the user may be mid-read.
 */
import { useCallback, useEffect, useState } from "react";

import type { Scan } from "../lib/schema.ts";

import { parseScan } from "../lib/schema.ts";

export type ScanState =
  | { readonly kind: "error"; readonly message: string }
  | { readonly kind: "loading" }
  | {
      readonly kind: "ready";
      readonly refreshError: null | string;
      readonly refreshing: boolean;
      readonly scan: Scan;
    };

export interface ScanHandle {
  readonly rescan: () => void;
  readonly state: ScanState;
}

async function fetchScan(isRefresh: boolean): Promise<Scan> {
  const response = await fetch(isRefresh ? "/api/scan?refresh=1" : "/api/scan");
  if (!response.ok) throw new Error(`HTTP ${response.status} from /api/scan`);
  return parseScan(await response.json());
}

function messageOf(error: unknown): string {
  return Error.isError(error) ? error.message : String(error);
}

function ready(scan: Scan): ScanState {
  return { kind: "ready", refreshError: null, refreshing: false, scan };
}

export function useScan(): ScanHandle {
  const [state, setState] = useState<ScanState>({ kind: "loading" });

  useEffect(() => {
    let isCancelled = false;

    async function load(): Promise<void> {
      try {
        const scan = await fetchScan(false);
        if (!isCancelled) setState(ready(scan));
      } catch (error) {
        if (!isCancelled) setState({ kind: "error", message: messageOf(error) });
      }
    }

    void load();
    return (): void => {
      isCancelled = true;
    };
  }, []);

  const rescan = useCallback(() => {
    async function refresh(): Promise<void> {
      setState((current) => {
        return current.kind === "ready"
          ? { ...current, refreshing: true }
          : { kind: "loading" };
      });
      try {
        setState(ready(await fetchScan(true)));
      } catch (error) {
        // A failed rescan keeps the last good scan and reports the failure
        // in the banner; only a first load with nothing to show is fatal.
        setState((current) => {
          return current.kind === "ready"
            ? { ...current, refreshError: messageOf(error), refreshing: false }
            : { kind: "error", message: messageOf(error) };
        });
      }
    }

    void refresh();
  }, []);

  return { rescan, state };
}
