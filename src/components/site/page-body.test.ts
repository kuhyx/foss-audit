// @vitest-environment node
import { experimental_AstroContainer as AstroContainer } from "astro/container";

import type { Page } from "../../lib/site/content.ts";

import { elementAt } from "../../lib/array.ts";
import { SITE_URL } from "../../lib/site/config.ts";
import { PAGES } from "../../lib/site/content.ts";
import NotFound from "../../pages/404.astro";
import PageBody from "./PageBody.astro";

async function render(page: Page): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-unsafe-argument -- typed lint cannot see .astro component types
  return await container.renderToString(PageBody, { props: { page } });
}

describe("PageBody", () => {
  it("links the homepage to every other page and to llms.txt with real anchors", async () => {
    const html = await render(elementAt(PAGES, 0));
    for (const p of PAGES.slice(1)) expect(html).toContain(`<a href="${p.path}">`);
    expect(html).toContain('<a href="llms.txt">');
    expect(html).toContain('<pre><code class="language-bash">');
    expect(html).not.toContain("home</a>");
  });

  it("escapes text and links a docs page back home", async () => {
    const custom: Page = {
      blocks: [
        { kind: "paragraph", text: 'a < b & "c"' },
        { items: ["pacman"], kind: "codes" },
        { kind: "heading", text: "H" },
        { items: [["t", "d"]], kind: "terms" },
      ],
      description: "d",
      path: "x/",
      title: "T",
    };
    const html = await render(custom);
    expect(html).toContain("a &lt; b &amp; &quot;c&quot;");
    expect(html).toContain('<ul class="codes">');
    expect(html).toMatch(/<dt>t<\/dt>\s*<dd>d<\/dd>/);
    expect(html).toContain('<a href="../">← FOSS audit home</a>');
  });
});

describe("404 page", () => {
  it("has real text and absolute links that work at any depth", async () => {
    const container = await AstroContainer.create();
    // eslint-disable-next-line @typescript-eslint/no-unsafe-argument -- typed lint cannot see .astro component types
    const html = await container.renderToString(NotFound);
    expect(html).toContain('<h1><span aria-label="Page not found">🗄</span></h1>');
    expect(html).toContain('<main class="doc">');
    for (const p of PAGES) expect(html).toContain(`href="${SITE_URL}${p.path}"`);
    expect(html).not.toContain("There is no page at this address</p>");
  });
});
