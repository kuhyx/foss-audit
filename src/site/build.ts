/**
 * Everything the build writes for agents, from the page table: the files
 * emitted next to the bundle, and the prerendered homepage in index.html.
 */
import { elementAt } from "../lib/array.ts";
import { PAGES } from "./content.ts";
import { aiCatalog, llmsTxt, robotsTxt, sitemapXml } from "./discovery.ts";
import { documentTitle, esc, headTags, notFoundHtml, pageBody, pageHtml } from "./render-html.ts";
import { pageMarkdown } from "./render-markdown.ts";

const ROOT = '<div id="root"></div>';

/**
 * Every generated file except index.html (the Vite entry, see injectHome).
 *
 * @param base - The site URL.
 * @returns Output-relative file name -> content, in emit order.
 */
export function siteFiles(base: string): Map<string, string> {
  const files = new Map<string, string>([
    [".well-known/ai-catalog.json", `${JSON.stringify(aiCatalog(PAGES, base), null, 2)}\n`],
    ["404.html", notFoundHtml(PAGES, base)],
    ["llms.txt", llmsTxt(PAGES, base)],
    ["robots.txt", robotsTxt(base)],
    ["sitemap.xml", sitemapXml(PAGES, base)],
  ]);
  for (const page of PAGES) {
    if (page.path !== "") files.set(`${page.path}index.html`, pageHtml(page, base));
    files.set(`${page.path}index.md`, pageMarkdown(page, base));
  }
  return files;
}

/**
 * Prerender the homepage into the app shell: title, description and the
 * shared head tags into `<head>`, the page content into `<div id="root">`.
 * React replaces that content when it mounts; without JS it is the page.
 *
 * @param html - index.html as Vite reads it.
 * @param base - The site URL.
 * @returns The filled-in document.
 */
export function injectHome(html: string, base: string): string {
  if (!html.includes(ROOT)) {
    throw new Error(`index.html needs an empty ${ROOT} to prerender the homepage into`);
  }
  const home = elementAt(PAGES, 0);
  const head = [
    `<title>${esc(documentTitle(home))}</title>`,
    `<meta name="description" content="${esc(home.description)}">`,
    headTags(home, base),
  ].join("\n");
  const body = `<div id="root">${pageBody(home)}</div>`;
  return html.replace("</head>", () => `${head}\n</head>`).replace(ROOT, () => body);
}
