## Commands

- run: `./run.sh` (API on 127.0.0.1:5191 + UI on 127.0.0.1:5190; `--build`, `--port`, `--api-port`, `--no-open`, `--install-launcher`)
- backend only: `python3 -m foss_audit.server --port 5191`
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

## Layout

- `foss_audit/`: stdlib-only Python scanner and HTTP API (`DOCS-api-contract.md`)
- `data/curated.json`: hand-verified verdicts and FOSS alternatives (fnmatch globs; `null` means no alternative)
- `src/`: React UI; `run.sh` starts both halves
