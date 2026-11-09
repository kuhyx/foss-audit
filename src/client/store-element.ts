import type { AppState } from "./store.ts";

import { store } from "./store.ts";

// True on the first call (prev is null) or when any watched slice changed identity.
export function hasChanged(
  state: AppState,
  previous: AppState | null,
  ...slices: readonly ((state: AppState) => unknown)[]
): boolean {
  return previous === null || slices.some((slice) => slice(state) !== slice(previous));
}

// Subscribes while connected; `update` runs once on connect (prev is null), then on every store change.
export abstract class StoreElement extends HTMLElement {
  #stop: (() => void) | null = null;

  connectedCallback(): void {
    this.#stop = store.subscribe((state, previous) => {
      this.update(state, previous);
    });
    this.update(store.getState(), null);
  }

  disconnectedCallback(): void {
    this.#stop?.();
    this.#stop = null;
    this.teardown();
  }

  // Release anything besides the store subscription: timers, observers, pending fetches.
  protected teardown(): void {
    this.replaceChildren();
  }

  protected abstract update(state: AppState, previous: AppState | null): void;
}

export function define(name: string, constructor: CustomElementConstructor): void {
  if (customElements.get(name) === undefined) customElements.define(name, constructor);
}
