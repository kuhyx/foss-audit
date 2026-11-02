import { act, renderHook, waitFor } from "@testing-library/react";

import { CHROME, makeItem, makeScan } from "../test/fixtures.ts";
import { postedIds, stubRemove } from "../test/remove-stub.ts";
import { respond, urlOf } from "../test/route.ts";
import { fetchRemove, invalidateRemoveCache } from "./remove-api.ts";
import { useRemoveInfos } from "./use-remove.ts";
import { useScan } from "./use-scan.ts";

const BASH = makeItem();

function never(): Promise<Response> {
  return new Promise<Response>(() => {});
}

describe("useRemoveInfos", () => {
  it("is loading, then ready with the fields of its ids", async () => {
    stubRemove([CHROME, BASH]);
    const { result } = renderHook(() => useRemoveInfos([CHROME.id, BASH.id]));
    expect(result.current.kind).toBe("loading");
    await waitFor(() => {
      expect(result.current.kind).toBe("ready");
    });
    const current = result.current;
    expect(current.kind === "ready" && current.infos.get(BASH.id)?.removeCommand).toBe(BASH.removeCommand);
  });

  it("asks again, via loading, when a new scan invalidates the cache", async () => {
    const mock = stubRemove([BASH]);
    const { result } = renderHook(() => useRemoveInfos([BASH.id]));
    await waitFor(() => {
      expect(result.current.kind).toBe("ready");
    });
    act(() => {
      invalidateRemoveCache();
    });
    expect(result.current.kind).toBe("loading");
    await waitFor(() => {
      expect(result.current.kind).toBe("ready");
    });
    expect(postedIds(mock)).toEqual([[BASH.id], [BASH.id]]);
  });

  it("does not fetch the same ids again on a rerender with an equal array", async () => {
    const mock = stubRemove([BASH]);
    const { rerender, result } = renderHook(() => useRemoveInfos([BASH.id]));
    await waitFor(() => {
      expect(result.current.kind).toBe("ready");
    });
    rerender();
    expect(mock).toHaveBeenCalledOnce();
  });

  it("handles no ids", async () => {
    const mock = stubRemove([]);
    const { result } = renderHook(() => useRemoveInfos([]));
    await waitFor(() => {
      expect(result.current.kind).toBe("ready");
    });
    expect(mock).not.toHaveBeenCalled();
  });

  it("ignores an answer that lands after unmount", async () => {
    const pending = Promise.withResolvers<Response>();
    vi.stubGlobal("fetch", vi.fn<typeof fetch>(() => pending.promise));
    const { result, unmount } = renderHook(() => useRemoveInfos([BASH.id]));
    unmount();
    pending.resolve(respond({}));
    await Promise.resolve();
    expect(result.current.kind).toBe("loading");
  });

  it("ignores a failure that lands after unmount", async () => {
    const pending = Promise.withResolvers<Response>();
    vi.stubGlobal("fetch", vi.fn<typeof fetch>(() => pending.promise));
    const { result, unmount } = renderHook(() => useRemoveInfos([BASH.id]));
    unmount();
    pending.reject(new Error("late"));
    await Promise.resolve();
    expect(result.current.kind).toBe("loading");
  });

  it("stays loading while the request is pending", () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>(never));
    const { result } = renderHook(() => useRemoveInfos([BASH.id]));
    expect(result.current.kind).toBe("loading");
  });
});

describe("useScan and the remove cache", () => {
  it("drops cached remove fields only when a different scan is swapped in", async () => {
    let generatedAt = "2026-10-11T14:02:11Z";
    const mock = vi.fn<typeof fetch>((input) => {
      const body = urlOf(input) === "/api/remove" ? { [BASH.id]: { removeCommand: "x", removeVia: "" } } : makeScan({ generatedAt });
      return Promise.resolve(respond(body));
    });
    vi.stubGlobal("fetch", mock);
    const callsTo = (url: string): number => mock.mock.calls.filter(([input]) => urlOf(input) === url).length;
    const { result } = renderHook(() => useScan());
    await waitFor(() => {
      expect(result.current.state.kind).toBe("ready");
    });
    await fetchRemove([BASH.id]);
    act(() => {
      result.current.rescan();
    });
    await waitFor(() => {
      expect(callsTo("/api/scan?refresh=1")).toBe(1);
    });
    await fetchRemove([BASH.id]);
    expect(callsTo("/api/remove")).toBe(1);

    generatedAt = "2026-10-12T09:00:00Z";
    act(() => {
      result.current.rescan();
    });
    await waitFor(() => {
      expect(callsTo("/api/scan?refresh=1")).toBe(2);
    });
    await fetchRemove([BASH.id]);
    expect(callsTo("/api/remove")).toBe(2);
  });
});
