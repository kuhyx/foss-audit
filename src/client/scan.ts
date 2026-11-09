/**
 * Loads `/api/scan`, watches `/api/scan/progress` while the backend scans and
 * rescans on demand. A rescan keeps the previous result on screen
 * (`refreshing`) rather than flashing back to a loading page.
 */
import type { Scan } from "../lib/schema.ts";
import type { Fetched } from "./scan-api.ts";
import type { ScanState } from "./store.ts";

import { invalidateRemoveCache } from "./remove-api.ts";
import { fetchProgress, fetchScan } from "./scan-api.ts";
import { store } from "./store.ts";

const POLL_MS = 250;

const session: { shown: null | string; stopPolling: (() => void) | null } = { shown: null, stopPolling: null };

function messageOf(error: unknown): string {
  return Error.isError(error) ? error.message : String(error);
}

function ready(scan: Scan): ScanState {
  return { kind: "ready", refreshError: null, refreshing: scan.scanning, scan };
}

// A failure keeps the last good scan and goes to the banner; with none it is fatal.
function fail(message: string): void {
  const current = store.getState().scan;
  store.set({
    scan:
      current.kind === "ready" ? { ...current, refreshError: message, refreshing: false } : { kind: "error", message },
  });
}

function show(fetched: Fetched): void {
  if (fetched.scan !== null) {
    if (fetched.scan.generatedAt !== session.shown) invalidateRemoveCache();
    session.shown = fetched.scan.generatedAt;
    store.set({ scan: ready(fetched.scan) });
  }
  if (fetched.scanning) watch();
  else halt();
}

function halt(): void {
  session.stopPolling?.();
  session.stopPolling = null;
}

function watch(): void {
  if (session.stopPolling !== null) return;
  let hasStopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  session.stopPolling = (): void => {
    hasStopped = true;
    clearTimeout(timer);
  };
  // A function, so TypeScript does not narrow the flag across the awaits.
  const isCancelled = (): boolean => hasStopped;

  async function poll(): Promise<void> {
    try {
      const latest = await fetchProgress();
      if (isCancelled()) return;
      store.set({ progress: latest });
      if (latest.error !== null) {
        fail(latest.error);
        halt();
        return;
      }
      if (latest.generatedAt !== null && latest.generatedAt !== session.shown) {
        const fetched = await fetchScan(false);
        if (isCancelled()) return;
        show(fetched);
        if (!fetched.scanning) return;
      } else if (!latest.scanning) {
        halt();
        return;
      }
    } catch (error) {
      if (isCancelled()) return;
      fail(messageOf(error));
      halt();
      return;
    }
    // Armed only after the reply lands, so polls never overlap.
    timer = setTimeout(() => void poll(), POLL_MS);
  }

  void poll();
}

export async function load(): Promise<void> {
  try {
    show(await fetchScan(false));
  } catch (error) {
    fail(messageOf(error));
  }
}

async function rerun(): Promise<void> {
  store.set({ progress: null });
  const current = store.getState().scan;
  store.set({ scan: current.kind === "ready" ? { ...current, refreshing: true } : { kind: "loading" } });
  try {
    show(await fetchScan(true));
  } catch (error) {
    fail(messageOf(error));
  }
}

export function refresh(): void {
  void rerun();
}

/**
For tests: stop polling and forget the shown scan.
*/
export function resetScan(): void {
  halt();
  session.shown = null;
}
