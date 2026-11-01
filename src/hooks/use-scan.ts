/**
 * Loads `/api/scan`, watches `/api/scan/progress` while the backend scans,
 * and rescans on demand.
 *
 * A rescan keeps the previous result on screen (with `refreshing` set) rather
 * than flashing back to a loading page.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import type { Scan, ScanProgress } from "../lib/schema.ts";
import type { Fetched } from "./scan-api.ts";

import { fetchProgress, fetchScan } from "./scan-api.ts";

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
  readonly progress: null | ScanProgress;
  readonly rescan: () => void;
  readonly state: ScanState;
}

const POLL_MS = 250;

function messageOf(error: unknown): string {
  return Error.isError(error) ? error.message : String(error);
}

function ready(scan: Scan): ScanState {
  return { kind: "ready", refreshError: null, refreshing: scan.scanning, scan };
}

/**
 * A failure keeps the last good scan and goes to the banner; with none it is fatal.
 */
function failed(message: string): (current: ScanState) => ScanState {
  return (current) => {
    return current.kind === "ready"
      ? { ...current, refreshError: message, refreshing: false }
      : { kind: "error", message };
  };
}

export function useScan(): ScanHandle {
  const [state, setState] = useState<ScanState>({ kind: "loading" });
  const [progress, setProgress] = useState<null | ScanProgress>(null);
  const [watching, setWatching] = useState(false);
  const shown = useRef<null | string>(null);

  const show = useCallback((fetched: Fetched) => {
    if (fetched.scan !== null) {
      shown.current = fetched.scan.generatedAt;
      setState(ready(fetched.scan));
    }
    setWatching(fetched.scanning);
  }, []);

  useEffect(() => {
    let isCancelled = false;

    async function load(): Promise<void> {
      try {
        const fetched = await fetchScan(false);
        if (!isCancelled) show(fetched);
      } catch (error) {
        if (!isCancelled) setState(failed(messageOf(error)));
      }
    }

    void load();
    return (): void => {
      isCancelled = true;
    };
  }, [show]);

  useEffect(() => {
    if (!watching) return;
    let hasStopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    // A function, so TypeScript does not narrow the flag across the awaits.
    const isCancelled = (): boolean => hasStopped;

    async function poll(): Promise<void> {
      try {
        const latest = await fetchProgress();
        if (isCancelled()) return;
        setProgress(latest);
        if (latest.error !== null) {
          setState(failed(latest.error));
          setWatching(false);
          return;
        }
        if (latest.generatedAt !== null && latest.generatedAt !== shown.current) {
          const fetched = await fetchScan(false);
          if (isCancelled()) return;
          show(fetched);
          if (!fetched.scanning) return;
        } else if (!latest.scanning) {
          setWatching(false);
          return;
        }
      } catch (error) {
        if (isCancelled()) return;
        setState(failed(messageOf(error)));
        setWatching(false);
        return;
      }
      // Armed only after the reply lands, so polls never overlap.
      timer = setTimeout(() => void poll(), POLL_MS);
    }

    void poll();
    return (): void => {
      hasStopped = true;
      clearTimeout(timer);
    };
  }, [watching, show]);

  const rescan = useCallback(() => {
    async function refresh(): Promise<void> {
      setProgress(null);
      setState((current) => current.kind === "ready" ? { ...current, refreshing: true } : { kind: "loading" });
      try {
        show(await fetchScan(true));
      } catch (error) {
        setState(failed(messageOf(error)));
      }
    }

    void refresh();
  }, [show]);

  return { progress, rescan, state };
}
