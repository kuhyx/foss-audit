import type { RemoveFetch } from "./remove.ts";

import { CHROME, makeItem, makeScan } from "../test/fixtures.ts";
import { postedIds, stubRemove } from "../test/remove-stub.ts";
import { respond, urlOf } from "../test/route.ts";
import { fetchRemove, invalidateRemoveCache } from "./remove-api.ts";
import { watchRemove } from "./remove.ts";
import { load, refresh, resetScan } from "./scan.ts";
import { resetStore, store } from "./store.ts";

const BASH = makeItem();

function collect(ids: readonly string[]): { readonly seen: RemoveFetch[]; readonly stop: () => void } {
  const seen: RemoveFetch[] = [];
  const stop = watchRemove(ids, (result) => {
    seen.push(result);
  });
  return { seen, stop };
}

async function settle(): Promise<void> {
  await vi.waitFor(() => {
    expect(true).toBe(true);
  });
  await Promise.resolve();
}

describe("watchRemove", () => {
  it("is loading, then ready with the fields of its ids", async () => {
    stubRemove([CHROME, BASH]);
    const { seen, stop } = collect([CHROME.id, BASH.id]);
    expect(seen).toEqual([{ kind: "loading" }]);
    await vi.waitFor(() => {
      expect(seen.at(-1)?.kind).toBe("ready");
    });
    const last = seen.at(-1);
    expect(last?.kind === "ready" && last.infos.get(BASH.id)?.removeCommand).toBe(BASH.removeCommand);
    stop();
  });

  it("asks again, via loading, when a new scan invalidates the cache", async () => {
    const mock = stubRemove([BASH]);
    const { seen, stop } = collect([BASH.id]);
    await vi.waitFor(() => {
      expect(seen.at(-1)?.kind).toBe("ready");
    });
    invalidateRemoveCache();
    expect(seen.at(-1)?.kind).toBe("loading");
    await vi.waitFor(() => {
      expect(seen.at(-1)?.kind).toBe("ready");
    });
    expect(postedIds(mock)).toEqual([[BASH.id], [BASH.id]]);
    stop();
  });

  it("never delivers the answer of an invalidated round", async () => {
    const first = Promise.withResolvers<Response>();
    const mock = vi.fn<typeof fetch>().mockReturnValueOnce(first.promise);
    mock.mockResolvedValue(respond({ [BASH.id]: { removeCommand: "second", removeVia: "" } }));
    vi.stubGlobal("fetch", mock);
    const { seen, stop } = collect([BASH.id]);
    invalidateRemoveCache();
    await vi.waitFor(() => {
      expect(seen.at(-1)?.kind).toBe("ready");
    });
    first.resolve(respond({ [BASH.id]: { removeCommand: "stale", removeVia: "" } }));
    await settle();
    const last = seen.at(-1);
    expect(last?.kind === "ready" && last.infos.get(BASH.id)?.removeCommand).toBe("second");
    stop();
  });

  it("handles no ids without a request", async () => {
    const mock = stubRemove([]);
    const { seen, stop } = collect([]);
    await vi.waitFor(() => {
      expect(seen.at(-1)?.kind).toBe("ready");
    });
    expect(mock).not.toHaveBeenCalled();
    stop();
  });

  it("reports a failed request", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue("offline"));
    const { seen, stop } = collect([BASH.id]);
    await vi.waitFor(() => {
      expect(seen.at(-1)).toEqual({ kind: "error", message: "offline" });
    });
    stop();
  });

  it("delivers nothing after stop", async () => {
    const pending = Promise.withResolvers<Response>();
    vi.stubGlobal("fetch", vi.fn<typeof fetch>(() => pending.promise));
    const { seen, stop } = collect([BASH.id]);
    stop();
    pending.resolve(respond({}));
    await settle();
    expect(seen).toEqual([{ kind: "loading" }]);
    invalidateRemoveCache();
    expect(seen).toEqual([{ kind: "loading" }]);
  });
});

describe("scan and the remove cache", () => {
  it("drops cached remove fields only when a different scan is swapped in", async () => {
    resetScan();
    resetStore();
    let generatedAt = "2026-10-11T14:02:11Z";
    const mock = vi.fn<typeof fetch>((input) => {
      const body =
        urlOf(input) === "/api/remove" ? { [BASH.id]: { removeCommand: "x", removeVia: "" } } : makeScan({ generatedAt });
      return Promise.resolve(respond(body));
    });
    vi.stubGlobal("fetch", mock);
    const callsTo = (url: string): number => mock.mock.calls.filter(([input]) => urlOf(input) === url).length;
    await load();
    await fetchRemove([BASH.id]);
    refresh();
    await vi.waitFor(() => {
      expect(callsTo("/api/scan?refresh=1")).toBe(1);
    });
    await fetchRemove([BASH.id]);
    expect(callsTo("/api/remove")).toBe(1);

    generatedAt = "2026-10-12T09:00:00Z";
    refresh();
    await vi.waitFor(() => {
      expect(store.getState().scan).toMatchObject({ scan: { generatedAt } });
    });
    await fetchRemove([BASH.id]);
    expect(callsTo("/api/remove")).toBe(2);
  });
});
