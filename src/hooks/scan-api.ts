import type { Scan, ScanProgress } from "../lib/schema.ts";

import { parseProgress, parseScan } from "../lib/schema.ts";

export interface Fetched {
  readonly scan: null | Scan;
  readonly scanning: boolean;
}

interface Early {
  readonly body: unknown;
  readonly status: number;
}

/**
 * index.html starts `GET /api/scan` before the bundle loads, so the download
 * and JSON parse overlap it. Only the first, non-refresh load may use it.
 */
async function takeEarly(): Promise<Early | null> {
  const early = Reflect.get(globalThis, "__scanPreload") as Promise<Early | null> | undefined;
  Reflect.deleteProperty(globalThis, "__scanPreload");
  const settled = (await early) ?? null;
  return settled !== null && (settled.status === 200 || settled.status === 202) ? settled : null;
}

function fromEarly(early: Early): Fetched {
  if (early.status === 202) return { scan: null, scanning: true };
  const scan = parseScan(early.body);
  return { scan, scanning: scan.scanning };
}

export async function fetchScan(isRefresh: boolean): Promise<Fetched> {
  const early = isRefresh ? null : await takeEarly();
  if (early !== null) return fromEarly(early);
  const response = await fetch(isRefresh ? "/api/scan?refresh=1" : "/api/scan");
  if (response.status === 202) return { scan: null, scanning: true };
  if (!response.ok) throw new Error(`HTTP ${response.status} from /api/scan`);
  const scan = parseScan(await response.json());
  return { scan, scanning: scan.scanning };
}

export async function fetchProgress(): Promise<ScanProgress> {
  const response = await fetch("/api/scan/progress");
  if (!response.ok) throw new Error(`HTTP ${response.status} from /api/scan/progress`);
  return parseProgress(await response.json());
}
