import type { Page } from "./content.ts";

import { SITE_URL } from "./config.ts";
import { PAGES } from "./content.ts";
import { documentTitle, headTags } from "./head.ts";
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
    for (const word of ["Non-free", "FOSS (partial)", "waydroid", "pip-cache", "Easy wins", "PgUp PgDn", "Astro"]) {
      expect(text).toContain(word);
    }
    expect(text).not.toContain("React");
  });
});

describe("head", () => {
  it("puts the discovery links and JSON-LD in every head", () => {
    for (const p of PAGES) {
      const head = headTags(p, BASE);
      const up = p.path === "" ? "" : "../";
      expect(head).toContain(`<link rel="ai-catalog" href="${up}.well-known/ai-catalog.json" type="application/ai-catalog+json">`);
      expect(head).toContain('<link rel="alternate" type="text/markdown" href="index.md">');
      expect(head).toContain(`<link rel="canonical" href="${BASE}${p.path}">`);
      expect(head).toContain(`<link rel="help" type="text/plain" href="${up}llms.txt" title="llms.txt">`);
      expect(jsonLd(head)["@context"]).toBe("https://schema.org");
    }
    const homeHead = headTags(page(""), BASE);
    expect(jsonLd(homeHead)["@type"]).toBe("WebSite");
    const viewsHead = headTags(page("views/"), BASE);
    expect(jsonLd(viewsHead)).toMatchObject({ "@type": "WebPage", isPartOf: { url: BASE } });
  });

  it("escapes < in JSON-LD so no text can close the script element", () => {
    const hostile: Page = { blocks: [], description: "</script><b>", path: "x/", title: "T" };
    const head = headTags(hostile, BASE);
    expect(head).not.toContain("</script><b>");
    expect(jsonLd(head).description).toBe("</script><b>");
  });

  it("titles the homepage with the site name alone", () => {
    expect(documentTitle(page(""))).toBe("FOSS audit");
    expect(documentTitle(page("verdicts/"))).toBe("How verdicts are decided · FOSS audit");
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
    expect(pageMarkdown(page("views/"), BASE)).toMatch(/^- \*\*Summary\*\*: /m);
  });
});
