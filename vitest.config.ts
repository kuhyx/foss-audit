/// <reference types="vitest/config" />
import { getViteConfig } from "astro/config";

// getViteConfig() runs Astro's Vite plugins, so `.astro` and `.ts` imports
// resolve in tests exactly as in the build.
export default getViteConfig({
  test: {
    coverage: {
      exclude: [
        "src/client/main.ts", // DOM bootstrap: nothing to assert that jsdom can see
        "src/test/**",
        "src/**/*.d.ts",
      ],
      include: ["src/**/*.ts"],
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
    // `.tsx` tests are React-era: not matched by `include` until each widget is ported.
    exclude: ["node_modules"],
    globals: true,
    include: ["src/**/*.test.ts"],
    passWithNoTests: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
