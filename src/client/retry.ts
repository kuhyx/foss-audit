import { store } from "./store.ts";

export const RETRY_DELAYS_MS: readonly number[] = [1000, 2000, 4000, 5000];

// While the first load has failed (scan.kind "error"), reload with backoff until it is ready. Returns stop().
export function startRetry(load: () => Promise<void>, delays: readonly number[] = RETRY_DELAYS_MS): () => void {
  let attempt = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const unsubscribe = store.subscribe((state, previous) => {
    if (state.scan === previous.scan) return;
    clearTimeout(timer);
    timer = undefined;
    if (state.scan.kind === "ready") attempt = 0;
    if (state.scan.kind !== "error") return;
    const delay = delays[Math.min(attempt, delays.length - 1)] ?? 0;
    attempt += 1;
    timer = setTimeout(() => void load(), delay);
  });
  return (): void => {
    unsubscribe();
    clearTimeout(timer);
  };
}
