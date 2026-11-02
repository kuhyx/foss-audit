import { makeProgress, makeScan } from "../test/fixtures.ts";
import { parseProgress, parseRemove, parseScan } from "./schema.ts";

describe("parseScan", () => {
  it("accepts a well-formed response and returns it typed", () => {
    const scan = makeScan();
    const parsed = parseScan(structuredClone(scan));
    expect(parsed.items.map((item) => item.id)).toEqual(scan.items.map((item) => item.id));
    expect(parsed.host).toBe(scan.host);
  });

  it("leaves the remove fields off scan items, whether or not the body has them", () => {
    const parsed = parseScan(makeScan());
    expect(parsed.items.every((item) => !("removeCommand" in item) && !("removeVia" in item))).toBe(true);
  });

  it("accepts null alternative, version and url", () => {
    const parsed = parseScan(makeScan());
    expect(parsed.items.some((item) => item.version === null)).toBe(true);
    expect(parsed.items.some((item) => item.url === null)).toBe(true);
  });

  it("names the offending path when an enum value is unknown", () => {
    const scan = makeScan();
    const body = { ...scan, items: [{ ...scan.items[0], source: "snap" }] };
    expect(() => parseScan(body)).toThrow(/at "items\.0\.source"/u);
  });

  it.each(["own", "blob", "unknown"])("rejects the removed verdict %s", (verdict) => {
    const scan = makeScan();
    const body = { ...scan, items: [{ ...scan.items[0], verdict }] };
    expect(() => parseScan(body)).toThrow(/at "items\.0\.verdict"/u);
  });

  it("requires the boolean own flag", () => {
    const scan = makeScan();
    const item: Partial<(typeof scan.items)[number]> = { ...scan.items[0] };
    delete item.own;
    expect(() => parseScan({ ...scan, items: [item] })).toThrow(/at "items\.0\.own"/u);
  });

  it("requires the boolean loose flag", () => {
    const scan = makeScan();
    const item: Partial<(typeof scan.items)[number]> = { ...scan.items[0] };
    delete item.loose;
    expect(() => parseScan({ ...scan, items: [item] })).toThrow(/at "items\.0\.loose"/u);
  });

  it("defaults a missing dangling flag to false", () => {
    const scan = makeScan();
    const item: Partial<(typeof scan.items)[number]> = { ...scan.items[0] };
    delete item.dangling;
    expect(parseScan({ ...scan, items: [item] }).items[0]?.dangling).toBe(false);
  });

  it("rejects a missing top-level field", () => {
    const scan: Partial<ReturnType<typeof makeScan>> = makeScan();
    delete scan.host;
    expect(() => parseScan(scan)).toThrow(/at "host"/u);
  });

  it("rejects a non-object body", () => {
    expect(() => parseScan("nope")).toThrow(/failed validation at ""/u);
  });

  it("rejects a bad alternative fit", () => {
    const scan = makeScan();
    const item = { ...scan.items[1], alternative: { ...scan.items[1]?.alternative, fit: "great" } };
    expect(() => parseScan({ ...scan, items: [item] })).toThrow(/alternative\.fit/u);
  });
});

describe("scanning flag", () => {
  it("defaults to false when a saved scan file lacks it", () => {
    const saved: Partial<ReturnType<typeof makeScan>> = makeScan();
    delete saved.scanning;
    expect(parseScan(saved).scanning).toBe(false);
  });

  it("keeps scanning: true", () => {
    expect(parseScan({ ...makeScan(), scanning: true }).scanning).toBe(true);
  });
});

describe("parseProgress", () => {
  it("accepts a running progress with an unknown total", () => {
    const progress = makeProgress({
      generatedAt: "2026-10-11T14:02:11Z",
      itemsFound: 9120,
      running: [{ done: 3400, source: "npm-cache", total: null }],
      sourcesDone: 14,
    });
    expect(parseProgress(structuredClone(progress))).toEqual(progress);
  });

  it("names the offending path", () => {
    expect(() => parseProgress({ ...makeProgress(), sourcesDone: "x" })).toThrow(
      /\/api\/scan\/progress response failed validation at "sourcesDone"/u,
    );
  });
});

describe("parseRemove", () => {
  it("accepts a map of id to remove fields, with a null command", () => {
    const body = { "a:b": { removeCommand: null, removeVia: "" }, "c:d": { removeCommand: "rm x", removeVia: "why" } };
    expect(parseRemove(body)).toEqual(body);
  });

  it("names the offending path", () => {
    expect(() => parseRemove({ "a:b": { removeCommand: "x" } })).toThrow(/\/api\/remove response failed validation at "a:b\.removeVia"/u);
  });
});
