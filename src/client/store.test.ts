import { createStore, initialState, resetStore, store } from "./store.ts";

describe("createStore", () => {
  it("notifies with the new and previous state and unsubscribes", () => {
    const s = createStore();
    const seen: [boolean, boolean][] = [];
    const stop = s.subscribe((state, previous) => {
      seen.push([state.helpOpen, previous.helpOpen]);
    });
    s.set({ helpOpen: true });
    stop();
    s.set({ helpOpen: false });
    expect(seen).toEqual([[true, false]]);
  });

  it("drops a patch that changes nothing", () => {
    const s = createStore();
    const listener = vi.fn();
    s.subscribe(listener);
    s.set({ helpOpen: false });
    s.set({});
    expect(listener).not.toHaveBeenCalled();
  });

  it("keeps the identity of untouched slices", () => {
    const s = createStore();
    const { url } = s.getState();
    s.set({ helpOpen: true });
    expect(s.getState().url).toBe(url);
  });

  it("delivers a nested update after the current round, in order", () => {
    const s = createStore();
    const order: string[] = [];
    s.subscribe((state) => {
      order.push(`a:${state.helpOpen}`);
      if (state.helpOpen) s.set({ helpOpen: false });
    });
    s.subscribe((state) => {
      order.push(`b:${state.helpOpen}`);
    });
    s.set({ helpOpen: true });
    expect(order).toEqual(["a:true", "b:true", "a:false", "b:false"]);
  });

  it("recovers after a throwing listener", () => {
    const s = createStore();
    const stop = s.subscribe(() => {
      throw new Error("bad listener");
    });
    expect(() => {
      s.set({ helpOpen: true });
    }).toThrow("bad listener");
    stop();
    const listener = vi.fn();
    s.subscribe(listener);
    s.set({ helpOpen: false });
    expect(listener).toHaveBeenCalledOnce();
  });
});

describe("resetStore", () => {
  it("restores the initial state", () => {
    store.set({ helpOpen: true });
    resetStore();
    expect(store.getState()).toEqual(initialState());
  });
});
