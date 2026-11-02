// The remove fields of the ids a view shows, fetched again after a rescan. An answer is kept
// with the key it was fetched for, so a changed id list shows "loading", never a stale answer.
import { useEffect, useState, useSyncExternalStore } from "react";

import type { RemoveMap } from "./remove-api.ts";

import { fetchRemove, removeEpoch, subscribeRemove } from "./remove-api.ts";

export type RemoveFetch =
  | { readonly infos: RemoveMap; readonly kind: "ready" }
  | { readonly kind: "error"; readonly message: string }
  | { readonly kind: "loading" };

const SEPARATOR = "\0";
const LOADING: RemoveFetch = { kind: "loading" };

function messageOf(error: unknown): string {
  return Error.isError(error) ? error.message : String(error);
}

export function useRemoveInfos(ids: readonly string[]): RemoveFetch {
  const epoch = useSyncExternalStore(subscribeRemove, removeEpoch);
  const idKey = ids.join(SEPARATOR);
  const key = `${String(epoch)}${SEPARATOR}${idKey}`;
  const [done, setDone] = useState<null | { readonly key: string; readonly result: RemoveFetch }>(null);

  useEffect(() => {
    let isCancelled = false;

    async function load(): Promise<void> {
      let result: RemoveFetch;
      try {
        result = { infos: await fetchRemove(idKey === "" ? [] : idKey.split(SEPARATOR)), kind: "ready" };
      } catch (error) {
        result = { kind: "error", message: messageOf(error) };
      }
      if (!isCancelled) setDone({ key, result });
    }

    void load();
    return (): void => {
      isCancelled = true;
    };
  }, [idKey, key]);

  return done?.key === key ? done.result : LOADING;
}
