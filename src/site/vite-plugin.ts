/**
 * Vite wiring for the agent-facing site: prerenders the homepage into
 * index.html (dev and build) and writes every generated file into the build
 * output once the bundle is on disk.
 *
 * The files are written with fs in closeBundle rather than emitted with
 * this.emitFile: that needs `this` as the Rollup context, and the outDir from
 * configResolved is all the plugin has to know.
 */
import type { Plugin } from "vite";

import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import { injectHome, siteFiles } from "./build.ts";
import { SITE_URL } from "./config.ts";

/**
 * @param base - The site URL; defaults to the one SITE_URL constant.
 * @returns The plugin.
 */
export function agentReadySite(base: string = SITE_URL): Plugin {
  let outDirectory = "";
  return {
    async closeBundle(): Promise<void> {
      for (const [name, source] of siteFiles(base)) {
        const file = path.join(outDirectory, name);
        await mkdir(path.dirname(file), { recursive: true });
        await writeFile(file, source);
      }
    },
    configResolved(config): void {
      outDirectory = path.resolve(config.root, config.build.outDir);
    },
    name: "foss-audit:agent-ready-site",
    transformIndexHtml: (html: string): string => injectHome(html, base),
  };
}
