/**
 * Title and shared discovery tags for every prerendered page's head.
 */
import type { Page } from "./content.ts";

import { absoluteUrl, relativeHref, SITE_NAME } from "./config.ts";

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

export function headTags(page: Page, base: string): string {
  const to = (path: string): string => relativeHref(page.path, path);
  const mirror = `${page.path}index.md`;
  return [
    `<link rel="canonical" href="${absoluteUrl(page.path, base)}">`,
    `<link rel="ai-catalog" href="${to(".well-known/ai-catalog.json")}" type="application/ai-catalog+json">`,
    `<link rel="alternate" type="text/markdown" href="${to(mirror)}">`,
    `<link rel="help" type="text/plain" href="${to("llms.txt")}" title="llms.txt">`,
    jsonLd(page, base),
  ].join("\n");
}
