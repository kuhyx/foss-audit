/**
 * The agent discovery files: robots.txt, sitemap.xml, llms.txt and the AI
 * Catalog (/.well-known/ai-catalog.json, ai-catalog specVersion 1.0). All are
 * built from the page table and the one site URL.
 */
import type { Page } from "./content.ts";

import { elementAt } from "../lib/array.ts";
import { absoluteUrl, SITE_NAME } from "./config.ts";

/**
Named so the intent is explicit: training crawlers are welcome too.
*/
const AGENTS = ["*", "GPTBot", "ClaudeBot", "CCBot", "Google-Extended"] as const;

/**
The catalog namespace: this project, whatever host it is served from.
*/
const NAMESPACE = "foss-audit";

export interface CatalogEntry {
  readonly displayName: string;
  readonly identifier: string;
  readonly type: string;
  readonly url: string;
}

export interface Catalog {
  readonly entries: readonly CatalogEntry[];
  readonly host: { readonly displayName: string; readonly documentationUrl: string };
  readonly specVersion: string;
}

/**
 * robots.txt: every agent may read everything.
 *
 * @param base - The site URL.
 * @returns The file content.
 */
export function robotsTxt(base: string): string {
  const groups = AGENTS.map((agent) => `User-agent: ${agent}\nAllow: /\n`);
  return `${groups.join("\n")}\nSitemap: ${absoluteUrl("sitemap.xml", base)}\n`;
}

/**
 * sitemap.xml listing every page.
 *
 * @param pages - Every public page.
 * @param base - The site URL.
 * @returns The XML document.
 */
export function sitemapXml(pages: readonly Page[], base: string): string {
  const urls = pages.map((p) => `  <url><loc>${absoluteUrl(p.path, base)}</loc></url>`);
  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.join("\n")}
</urlset>
`;
}

/**
 * llms.txt: title, summary, and a described link per page.
 *
 * @param pages - Every public page; the first is the homepage.
 * @param base - The site URL.
 * @returns The file content.
 */
export function llmsTxt(pages: readonly Page[], base: string): string {
  const summary = elementAt(pages, 0).description;
  const links = pages.map((p) => `- [${p.title}](${absoluteUrl(p.path, base)}): ${p.description}`);
  const mirrors = "Every page has a markdown mirror at <page>/index.md.";
  return `# ${SITE_NAME}\n\n> ${summary}\n\n${mirrors}\n\n## Pages\n\n${links.join("\n")}\n`;
}

/**
 * The AI Catalog: llms.txt, the sitemap and every markdown mirror.
 *
 * @param pages - Every public page.
 * @param base - The site URL.
 * @returns The catalog object (serialise with JSON.stringify).
 */
export function aiCatalog(pages: readonly Page[], base: string): Catalog {
  const { host: publisher } = new URL(base);
  const entry = (name: string, displayName: string, type: string, path: string): CatalogEntry => ({ displayName, identifier: `urn:air:${publisher}:${NAMESPACE}:${name}`, type, url: absoluteUrl(path, base) });
  const mirrors = pages.map((p) => entry(`mirror-${p.path.replace(/\/$/, "") || "home"}`, `${p.title} (markdown)`, "text/markdown", `${p.path}index.md`));
  return {
    entries: [
      entry("llms", "llms.txt", "text/plain", "llms.txt"),
      entry("sitemap", "Sitemap", "application/xml", "sitemap.xml"),
      ...mirrors,
    ],
    host: { displayName: SITE_NAME, documentationUrl: absoluteUrl("", base) },
    specVersion: "1.0",
  };
}
