/**
 * Markdown mirror of a page (`<route>/index.md`), from the same blocks the
 * HTML is rendered from. Links are absolute: a mirror is read out of context.
 */
import type { Block, Page } from "./content.ts";

import { absoluteUrl } from "./config.ts";

function blockMarkdown(block: Block, base: string): string {
  switch (block.kind) {
    case "code": {
      return `\`\`\`${block.lang}\n${block.code}\n\`\`\``;
    }
    case "codes": {
      return block.items.map((item) => `- \`${item}\``).join("\n");
    }
    case "heading": {
      return `## ${block.text}`;
    }
    case "links": {
      return block.items
        .map((item) => `- [${item.title}](${absoluteUrl(item.path, base)}): ${item.note}`)
        .join("\n");
    }
    case "paragraph": {
      return block.text;
    }
    case "terms": {
      return block.items.map(([term, text]) => `- **${term}**: ${text}`).join("\n");
    }
  }
}

/**
 * The page as markdown: H1 title, quoted summary, then its blocks.
 *
 * @param page - The page to mirror.
 * @param base - The site URL.
 * @returns The markdown document, ending in a newline.
 */
export function pageMarkdown(page: Page, base: string): string {
  const parts = [`# ${page.title}`, `> ${page.description}`, ...page.blocks.map((b) => blockMarkdown(b, base))];
  return `${parts.join("\n\n")}\n`;
}
