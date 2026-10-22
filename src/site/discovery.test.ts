import { SITE_URL } from "./config.ts";
import { PAGES } from "./content.ts";
import { aiCatalog, llmsTxt, robotsTxt, sitemapXml } from "./discovery.ts";

const BASE = SITE_URL;

describe("robots.txt", () => {
  it("allows every agent, training crawlers included, and names the sitemap", () => {
    const robots = robotsTxt(BASE);
    for (const agent of ["*", "GPTBot", "ClaudeBot", "CCBot", "Google-Extended"]) {
      expect(robots).toContain(`User-agent: ${agent}\nAllow: /\n`);
    }
    expect(robots).not.toMatch(/disallow/i);
    expect(robots.trimEnd().split("\n").at(-1)).toBe(`Sitemap: ${BASE}sitemap.xml`);
  });
});

describe("sitemap.xml", () => {
  it("lists every page once, absolute on the site URL", () => {
    const xml = sitemapXml(PAGES, BASE);
    expect(xml.startsWith('<?xml version="1.0" encoding="UTF-8"?>')).toBe(true);
    const locs = xml.matchAll(/<loc>([^<]+)<\/loc>/g).map((m) => m[1]).toArray();
    expect(locs).toEqual(PAGES.map((page) => `${BASE}${page.path}`));
  });
});

describe("llms.txt", () => {
  it("has a title, a summary and a described link per page", () => {
    const lines = llmsTxt(PAGES, BASE).split("\n");
    expect(lines[0]).toBe("# FOSS audit");
    expect(lines[2]).toMatch(/^> \S/);
    expect(lines).toContain("## Pages");
    for (const page of PAGES) {
      expect(lines).toContain(`- [${page.title}](${BASE}${page.path}): ${page.description}`);
    }
  });
});

describe("AI Catalog", () => {
  it("is a valid catalog listing llms.txt, the sitemap and every mirror", () => {
    const catalog = aiCatalog(PAGES, BASE);
    expect(catalog.specVersion).toBe("1.0");
    expect(catalog.host.displayName).toBe("FOSS audit");
    const urls = catalog.entries.map((entry) => entry.url);
    expect(urls).toContain(`${BASE}llms.txt`);
    expect(urls).toContain(`${BASE}sitemap.xml`);
    for (const page of PAGES) expect(urls).toContain(`${BASE}${page.path}index.md`);
    for (const entry of catalog.entries) {
      expect(entry.identifier).toMatch(/^urn:air:foss-audit\.kuhy\.duckdns\.org:foss-audit:[\w-]+$/);
      expect(entry.type).toMatch(/^[a-z]+\/[\w.+-]+$/);
    }
    const ids = new Set(catalog.entries.map((entry) => entry.identifier));
    expect(ids.size).toBe(catalog.entries.length);
  });
});
