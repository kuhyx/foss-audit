import { absoluteUrl, relativeHref, SITE_URL } from "./config.ts";

describe("site config", () => {
  it("lives at a host root, where robots.txt and /.well-known count", () => {
    expect(SITE_URL).toBe("https://foss-audit.kuhy.duckdns.org/");
    const { pathname } = new URL(SITE_URL);
    expect(pathname).toBe("/");
  });

  it("derives every absolute URL from the site URL", () => {
    expect(absoluteUrl("")).toBe(SITE_URL);
    expect(absoluteUrl("verdicts/")).toBe(`${SITE_URL}verdicts/`);
    expect(absoluteUrl("llms.txt", "https://example.org/sub/")).toBe("https://example.org/sub/llms.txt");
  });

  it("links pages relatively, so one build works on any host", () => {
    expect(relativeHref("", "")).toBe("./");
    expect(relativeHref("", "sources/")).toBe("sources/");
    expect(relativeHref("verdicts/", "")).toBe("../");
    expect(relativeHref("verdicts/", "sources/")).toBe("../sources/");
    expect(relativeHref("verdicts/", "verdicts/index.md")).toBe("index.md");
    expect(relativeHref("verdicts/", "llms.txt")).toBe("../llms.txt");
  });
});
