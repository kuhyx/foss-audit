import type { APIRoute } from "astro";

import { siteResponse } from "../lib/site/build.ts";
import { SITE_URL } from "../lib/site/config.ts";

export const GET: APIRoute = () => siteResponse("sitemap.xml", "application/xml", SITE_URL);
