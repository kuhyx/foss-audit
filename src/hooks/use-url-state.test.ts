import { act, renderHook } from "@testing-library/react";

import { updateState, useUrlState } from "./use-url-state.ts";

beforeEach(() => {
  globalThis.history.replaceState(null, "", "/");
});

describe("useUrlState / updateState", () => {
  it("reads the current query and re-renders on updates", () => {
    globalThis.history.replaceState(null, "", "/?view=wins");
    const { result } = renderHook(() => useUrlState());
    expect(result.current.view).toBe("wins");

    act(() => {
      updateState((s) => ({ ...s, view: "table" }));
    });
    expect(result.current.view).toBe("table");
    expect(globalThis.location.search).toBe("?view=table");
  });

  it("composes two updates from one handler", () => {
    const { result } = renderHook(() => useUrlState());
    act(() => {
      updateState((s) => ({ ...s, filter: { ...s.filter, query: "chrome" } }));
      updateState((s) => ({ ...s, sort: { desc: false, id: "name" } }));
    });
    expect(result.current.filter.query).toBe("chrome");
    expect(result.current.sort).toEqual({ desc: false, id: "name" });
  });

  it("pushes a history entry only when asked", () => {
    const before = globalThis.history.length;
    act(() => {
      updateState((s) => ({ ...s, view: "table" }));
    });
    expect(globalThis.history.length).toBe(before);
    act(() => {
      updateState((s) => ({ ...s, view: "wins" }), { push: true });
    });
    expect(globalThis.history.length).toBe(before + 1);
  });

  it("writes a clean path for the default state", () => {
    globalThis.history.replaceState(null, "", "/?view=table");
    act(() => {
      updateState((s) => ({ ...s, view: "summary" }));
    });
    expect(globalThis.location.search).toBe("");
    expect(globalThis.location.pathname).toBe("/");
  });
});
