import { defineConfig } from "astro/config";
// Static site: `astro build` writes dist/, which scripts/serve-dist.mjs (or any
// static host) serves. The Python backend (foss_audit/server.py) binds
// 127.0.0.1 only; proxying the API prefix keeps the UI same-origin in dev so
// the backend needs no CORS headers. run.sh exports FOSS_AUDIT_API_PORT when
// --api-port is given.
import process from "node:process";

const apiPort = process.env.FOSS_AUDIT_API_PORT ?? "5191";
const proxy = { "/api": { target: `http://127.0.0.1:${apiPort}` } };

export default defineConfig({
  // The dev toolbar injects its own scripts into every page; the e2e flows
  // assert a clean console and exact DOM.
  devToolbar: { enabled: false },
  output: "static",
  server: { host: "127.0.0.1", port: 5190 },
  vite: { preview: { proxy }, server: { proxy } },
});
