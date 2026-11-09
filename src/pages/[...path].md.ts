import type { APIRoute, GetStaticPaths } from "astro";

import { siteResponse } from "../lib/site/build.ts";
import { SITE_URL } from "../lib/site/config.ts";
import { PAGES } from "../lib/site/content.ts";

// `/index.md`, `/verdicts/index.md`, ...: the markdown mirror of every page.
export const getStaticPaths = (() => PAGES.map((page) => ({ params: { path: `${page.path}index` } }))) satisfies GetStaticPaths;

export const GET: APIRoute = ({ params }) => siteResponse(`${params.path ?? ""}.md`, "text/markdown; charset=utf-8", SITE_URL);
