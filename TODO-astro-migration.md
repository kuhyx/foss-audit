# Migrate the foss-audit UI to Astro (no React)

## what
The audit UI is a table, summary and easy-wins views over the scanner API on
127.0.0.1:5191. It becomes Astro 7 static output. One page's script fetches
`/api` and renders with custom elements. The `src/site` AgentReady generator
becomes Astro endpoints. The Python scanner (`foss_audit/`) is untouched.

## steps
1. Do `~/src/utils/web_ui/TODO-astro-port.md` first. Then bump `@kuhyx/web-ui`
   from `web_ui-v0.4.0` to the new tag (`tokens.css`).
2. Pages:
   - `src/pages/index.astro`. Prerender the homepage content now injected by
     `injectHome` (no-JS content). The table enhances it.
   - `src/pages/404.astro`.
   - The views (`view-tabs`: table, summary, easy-wins) stay in-page and are
     kept in the URL by `lib/url-state.ts`.
3. AgentReady. Port `src/site/*` (`build.ts`, `discovery.ts`,
   `render-markdown.ts`, `content.ts` and `config.ts` with `SITE_URL`) into
   endpoints:
   `src/pages/robots.txt.ts`, `sitemap.xml.ts`, `llms.txt.ts`,
   `.well-known/ai-catalog.json.ts` and `[...path].md.ts`.
   Delete `vite-plugin.ts`, `render-html.ts` and `style.ts` when the endpoints
   match the old output.
4. Rewrite the 16 React files:
   - `app.tsx` and `app-header` become `index.astro` plus `layouts/Base.astro`.
   - `items-table`, `columns`, `check-cells` and `verdict-badge` become an
     `<items-table>` element (sort, filter, select), using `lib/filter.ts`
     and `lib/selection.ts`.
   - `filter-bar`, `selection-bar` and `copy-button` are element-backed
     controls. Copy uses `navigator.clipboard`.
   - `summary-view`, `easy-wins` and `source-chart` become `.astro` shells
     with TS renderers. The chart becomes an SVG builder.
   - `detail-panel` and `help-overlay` use `<dialog>` with TS.
     `error-banner` becomes `.astro` with a TS fill-in.
   - The 5 hooks (`use-scan`, `use-selection`, `use-url-state`, `use-keyboard`,
     `use-element-width`) become plain modules. `use-element-width` becomes a
     `ResizeObserver` helper.
5. Dev and preview proxy. Move `/api` to `vite.server.proxy` in
   `astro.config.mjs`. `astro preview` may not apply Vite's preview proxy, so
   check it. If it does not, `run.sh --build` serves `dist/` some other way
   that keeps `/api` same-origin. Ask kuhy which way.
6. Dependencies, exact pins via pnpm:
   - Add `astro@7.4.4`, `@astrojs/check@0.9.12`, `eslint-plugin-astro@3.2.1`
     and `@testing-library/dom`.
   - Remove `react`, `react-dom`, `@vitejs/plugin-react`,
     `@rolldown/plugin-babel`, `babel-plugin-react-compiler` and
     `@testing-library/react`.
   - Drop direct `vite` unless step 5 needs it.
7. Tests. Use vitest 5.0.5 with `getViteConfig()`:
   - `src/lib/*` tests and `__snapshots__` stay.
   - Elements are tested in jsdom against `fixtures/`.
   - The Container API renders the pages. Coverage is scoped to `src/**/*.ts`.

## done
Run from the repo root:
`pnpm install --frozen-lockfile && pnpm exec astro check && pnpm test && pnpm build && ~/src/utils/agent_ready/check.sh dist dist`
Then:
`! grep -q '"react"' package.json && ! grep -qE '"(react-dom|@vitejs/plugin-react)"' package.json && ! find src -name '*.tsx' | grep -q .`
Both exit 0. Also: `.venv/bin/python -m pytest -q` passes, and the headless
e2e `scripts/e2e_selection.sh /tmp/fa_scan.json` passes after `pnpm run build`.
Port its selectors if they change.

## verify
The public host `https://foss-audit.kuhy.duckdns.org/` (`SITE_URL`) is not
live. A curl returned 000 on 2026-11-01. Verify with `./run.sh --build`, which
puts the UI on 127.0.0.1:5190 and the API on 5191, in a headless chromium:
- A scan loads.
- The table sorts and filters.
- Selection builds a prompt.
- Summary and easy-wins render.
- There are no console errors.

## read first
- `~/src/utils/web_ui/TODO-astro-port.md` (do it first)
- `src/site/vite-plugin.ts`, `src/site/build.ts`, `vite.config.ts`, `run.sh`
- `DOCS-api-contract.md`, `src/app.tsx`

REMOVE ME AFTER FINISH
