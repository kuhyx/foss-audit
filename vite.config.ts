/// <reference types="vitest/config" />
import babel from "@rolldown/plugin-babel";
import react, { reactCompilerPreset } from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The Python backend (foss_audit/server.py) binds 127.0.0.1 only. Proxying the
// API prefix through Vite keeps the UI same-origin in both dev and preview, so the
// backend needs no CORS headers. run.sh exports FOSS_AUDIT_API_PORT when
// --api-port is given.
const apiPort = process.env.FOSS_AUDIT_API_PORT ?? "5191";
const proxy = { "/api": { target: `http://127.0.0.1:${apiPort}` } };

// React Compiler through Babel: the stable path in plugin-react 6. The Rust
// (oxc) port is marked experimental upstream, so it is not used here.
//
// Off under Vitest: the compiler wraps every component in memo-cache checks
// (`if ($[0] !== props) ... else reuse`), and v8 counts each as a branch of
// our source. The "reuse" arm only runs on a re-render with identical props,
// so coverage would measure the compiler rather than this code. The compiled
// bundle is exercised end to end in a real browser instead.
const compiler = process.env.VITEST === undefined ? [babel({ presets: [reactCompilerPreset()] })] : [];

const config = defineConfig({
  plugins: [react(), ...compiler],
  preview: { host: "127.0.0.1", proxy },
  server: { host: "127.0.0.1", proxy },
  test: {
    coverage: {
      exclude: [
        "src/main.tsx", // DOM bootstrap: nothing to assert that jsdom can see
        "src/test/**",
        "src/**/*.d.ts",
      ],
      include: ["src/**/*.{ts,tsx}"],
      provider: "v8",
      // 90% branch overall; the pure logic in src/lib must be fully covered.
      thresholds: {
        branches: 90,
        functions: 90,
        lines: 90,
        "src/lib/**": {
          branches: 100,
          functions: 100,
          lines: 100,
          statements: 100,
        },
        statements: 90,
      },
    },
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
    // No tests exist yet (they come after the UI is approved); without this
    // `pnpm run test` would fail on an empty suite.
    passWithNoTests: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});

export default config;
