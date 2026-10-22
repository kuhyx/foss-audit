/**
 * Where the public site lives. Every absolute URL the build emits (sitemap,
 * robots.txt, llms.txt, AI Catalog, canonical links, JSON-LD, the 404 page)
 * is derived from SITE_URL, so moving the site is a one-line change.
 *
 * The site is not deployed yet. It must sit at a host root: robots.txt and
 * /.well-known/ only count there (RFC 9309, RFC 8615), so a GitHub Pages
 * project sub-path could never pass AgentReady. Page paths are site-relative
 * ("" for home, "verdicts/" ...) and links between pages are relative, so the
 * same build also works locally at http://127.0.0.1:5190/.
 */

export const SITE_URL = "https://foss-audit.kuhy.duckdns.org/";
export const SITE_NAME = "FOSS audit";

/**
 * Absolute URL of a site-relative path.
 *
 * @param path - Site-relative path, e.g. "" or "verdicts/" or "llms.txt".
 * @param base - The site URL, ending in "/".
 * @returns The absolute URL (any path in `base` is kept).
 */
export function absoluteUrl(path: string, base: string = SITE_URL): string {
  const url = new URL(path, base);
  return url.href;
}

/**
 * Relative href from one site-relative page path to another.
 *
 * @param from - Path of the page the link sits on ("" or "dir/").
 * @param to - Site-relative target path.
 * @returns A relative href that resolves to `to` from `from`.
 */
export function relativeHref(from: string, to: string): string {
  // Not under `from` means `from` is a non-empty "a/" or "a/b/": climb out.
  return to.startsWith(from) ? to.slice(from.length) || "./" : "../".repeat(from.split("/").length - 1) + to;
}
