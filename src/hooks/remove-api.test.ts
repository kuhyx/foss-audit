import { CHROME, makeItem } from "../test/fixtures.ts";
import { postedIds, stubRemove } from "../test/remove-stub.ts";
import { respond } from "../test/route.ts";
import { fetchRemove, invalidateRemoveCache, withRemove, withRemoves } from "./remove-api.ts";

const BASH = makeItem();

describe("fetchRemove", () => {
  it("posts the ids as JSON and returns the fields per id", async () => {
    const mock = stubRemove([CHROME, BASH]);
    const infos = await fetchRemove([CHROME.id, BASH.id]);
    expect(mock).toHaveBeenCalledWith("/api/remove", expect.objectContaining({ method: "POST" }));
    expect(postedIds(mock)).toEqual([[CHROME.id, BASH.id]]);
    expect(infos.get(CHROME.id)).toEqual({ removeCommand: CHROME.removeCommand, removeVia: "" });
  });

  it("asks only for ids it does not hold, and not at all when it holds them all", async () => {
    const mock = stubRemove([CHROME, BASH]);
    await fetchRemove([CHROME.id]);
    const infos = await fetchRemove([CHROME.id, BASH.id, CHROME.id]);
    expect(postedIds(mock)).toEqual([[CHROME.id], [BASH.id]]);
    expect(infos.keys().toArray()).toEqual([CHROME.id, BASH.id]);
    await fetchRemove([BASH.id]);
    expect(mock).toHaveBeenCalledTimes(2);
  });

  it("leaves out ids the backend does not know, and asks again next time", async () => {
    const mock = stubRemove([BASH]);
    const infos = await fetchRemove(["gone:x"]);
    expect(infos.size).toBe(0);
    await fetchRemove(["gone:x"]);
    expect(mock).toHaveBeenCalledTimes(2);
  });

  it("forgets everything when a new scan is swapped in", async () => {
    const mock = stubRemove([BASH]);
    await fetchRemove([BASH.id]);
    invalidateRemoveCache();
    await fetchRemove([BASH.id]);
    expect(mock).toHaveBeenCalledTimes(2);
  });

  it("does not cache an answer that was in flight when a new scan arrived", async () => {
    const mock = stubRemove([BASH]);
    const pending = fetchRemove([BASH.id]);
    invalidateRemoveCache();
    const infos = await pending;
    expect(infos.get(BASH.id)).toBeDefined();
    await fetchRemove([BASH.id]);
    expect(mock).toHaveBeenCalledTimes(2);
  });

  it("throws on an HTTP error naming the endpoint", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(respond({ error: "x" }, 400)));
    await expect(fetchRemove(["a"])).rejects.toThrow("HTTP 400 from /api/remove");
  });

  it("throws on a body of the wrong shape, naming the path", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(respond({ a: { removeCommand: 1 } })));
    await expect(fetchRemove(["a"])).rejects.toThrow(/\/api\/remove response failed validation at "a\.removeCommand"/u);
  });
});

describe("withRemove(s)", () => {
  it("joins the fetched fields onto the items, in order, with none-known for a missing id", async () => {
    const mock = stubRemove([CHROME]);
    const out = await withRemoves([CHROME, { ...BASH, id: "gone:y" }]);
    expect(postedIds(mock)).toEqual([[CHROME.id, "gone:y"]]);
    expect(out.map((item) => [item.id, item.removeCommand, item.removeVia])).toEqual([
      [CHROME.id, CHROME.removeCommand, ""],
      ["gone:y", null, ""],
    ]);
  });

  it("does one item", async () => {
    stubRemove([CHROME]);
    const joined = await withRemove(CHROME);
    expect(joined.removeCommand).toBe(CHROME.removeCommand);
  });

  it("gives an item the backend does not know no command", async () => {
    stubRemove([]);
    const joined = await withRemove(CHROME);
    expect([joined.removeCommand, joined.removeVia]).toEqual([null, ""]);
  });
});
