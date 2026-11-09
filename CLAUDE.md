## Commands

- run: `./run.sh` (API on 127.0.0.1:5191 + UI on 127.0.0.1:5190; `--build`, `--port`, `--api-port`, `--scan-file`, `--no-open`, `--install-launcher`)
- backend only: `python3 -m foss_audit.server --port 5191` (`--scan-file PATH` serves a saved scan, no live scan)
- build: `pnpm run build`
- lint: `pnpm run lint`
- test: `pnpm run test`
- test-changed: `scripts/test_changed.sh`
- coverage: `pnpm run coverage --coverage.reporter=lcov --coverage.reporter=text-summary`
- coverage-gaps: `coverage-gaps coverage/lcov.info`
- dependency freshness: `scripts/check_dependency_freshness.sh package.json`
- backend setup: `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`
- backend test: `.venv/bin/python -m pytest -q` (100% branch gate)
- backend lint: `.venv/bin/ruff check foss_audit tests && .venv/bin/mypy`
- one-shot scan: `.venv/bin/python -m foss_audit.scan --summary`
- load time: `scripts/e2e/load_time.py warm 'http://127.0.0.1:5190/?view=table'` (median of 5 fresh-browser loads, API on a saved scan) or `cold <ui-url> <shot-dir> 2 8`
- e2e: `scripts/e2e_selection.sh /tmp/fa_scan.json` (multi-select flow in headless Chromium, ~4 s; first, as separate calls: `.venv/bin/python -m foss_audit.scan > /tmp/fa_scan.json` and `pnpm run build`)

## Layout

- `foss_audit/`: stdlib-only Python scanner and HTTP API (`DOCS-api-contract.md`)
- `data/curated.json`: hand-verified verdicts and FOSS alternatives (fnmatch globs; `null` means no alternative)
- `src/`: Astro UI, custom elements (`DOCS-ui-contract.md`); `run.sh` starts both halves
