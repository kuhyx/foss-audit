import type { Page } from "./content.ts";

import { SITE_URL } from "./config.ts";
import { PAGES } from "./content.ts";
import { headTags, notFoundHtml, pageBody, pageHtml } from "./render-html.ts";
import { pageMarkdown } from "./render-markdown.ts";

const BASE = SITE_URL;

function page(path: string): Page {
  const found = PAGES.find((p) => p.path === path);
  if (found === undefined) throw new Error(`no page ${path}`);
  return found;
}

function jsonLd(html: string): Record<string, unknown> {
  const match = /<script type="application\/ld\+json">(.+?)<\/script>/s.exec(html);
  return JSON.parse(match?.[1] ?? "null") as Record<string, unknown>;
}

describe("content", () => {
  it("has a homepage first and unique trailing-slash paths", () => {
    expect(PAGES[0]?.path).toBe("");
    const paths = PAGES.map((p) => p.path);
    const unique = new Set(paths);
    expect(unique.size).toBe(paths.length);
    for (const path of paths.slice(1)) expect(path).toMatch(/^[a-z-]+\/$/);
  });

  it("documents every verdict, source, view and shortcut the app knows", () => {
    const mirrors = PAGES.map((p) => pageMarkdown(p, BASE));
    const text = mirrors.join("\n");
    for (const word of ["Non-free", "FOSS (partial)", "waydroid", "pip-cache", "Easy wins", "PgUp PgDn"]) {
      expect(text).toContain(word);
    }
  });
});

describe("HTML pages", () => {
  it("puts the discovery links and JSON-LD in every head", () => {
    for (const p of PAGES) {
      const head = headTags(p, BASE);
      const up = p.path === "" ? "" : "../";
      expect(head).toContain(`<link rel="ai-catalog" href="${up}.well-known/ai-catalog.json" type="application/ai-catalog+json">`);
      expect(head).toContain('<link rel="alternate" type="text/markdown" href="index.md">');
      expect(head).toContain(`<link rel="canonical" href="${BASE}${p.path}">`);
      expect(jsonLd(head)["@context"]).toBe("https://schema.org");
    }
    const homeHead = headTags(page(""), BASE);
    expect(jsonLd(homeHead)["@type"]).toBe("WebSite");
    expect(homeHead).not.toContain("</script><");
  });

  it("links the homepage to every other page and to llms.txt with real anchors", () => {
    const body = pageBody(page(""));
    for (const p of PAGES.slice(1)) expect(body).toContain(`<a href="${p.path}">`);
    expect(body).toContain('<a href="llms.txt">');
  });

  it("tags code blocks with a language and escapes text", () => {
    const html = pageHtml(page(""), BASE);
    expect(html).toContain('<pre><code class="language-bash">');
    expect(html).not.toMatch(/<pre><code>/);
    const custom: Page = {
      blocks: [{ kind: "paragraph", text: "a < b & \"c\"" }],
      description: "d",
      path: "x/",
      title: "T",
    };
    expect(pageBody(custom)).toContain("a &lt; b &amp; &quot;c&quot;");
  });

  it("renders a standalone document per page with a way back home", () => {
    const html = pageHtml(page("verdicts/"), BASE);
    expect(html.startsWith('<!doctype html>\n<html lang="en">')).toBe(true);
    expect(html).toContain("<title>How verdicts are decided · FOSS audit</title>");
    expect(html).toContain('<a href="../">');
  });

  it("serves a 404 with real text and absolute links that work at any depth", () => {
    const html = notFoundHtml(PAGES, BASE);
    expect(html).toContain("<h1>Page not found</h1>");
    for (const p of PAGES) expect(html).toContain(`<a href="${BASE}${p.path}">`);
  });
});

describe("markdown mirrors", () => {
  it("mirrors the page with absolute links and fenced, tagged code", () => {
    const md = pageMarkdown(page(""), BASE);
    expect(md.startsWith("# FOSS audit\n\n> ")).toBe(true);
    expect(md).toContain("```bash\n./run.sh");
    expect(md).not.toMatch(/^```$\n(?!\n|$)/m);
    expect(md).toContain(`(${BASE}verdicts/)`);
    expect(pageMarkdown(page("sources/"), BASE)).toContain("- `pacman`");
  });
});
