import { act, renderHook, waitFor } from "@testing-library/react";

import { makeScan } from "../test/fixtures.ts";
import { useScan } from "./use-scan.ts";

function respond(body: unknown, status = 200): Response {
  return Response.json(body, { status });
}

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useScan", () => {
  it("loads and validates /api/scan", async () => {
    fetchMock.mockResolvedValueOnce(respond(makeScan()));
    const { result } = renderHook(() => useScan());
    expect(result.current.state.kind).toBe("loading");
    await waitFor(() => {
      expect(result.current.state.kind).toBe("ready");
    });
    expect(fetchMock).toHaveBeenCalledWith("/api/scan");
  });

  it("reports an HTTP error", async () => {
    fetchMock.mockResolvedValueOnce(respond({}, 500));
    const { result } = renderHook(() => useScan());
    await waitFor(() => {
      expect(result.current.state).toEqual({ kind: "error", message: "HTTP 500 from /api/scan" });
    });
  });

  it("reports a schema failure with its path", async () => {
    fetchMock.mockResolvedValueOnce(respond({ ...makeScan(), host: 1 }));
    const { result } = renderHook(() => useScan());
    await waitFor(() => {
      expect(result.current.state.kind).toBe("error");
    });
    const state = result.current.state;
    expect(state.kind === "error" && state.message).toContain('"host"');
  });

  it("stringifies a non-Error rejection", async () => {
    fetchMock.mockRejectedValueOnce("offline");
    const { result } = renderHook(() => useScan());
    await waitFor(() => {
      expect(result.current.state).toEqual({ kind: "error", message: "offline" });
    });
  });

  it("rescans with refresh=1, keeping the old scan visible meanwhile", async () => {
    fetchMock.mockResolvedValueOnce(respond(makeScan()));
    const { result } = renderHook(() => useScan());
    await waitFor(() => {
      expect(result.current.state.kind).toBe("ready");
    });

    const { promise, resolve } = Promise.withResolvers<Response>();
    fetchMock.mockReturnValueOnce(promise);
    act(() => {
      result.current.rescan();
    });
    expect(result.current.state).toMatchObject({ kind: "ready", refreshing: true });
    expect(fetchMock).toHaveBeenLastCalledWith("/api/scan?refresh=1");

    await act(async () => {
      resolve(respond(makeScan({ host: "new" })));
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(result.current.state).toMatchObject({ refreshing: false, scan: { host: "new" } });
    });
  });

  it("keeps the last scan and records the error when a rescan fails", async () => {
    fetchMock.mockResolvedValueOnce(respond(makeScan()));
    const { result } = renderHook(() => useScan());
    await waitFor(() => {
      expect(result.current.state.kind).toBe("ready");
    });
    fetchMock.mockRejectedValueOnce(new Error("boom"));
    act(() => {
      result.current.rescan();
    });
    await waitFor(() => {
      expect(result.current.state).toMatchObject({ kind: "ready", refreshError: "boom", refreshing: false });
    });
  });

  it("falls back to loading, then error, when rescanning from an error", async () => {
    fetchMock.mockRejectedValueOnce(new Error("first"));
    const { result } = renderHook(() => useScan());
    await waitFor(() => {
      expect(result.current.state.kind).toBe("error");
    });
    fetchMock.mockRejectedValueOnce(new Error("second"));
    act(() => {
      result.current.rescan();
    });
    expect(result.current.state.kind).toBe("loading");
    await waitFor(() => {
      expect(result.current.state).toEqual({ kind: "error", message: "second" });
    });
  });

  it("ignores a response that arrives after unmount", async () => {
    const { promise, resolve } = Promise.withResolvers<Response>();
    fetchMock.mockReturnValueOnce(promise);
    const { result, unmount } = renderHook(() => useScan());
    unmount();
    await act(async () => {
      resolve(respond(makeScan()));
      await Promise.resolve();
    });
    expect(result.current.state.kind).toBe("loading");
  });

  it("ignores a failure that arrives after unmount", async () => {
    const { promise, reject } = Promise.withResolvers<Response>();
    fetchMock.mockReturnValueOnce(promise);
    const { result, unmount } = renderHook(() => useScan());
    unmount();
    await act(async () => {
      reject(new Error("late"));
      await Promise.resolve();
    });
    expect(result.current.state.kind).toBe("loading");
  });
});
