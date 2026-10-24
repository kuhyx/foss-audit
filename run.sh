#!/bin/bash

# ============================================================================
# foss-audit: start the scanner API and the UI, then open the UI in a browser.
#
#   ./run.sh                     install if needed, serve dev UI, open browser
#   ./run.sh --build             serve the production build (vite preview)
#   ./run.sh --port 5190         UI port (default 5190)
#   ./run.sh --api-port 5191     backend port (default 5191)
#   ./run.sh --scan-file PATH    serve a saved `python -m foss_audit.scan` output
#   ./run.sh --no-open           do not launch a browser (headless use)
#   ./run.sh --install-launcher  add foss-audit to dmenu/rofi, then exit
#
# Both servers bind 127.0.0.1 only; Ctrl-C (or closing the terminal) stops both.
# If foss-audit is already running and newer than its sources, run.sh just opens
# it; if the code changed since it started, it is restarted. Foreign processes
# on the ports are never touched.
# ============================================================================

set -euo pipefail

# Assigned separately from `readonly` so a failure in the subshell is not masked
# by readonly's own exit status (shellcheck SC2155).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly REQUIRED_NODE_MAJOR=24
readonly LAUNCHER_DIR="${XDG_DATA_HOME:-${HOME}/.local/share}/applications"

# shellcheck source=scripts/lib/toolchain.sh
. "${SCRIPT_DIR}/scripts/lib/toolchain.sh"
# shellcheck source=scripts/lib/running.sh
. "${SCRIPT_DIR}/scripts/lib/running.sh"

PORT=5190
API_PORT=5191
PRODUCTION_BUILD=false
OPEN_BROWSER=true
SCAN_FILE=""
API_PID=""
UI_PID=""
COREPACK_SHIM_DIR=""

# Each server is started under `setsid`, so its PID is also its process
# group id. Signalling the group (`-pid`) reaches the real server too: the UI
# PID is pnpm, and vite is pnpm's child, which a plain `kill pid` orphans.
#
# Called only from cleanup, which runs from the traps below; shellcheck cannot
# follow a trap string, hence the SC2329 ("never invoked") opt-outs.
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
    if [[ -n "${UI_PID}${API_PID}" ]]; then
        echo ""
        echo "Stopping servers..."
    fi
    stop_group "$UI_PID"
    stop_group "$API_PID"
    if [[ -n "$COREPACK_SHIM_DIR" && -d "$COREPACK_SHIM_DIR" ]]; then
        rm -rf "$COREPACK_SHIM_DIR"
    fi
}

# Signals just exit; the EXIT trap does the stopping, exactly once. HUP is
# what closing the launcher's terminal window sends.
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

usage() {
    sed -n '4,17p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
}

die() {
    echo "Error: $1" >&2
    exit 1
}

# --- launcher -----------------------------------------------------------------

install_launcher() {
    local target="${LAUNCHER_DIR}/foss-audit.desktop"
    mkdir -p "$LAUNCHER_DIR"
    # Terminal=true on purpose: the servers live as long as this script, and
    # the terminal window is how you stop them (close it, or Ctrl-C). Without
    # one, a second launch would fail on the occupied ports with no visible
    # error and no obvious way to stop the first.
    cat >"$target" <<EOF
[Desktop Entry]
Type=Application
Name=FOSS audit
Comment=Which installed programs are FOSS, and the FOSS alternatives for the rest
Exec="${SCRIPT_DIR}/run.sh"
Path=${SCRIPT_DIR}
Terminal=true
Categories=System;
EOF
    if command -v desktop-file-validate >/dev/null 2>&1; then
        desktop-file-validate "$target" || die "generated ${target} failed validation"
    fi
    echo "==> Installed launcher: ${target}"
}

# --- serving ------------------------------------------------------------------

port_in_use() {
    curl -s -o /dev/null --max-time 1 "http://127.0.0.1:$1/"
}

wait_for() {
    local url="$1" name="$2" attempt=0
    echo -n "==> Waiting for ${name}"
    while (( attempt < 60 )); do
        if curl -sf -o /dev/null --max-time 2 "$url"; then
            echo " ready"
            return 0
        fi
        echo -n "."
        sleep 0.5
        # An assignment, not `(( attempt++ ))`, which returns 1 on zero and
        # trips `set -e` on the first iteration.
        attempt=$(( attempt + 1 ))
    done
    echo ""
    die "${name} did not come up at ${url}"
}

start_api() {
    port_in_use "$API_PORT" && die "port ${API_PORT} is already in use (another foss-audit?); try --api-port"
    command -v python3 >/dev/null 2>&1 || die "python3 not found"
    local scan_args=()
    [[ -z "$SCAN_FILE" ]] || scan_args=(--scan-file "$SCAN_FILE")
    setsid python3 -m foss_audit.server --port "$API_PORT" "${scan_args[@]}" &
    API_PID=$!
    wait_for "http://127.0.0.1:${API_PORT}/api/health" "scanner API"
}

start_ui() {
    port_in_use "$PORT" && die "port ${PORT} is already in use; try --port"
    export FOSS_AUDIT_API_PORT="$API_PORT"
    if [[ "$PRODUCTION_BUILD" == true ]]; then
        echo "==> Building for production"
        pnpm run build
        setsid pnpm exec vite preview --host 127.0.0.1 --port "$PORT" --strictPort &
    else
        setsid pnpm exec vite --host 127.0.0.1 --port "$PORT" --strictPort &
    fi
    UI_PID=$!
    # Health through Vite's proxy: proves the UI server AND the /api wiring.
    wait_for "http://127.0.0.1:${PORT}/api/health" "UI (and its /api proxy)"
}

open_browser() {
    local url="$1"
    [[ "$OPEN_BROWSER" == true ]] || return 0
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1 &
    else
        echo "    (no xdg-open; open ${url} yourself)"
    fi
}

serve() {
    local url="http://127.0.0.1:${PORT}/"
    start_api
    start_ui

    cat <<EOF

============================================================================
  FOSS audit is running at ${url}
  (scanner API on 127.0.0.1:${API_PORT})

    ${url}?view=wins                    easy wins
    ${url}?view=table&v=nonfree&sort=name   non-free, by name

  Keys:  /  search    ?  help    Esc  close
  Ctrl-C to stop both servers.
============================================================================

EOF

    open_browser "$url"
    # Return as soon as EITHER server exits, so the trap stops the other one
    # instead of leaving a half-running app behind.
    local status=0
    wait -n "$API_PID" "$UI_PID" || status=$?
    die "a server exited (status ${status}); stopping the other"
}

main() {
    cd "$SCRIPT_DIR"
    # A fresh instance is reused; a stale or half-running one is stopped first.
    if reconcile_running; then
        open_browser "http://127.0.0.1:${PORT}/"
        exit 0
    fi
    check_node
    setup_pnpm
    install_dependencies
    serve
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --build) PRODUCTION_BUILD=true; shift ;;
        --no-open) OPEN_BROWSER=false; shift ;;
        --port)
            [[ "${2:-}" =~ ^[0-9]+$ ]] || die "--port needs a number"
            PORT="$2"; shift 2 ;;
        --api-port)
            [[ "${2:-}" =~ ^[0-9]+$ ]] || die "--api-port needs a number"
            API_PORT="$2"; shift 2 ;;
        --scan-file)
            [[ -r "${2:-}" ]] || die "--scan-file needs a readable file"
            SCAN_FILE="$(realpath "$2")"; shift 2 ;;
        --install-launcher) install_launcher; exit 0 ;;
        -h|--help) usage ;;
        *) die "unknown option: $1 (try --help)" ;;
    esac
done

main
