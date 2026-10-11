import { makeScan } from "../test/fixtures.ts";
import { parseScan } from "./schema.ts";

describe("parseScan", () => {
  it("accepts a well-formed response and returns it typed", () => {
    const scan = makeScan();
    expect(parseScan(structuredClone(scan))).toEqual(scan);
  });

  it("accepts null alternative, version, url and removeCommand", () => {
    const scan = makeScan();
    const parsed = parseScan(scan);
    expect(parsed.items.some((item) => item.version === null)).toBe(true);
    expect(parsed.items.some((item) => item.removeCommand === null)).toBe(true);
  });

  it("names the offending path when an enum value is unknown", () => {
    const scan = makeScan();
    const body = { ...scan, items: [{ ...scan.items[0], source: "snap" }] };
    expect(() => parseScan(body)).toThrow(/at "items\.0\.source"/u);
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
