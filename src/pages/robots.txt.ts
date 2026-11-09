import type { APIRoute } from "astro";

import { siteResponse } from "../lib/site/build.ts";
import { SITE_URL } from "../lib/site/config.ts";

export const GET: APIRoute = () => siteResponse("robots.txt", "text/plain; charset=utf-8", SITE_URL);
