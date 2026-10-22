import type { Plugin } from "vite";

import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { injectHome, siteFiles } from "./build.ts";
import { SITE_URL } from "./config.ts";
import { PAGES } from "./content.ts";
import { agentReadySite } from "./vite-plugin.ts";

const BASE = SITE_URL;
const SHELL = '<html><head><title>x</title></head><body><div id="root"></div></body></html>';

describe("siteFiles", () => {
  it("emits the discovery files, a 404 and an HTML + markdown file per route", () => {
    const files = siteFiles(BASE);
    for (const name of ["robots.txt", "sitemap.xml", "llms.txt", ".well-known/ai-catalog.json", "404.html", "index.md"]) {
      expect(files.get(name)?.length).toBeGreaterThan(0);
    }
    for (const p of PAGES.slice(1)) {
      expect(files.get(`${p.path}index.html`)).toContain(`<h1>${p.title}</h1>`);
      expect(files.get(`${p.path}index.md`)).toContain(`# ${p.title}`);
    }
    // index.html is the Vite entry: injectHome fills it instead.
    expect(files.has("index.html")).toBe(false);
    expect(JSON.parse(files.get(".well-known/ai-catalog.json") ?? "")).toHaveProperty("specVersion", "1.0");
  });
});

describe("injectHome", () => {
  it("prerenders the homepage into the root element and its tags into the head", () => {
    const html = injectHome(SHELL, BASE);
    const head = html.slice(0, html.indexOf("</head>"));
    expect(head).toContain('<link rel="ai-catalog"');
    expect(head).toContain("<title>FOSS audit</title>");
    const root = html.slice(html.indexOf('<div id="root">'));
    expect(root.startsWith('<div id="root"><h1>FOSS audit</h1>')).toBe(true);
    expect(root).toContain('<a href="verdicts/">');
  });

  it("refuses a shell without a root element rather than shipping an empty page", () => {
    expect(() => injectHome("<html><head></head><body></body></html>", BASE)).toThrow(/id="root"/);
  });
});

describe("agentReadySite", () => {
  it("fills index.html and writes every site file into the build output", async () => {
    const plugin: Plugin = agentReadySite(BASE);
    const transform = plugin.transformIndexHtml as unknown as (html: string) => string;
    expect(transform(SHELL)).toContain("<h1>FOSS audit</h1>");
    const root = await mkdtemp(path.join(tmpdir(), "foss-audit-site-"));
    const configResolved = plugin.configResolved as (config: unknown) => void;
    configResolved({ build: { outDir: "out" }, root });
    const closeBundle = plugin.closeBundle as () => Promise<void>;
    await closeBundle();
    for (const [name, source] of siteFiles(BASE)) {
      expect(await readFile(path.join(root, "out", name), "utf8")).toBe(source);
    }
    await rm(root, { force: true, recursive: true });
  });
});
