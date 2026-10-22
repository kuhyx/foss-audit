/**
 * HTML for the prerendered pages: the homepage body that index.html ships
 * before React mounts, the static docs pages, and 404.html.
 *
 * Every page gets its head tags from headTags(), so the discovery links and
 * JSON-LD are emitted in one place, never page by page.
 */
import type { Block, Page } from "./content.ts";

import { absoluteUrl, relativeHref, SITE_NAME } from "./config.ts";
import { STYLE } from "./style.ts";

/**
Escape text for HTML element content and double-quoted attributes.
*/
export function esc(text: string): string {
  // `&` first, so the entities added after it are not escaped again.
  return text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

function blockHtml(block: Block, from: string): string {
  switch (block.kind) {
    case "code": {
      return `<pre><code class="language-${block.lang}">${esc(block.code)}</code></pre>`;
    }
    case "codes": {
      const items = block.items.map((item) => `<li><code>${esc(item)}</code></li>`);
      return `<ul class="codes">${items.join("")}</ul>`;
    }
    case "heading": {
      return `<h2>${esc(block.text)}</h2>`;
    }
    case "links": {
      const items = block.items.map((item) => `<li><a href="${relativeHref(from, item.path)}">${esc(item.title)}</a>: ${esc(item.note)}</li>`);
      return `<ul>${items.join("")}</ul>`;
    }
    case "paragraph": {
      return `<p>${esc(block.text)}</p>`;
    }
    case "terms": {
      const rows = block.items.map(([term, text]) => `<div><dt>${esc(term)}</dt><dd>${esc(text)}</dd></div>`);
      return `<dl>${rows.join("")}</dl>`;
    }
  }
}

/**
`<title>` text: the site name alone on the homepage.
*/
export function documentTitle(page: Page): string {
  return page.path === "" ? SITE_NAME : `${page.title} · ${SITE_NAME}`;
}

function jsonLd(page: Page, base: string): string {
  const url = absoluteUrl(page.path, base);
  const data =
    page.path === ""
      ? { "@type": "WebSite", description: page.description, name: SITE_NAME, url }
      : {
          "@type": "WebPage",
          description: page.description,
          isPartOf: { "@type": "WebSite", name: SITE_NAME, url: absoluteUrl("", base) },
          name: page.title,
          url,
        };
  const json = JSON.stringify({ "@context": "https://schema.org", ...data }).replaceAll("<", String.raw`\u003c`);
  return `<script type="application/ld+json">${json}</script>`;
}

/**
 * Head tags shared by every page: canonical, AI Catalog, markdown mirror,
 * llms.txt and JSON-LD.
 *
 * @param page - The page the tags are for.
 * @param base - The site URL.
 * @returns The tags, one per line.
 */
export function headTags(page: Page, base: string): string {
  const to = (path: string): string => relativeHref(page.path, path);
  const mirror = to(`${page.path}index.md`);
  return [
    `<link rel="canonical" href="${absoluteUrl(page.path, base)}">`,
    `<link rel="ai-catalog" href="${to(".well-known/ai-catalog.json")}" type="application/ai-catalog+json">`,
    `<link rel="alternate" type="text/markdown" href="${mirror}">`,
    `<link rel="help" type="text/plain" href="${to("llms.txt")}" title="llms.txt">`,
    jsonLd(page, base),
  ].join("\n");
}

/**
 * The page's visible content (no layout chrome), as the homepage's
 * `<div id="root">` and the docs pages' `<main>` carry it.
 *
 * @param page - The page to render.
 * @returns HTML for the page body.
 */
export function pageBody(page: Page): string {
  const back = page.path === "" ? [] : [`<p><a href="${relativeHref(page.path, "")}">← ${SITE_NAME} home</a></p>`];
  return [
    `<h1>${esc(page.title)}</h1>`,
    `<p class="lead">${esc(page.description)}</p>`,
    ...page.blocks.map((block) => blockHtml(block, page.path)),
    ...back,
  ].join("\n");
}

function documentHtml(title: string, description: string, head: string, body: string): string {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${esc(title)}</title>
<meta name="description" content="${esc(description)}">
${head}
<style>${STYLE}</style>
</head>
<body>
<main class="doc">
${body}
</main>
</body>
</html>
`;
}

/**
 * A standalone docs page.
 *
 * @param page - The page to render.
 * @param base - The site URL.
 * @returns The full HTML document.
 */
export function pageHtml(page: Page, base: string): string {
  return documentHtml(documentTitle(page), page.description, headTags(page, base), pageBody(page));
}

/**
 * 404.html. A host serves it at whatever depth the missing path had, so its
 * links are absolute rather than relative.
 *
 * @param pages - Every page, to link to.
 * @param base - The site URL.
 * @returns The full HTML document.
 */
export function notFoundHtml(pages: readonly Page[], base: string): string {
  const links = pages.map((p) => `<li><a href="${absoluteUrl(p.path, base)}">${esc(p.title)}</a>: ${esc(p.description)}</li>`);
  const body = `<h1>Page not found</h1>
<p class="lead">There is no page at this address on the ${SITE_NAME} site. It may have moved; these are the pages that exist:</p>
<ul>${links.join("")}</ul>`;
  return documentHtml(`Page not found · ${SITE_NAME}`, "No page at this address.", "", body);
}
