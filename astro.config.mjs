import { defineConfig } from "astro/config";
// Static site: `astro build` writes dist/, which scripts/serve-dist.mjs (or any
// static host) serves. The Python backend (foss_audit/server.py) binds
// 127.0.0.1 only; proxying the API prefix keeps the UI same-origin in dev so
// the backend needs no CORS headers. run.sh exports FOSS_AUDIT_API_PORT when
// --api-port is given.
import { execFileSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import process from "node:process";
import { URL } from "node:url";

const apiPort = process.env.FOSS_AUDIT_API_PORT ?? "5191";
const proxy = { "/api": { target: `http://127.0.0.1:${apiPort}` } };

// Stamps dist/version.txt with the short commit hash, so scripts/deploy.sh can
// prove the live UI serves this build and not a stale one.
const buildId = {
  hooks: {
    "astro:build:done": ({ dir }) => {
      let id = "unknown";
      try {
        id = execFileSync("/usr/bin/git", ["rev-parse", "--short", "HEAD"], { encoding: "utf8" }).trim();
      } catch {
        // Not a Git checkout (e.g. a tarball): leave the id unknown.
      }
      writeFileSync(new URL("version.txt", dir), `${id}\n`);
    },
  },
  name: "build-id",
};

export default defineConfig({
  // The dev toolbar injects its own scripts into every page; the e2e flows
  // assert a clean console and exact DOM.
  devToolbar: { enabled: false },
  integrations: [buildId],
  output: "static",
  server: { host: "127.0.0.1", port: 5190 },
  vite: { preview: { proxy }, server: { proxy } },
});
