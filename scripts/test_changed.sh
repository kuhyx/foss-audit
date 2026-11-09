#!/bin/bash

# ============================================================================
# Run only the tests related to files changed vs HEAD (staged, unstaged and
# untracked). Two halves: Python backend changes run the pytest suite (whole
# suite, it takes under a second); TS changes run `vitest related`. Falls back
# to the full frontend suite when a change cannot be mapped to tests.
# ============================================================================

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
CHANGED=()
while IFS= read -r f; do
    [[ -n "$f" && -e "$f" ]] && CHANGED+=("$f")
done < <({ git diff --name-only HEAD 2>/dev/null || true; git ls-files --others --exclude-standard; } | sort -u)

full=0
python=0
src=()
for f in "${CHANGED[@]}"; do
    case "$f" in
        package.json | pnpm-lock.yaml) full=1 ;;
        *.ts | *.astro | *.js | *.mjs) src+=("$f") ;;
        *.py | pyproject.toml | data/curated.json) python=1 ;;
    esac
done

if [[ $full -eq 0 && $python -eq 0 && ${#src[@]} -eq 0 ]]; then
    echo "no testable changes vs HEAD: nothing to test"
    exit 0
fi

status=0
if [[ $python -eq 1 ]]; then
    .venv/bin/python -m pytest -q --no-cov -p no:cacheprovider || status=$?
fi
if [[ $full -eq 1 ]]; then
    pnpm test --silent || status=$?
elif [[ ${#src[@]} -gt 0 ]]; then
    pnpm exec vitest related --run --reporter=dot "${src[@]}" || status=$?
fi
exit "$status"
