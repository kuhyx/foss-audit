import { makeScan } from "../test/fixtures.ts";
import { fetchScan } from "./scan-api.ts";

const fetchMock = vi.fn<typeof fetch>();

function preload(value: null | { body: unknown; status: number }): void {
  Reflect.set(globalThis, "__scanPreload", Promise.resolve(value));
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  Reflect.deleteProperty(globalThis, "__scanPreload");
});

describe("fetchScan with the page's early request", () => {
  it("uses the scan index.html already fetched, without a second request", async () => {
    preload({ body: makeScan(), status: 200 });
    const fetched = await fetchScan(false);
    expect(fetched.scan?.host).toBe(makeScan().host);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("uses it once only", async () => {
    preload({ body: makeScan(), status: 200 });
    await fetchScan(false);
    fetchMock.mockResolvedValueOnce(Response.json(makeScan()));
    await fetchScan(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("reads a 202 as scanning with no result yet", async () => {
    preload({ body: null, status: 202 });
    expect(await fetchScan(false)).toEqual({ scan: null, scanning: true });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([null, { body: null, status: 500 }])("falls back to a normal fetch for %j", async (early) => {
    preload(early);
    fetchMock.mockResolvedValueOnce(Response.json(makeScan()));
    const fetched = await fetchScan(false);
    expect(fetched.scan).not.toBeNull();
    expect(fetchMock).toHaveBeenCalledWith("/api/scan");
  });

  it("never uses it for a refresh", async () => {
    preload({ body: makeScan(), status: 200 });
    fetchMock.mockResolvedValueOnce(Response.json(makeScan()));
    await fetchScan(true);
    expect(fetchMock).toHaveBeenCalledWith("/api/scan?refresh=1");
  });

  it("still validates the early body", async () => {
    preload({ body: { ...makeScan(), host: 1 }, status: 200 });
    await expect(fetchScan(false)).rejects.toThrow('"host"');
  });
});
