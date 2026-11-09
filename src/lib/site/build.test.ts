import type { APIContext } from "astro";

import * as catalog from "../../pages/.well-known/ai-catalog.json.ts";
import * as mirror from "../../pages/[...path].md.ts";
import * as llms from "../../pages/llms.txt.ts";
import * as robots from "../../pages/robots.txt.ts";
import * as sitemap from "../../pages/sitemap.xml.ts";
import { siteFiles, siteResponse } from "./build.ts";
import { SITE_URL } from "./config.ts";
import { PAGES } from "./content.ts";

const BASE = SITE_URL;

async function get(route: { GET: unknown }, parameters: Record<string, string> = {}): Promise<Response> {
  const handler = route.GET as (context: Pick<APIContext, "params">) => Promise<Response> | Response;
  return await handler({ params: parameters });
}

describe("siteFiles", () => {
  it("emits the discovery files and a markdown mirror per route, no HTML", () => {
    const files = siteFiles(BASE);
    for (const name of ["robots.txt", "sitemap.xml", "llms.txt", ".well-known/ai-catalog.json"]) {
      expect(files.get(name)?.length).toBeGreaterThan(0);
    }
    for (const p of PAGES) expect(files.get(`${p.path}index.md`)).toContain(`# ${p.title}`);
    expect(files.keys().filter((name) => name.endsWith(".html")).toArray()).toEqual([]);
    expect(JSON.parse(files.get(".well-known/ai-catalog.json") ?? "")).toHaveProperty("specVersion", "1.0");
  });

  it("refuses a file it does not emit rather than serving an empty one", () => {
    expect(() => siteResponse("nope.txt", "text/plain", BASE)).toThrow(/nope\.txt/);
  });
});

describe("endpoints", () => {
  it.each([
    [robots, "robots.txt", "text/plain; charset=utf-8"],
    [llms, "llms.txt", "text/plain; charset=utf-8"],
    [sitemap, "sitemap.xml", "application/xml"],
    [catalog, ".well-known/ai-catalog.json", "application/ai-catalog+json"],
  ])("serve %#: %s from the site URL", async (route, name, type) => {
    const response = await get(route);
    expect(response.headers.get("Content-Type")).toBe(type);
    expect(await response.text()).toBe(siteFiles(BASE).get(name));
  });

  it("prerenders one markdown mirror per page at <page>/index.md", async () => {
    const paths = mirror.getStaticPaths().map((entry) => entry.params.path);
    expect(paths).toEqual(PAGES.map((p) => `${p.path}index`));
    for (const path of paths) {
      const response = await get(mirror, { path });
      expect(response.headers.get("Content-Type")).toBe("text/markdown; charset=utf-8");
      expect(await response.text()).toBe(siteFiles(BASE).get(`${path}.md`));
    }
  });

  it("throws for a mirror without a path param", async () => {
    await expect(get(mirror)).rejects.toThrow(/no site file \.md/);
  });
});
