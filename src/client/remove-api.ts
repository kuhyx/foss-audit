// POST /api/remove: removeCommand and removeVia per item id (/api/scan leaves them out).
// Cached per id until invalidateRemoveCache: a new scan was swapped in, ids may mean other commands.
import type { Item, RemovableItem, RemoveInfo } from "../lib/schema.ts";

import { parseRemove } from "../lib/schema.ts";

export type RemoveMap = ReadonlyMap<string, RemoveInfo>;

const NONE: RemoveInfo = { removeCommand: null, removeVia: "" };

const cache = new Map<string, RemoveInfo>();
const listeners = new Set<() => void>();
const generation = { epoch: 0 };

export function invalidateRemoveCache(): void {
  cache.clear();
  generation.epoch += 1;
  for (const listener of listeners) listener();
}

export function subscribeRemove(listener: () => void): () => void {
  listeners.add(listener);
  return (): void => {
    listeners.delete(listener);
  };
}

export function removeEpoch(): number {
  return generation.epoch;
}

async function request(ids: readonly string[]): Promise<RemoveMap> {
  if (ids.length === 0) return new Map();
  const response = await fetch("/api/remove", {
    body: JSON.stringify({ ids }),
    headers: { "Content-Type": "application/json" },
    method: "POST",
  });
  if (!response.ok) throw new Error(`HTTP ${response.status} from /api/remove`);
  const reply = parseRemove(await response.json());
  return new Map(Object.entries(reply));
}

// Unknown ids are left out. An answer in flight across an invalidation is returned, not cached.
export async function fetchRemove(ids: readonly string[]): Promise<RemoveMap> {
  const wanted = [...new Set(ids)];
  const missing = wanted.filter((id) => !cache.has(id));
  const startedAt = generation.epoch;
  const fresh = await request(missing);
  if (startedAt === generation.epoch) {
    for (const [id, info] of fresh) cache.set(id, info);
  }
  const found = new Map<string, RemoveInfo>();
  for (const id of wanted) {
    const info = cache.get(id) ?? fresh.get(id);
    if (info !== undefined) found.set(id, info);
  }
  return found;
}

export async function withRemoves(items: readonly Item[]): Promise<RemovableItem[]> {
  const infos = await fetchRemove(items.map((item) => item.id));
  return items.map((item) => ({ ...item, ...(infos.get(item.id) ?? NONE) }));
}

export async function withRemove(item: Item): Promise<RemovableItem> {
  const infos = await fetchRemove([item.id]);
  return { ...item, ...(infos.get(item.id) ?? NONE) };
}
