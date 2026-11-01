import type { Scan, ScanProgress } from "../lib/schema.ts";

import { parseProgress, parseScan } from "../lib/schema.ts";

export interface Fetched {
  readonly scan: null | Scan;
  readonly scanning: boolean;
}

export async function fetchScan(isRefresh: boolean): Promise<Fetched> {
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
