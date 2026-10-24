#!/bin/bash

# ============================================================================
# E2E: the all-items multi-select, on a saved real scan, in headless Chromium.
#
#   scripts/e2e_selection.sh [scan.json]     default /tmp/fa_scan.json
#
# Make the inputs first, each its own (slow) step:
#   .venv/bin/python -m foss_audit.scan > /tmp/fa_scan.json    (~45 s)
#   pnpm run build                                             (dist/)
#
# Serves the scan file through the real backend (--scan-file, no live scan)
# and dist/ through `vite preview` with its /api proxy, on ports of its own
# (E2E_API_PORT / E2E_UI_PORT, default 5291 / 5290), then drives the UI with
# scripts/e2e/selection_flow.py. Exit 0 = every step passed. Screenshots:
# /tmp/fa-e2e-table.png, /tmp/fa-e2e-bar.png (and /tmp/fa-e2e-fail.png).
# Nothing on the clipboard is ever run.
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
REPO_DIR="$(dirname "$SCRIPT_DIR")"
readonly REPO_DIR
readonly SCAN_FILE="${1:-/tmp/fa_scan.json}"
readonly API_PORT="${E2E_API_PORT:-5291}"
readonly UI_PORT="${E2E_UI_PORT:-5290}"
readonly SHOT_DIR="${E2E_SHOT_DIR:-/tmp}"
STARTED_NS="$(date +%s%N)"
readonly STARTED_NS

API_PID=""
UI_PID=""

die() {
    echo "Error: $1" >&2
    exit 1
}

elapsed() {
    local now
    now="$(date +%s%N)"
    printf '%d.%01d' $(((now - STARTED_NS) / 1000000000)) $(((now - STARTED_NS) / 100000000 % 10))
}

# Both servers run under setsid, so the PID is a process group: signalling
# the group also reaches vite under node. Called from the EXIT trap only.
# shellcheck disable=SC2317,SC2329
stop_group() {
    local pid="$1"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        kill -TERM -- "-${pid}" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
    fi
}

# shellcheck disable=SC2317,SC2329
cleanup() {
    stop_group "$UI_PID"
    stop_group "$API_PID"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

port_free() {
    ! curl -s -o /dev/null --max-time 1 "http://127.0.0.1:$1/"
}

wait_for() {
    local url="$1" name="$2" attempt=0
    while ((attempt < 100)); do
        curl -sf -o /dev/null --max-time 2 "$url" && return 0
        kill -0 "$3" 2>/dev/null || die "${name} exited before it came up"
        sleep 0.1
        attempt=$((attempt + 1))
    done
    die "${name} did not come up at ${url}"
}

preflight() {
    [[ -r "$SCAN_FILE" ]] || die "no scan file ${SCAN_FILE}; make one: .venv/bin/python -m foss_audit.scan > ${SCAN_FILE}"
    [[ -f "${REPO_DIR}/dist/index.html" ]] || die "no dist/; run: pnpm run build"
    local stale
    stale="$(find "${REPO_DIR}/src" "${REPO_DIR}/index.html" -newer "${REPO_DIR}/dist/index.html" -print -quit)"
    [[ -z "$stale" ]] || die "dist/ is older than ${stale#"${REPO_DIR}/"}; run: pnpm run build"
    [[ -x "${REPO_DIR}/node_modules/.bin/vite" ]] || die "no node_modules; run: pnpm install"
    port_free "$API_PORT" || die "port ${API_PORT} in use; set E2E_API_PORT"
    port_free "$UI_PORT" || die "port ${UI_PORT} in use; set E2E_UI_PORT"
}

start_servers() {
    setsid python3 -m foss_audit.server --port "$API_PORT" --scan-file "$SCAN_FILE" &
    API_PID=$!
    FOSS_AUDIT_API_PORT="$API_PORT" setsid "${REPO_DIR}/node_modules/.bin/vite" preview \
        --host 127.0.0.1 --port "$UI_PORT" --strictPort >/dev/null &
    UI_PID=$!
    wait_for "http://127.0.0.1:${API_PORT}/api/health" "backend" "$API_PID"
    # Through vite's proxy: proves the preview server AND its /api wiring.
    wait_for "http://127.0.0.1:${UI_PORT}/api/health" "vite preview" "$UI_PID"
    echo "==> servers up in $(elapsed) s (scan: ${SCAN_FILE})"
}

main() {
    cd "$REPO_DIR"
    preflight
    start_servers
    local status=0
    python3 "${SCRIPT_DIR}/e2e/selection_flow.py" "http://127.0.0.1:${UI_PORT}" "$SCAN_FILE" \
        "${SHOT_DIR}/fa-e2e-table.png" "${SHOT_DIR}/fa-e2e-bar.png" "${SHOT_DIR}/fa-e2e-fail.png" || status=$?
    if ((status == 0)); then
        echo "PASS e2e_selection in $(elapsed) s"
    else
        echo "FAIL e2e_selection (exit ${status}) in $(elapsed) s"
    fi
    return "$status"
}

main
