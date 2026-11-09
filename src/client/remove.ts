import type { RemoveMap } from "./remove-api.ts";

import { fetchRemove, subscribeRemove } from "./remove-api.ts";

export type RemoveFetch =
  | { readonly infos: RemoveMap; readonly kind: "ready" }
  | { readonly kind: "error"; readonly message: string }
  | { readonly kind: "loading" };

const LOADING: RemoveFetch = { kind: "loading" };

function messageOf(error: unknown): string {
  return Error.isError(error) ? error.message : String(error);
}

// "loading" first, then the answer, again after every rescan; never a stale answer. Returns stop().
export function watchRemove(ids: readonly string[], onChange: (result: RemoveFetch) => void): () => void {
  let isStopped = false;
  let round = 0;

  async function load(): Promise<void> {
    round += 1;
    const mine = round;
    onChange(LOADING);
    let result: RemoveFetch;
    try {
      result = { infos: await fetchRemove(ids), kind: "ready" };
    } catch (error) {
      result = { kind: "error", message: messageOf(error) };
    }
    if (!isStopped && mine === round) onChange(result);
  }

  const unsubscribe = subscribeRemove(() => void load());
  void load();
  return (): void => {
    isStopped = true;
    unsubscribe();
  };
}
