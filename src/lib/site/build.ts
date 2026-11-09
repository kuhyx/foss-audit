/**
 * Every text artifact the build serves to agents, from the page table. The
 * endpoints in src/pages only look files up here.
 */
import { PAGES } from "./content.ts";
import { aiCatalog, llmsTxt, robotsTxt, sitemapXml } from "./discovery.ts";
import { pageMarkdown } from "./render-markdown.ts";

/**
 * @param base - The site URL.
 * @returns Output-relative file name -> content.
 */
export function siteFiles(base: string): Map<string, string> {
  const files = new Map<string, string>([
    [".well-known/ai-catalog.json", `${JSON.stringify(aiCatalog(PAGES, base), null, 2)}\n`],
    ["llms.txt", llmsTxt(PAGES, base)],
    ["robots.txt", robotsTxt(base)],
    ["sitemap.xml", sitemapXml(PAGES, base)],
  ]);
  for (const page of PAGES) files.set(`${page.path}index.md`, pageMarkdown(page, base));
  return files;
}

/**
 * One artifact as an HTTP response.
 *
 * @param name - Output-relative file name.
 * @param type - Its Content-Type.
 * @param base - The site URL.
 * @returns The response; throws for a name siteFiles() does not emit.
 */
export function siteResponse(name: string, type: string, base: string): Response {
  const body = siteFiles(base).get(name);
  if (body === undefined) throw new Error(`no site file ${name}`);
  return new Response(body, { headers: { "Content-Type": type } });
}
