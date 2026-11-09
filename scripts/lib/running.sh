#!/bin/bash

# ============================================================================
# Detect a foss-audit instance that is already serving, decide whether it is
# up to date, and stop it when it is not. Sourced by run.sh, which supplies
# SCRIPT_DIR, PORT, API_PORT, PRODUCTION_BUILD and die().
#
# "Ours" is decided from /proc/<pid>/cmdline only, so a foreign process that
# happens to hold a port is never signalled.
# ============================================================================

# Paths the servers load: the scanner (foss_audit/, data/curated.json) and the
# UI build inputs. Untracked files count too (a new module is a code change).
readonly -a WATCHED_PATHS=(foss_audit data src package.json pnpm-lock.yaml 'astro.config.*')
readonly STOP_GRACE_TENTHS=50

# PID listening on TCP port $1 (empty when none).
listener_pid() {
    ss -ltnpH "sport = :$1" 2>/dev/null | grep -o 'pid=[0-9]*' | head -n 1 | cut -d= -f2 || true
}

proc_cmdline() {
    tr '\0' ' ' <"/proc/$1/cmdline" 2>/dev/null || true
}

is_our_api() {
    [[ "$(proc_cmdline "$1")" == *foss_audit.server* ]]
}

# The UI listener is astro itself (node), pnpm being its parent.
is_our_ui() {
    local cmd
    cmd="$(proc_cmdline "$1")"
    [[ "$cmd" == *"${SCRIPT_DIR}"* && "$cmd" == *astro* ]]
}

# Epoch seconds at which process $1 started.
proc_start() {
    local age
    age="$(ps -o etimes= -p "$1" 2>/dev/null | tr -d ' ')" || true
    [[ -n "$age" ]] || { echo 0; return; }
    echo $(( $(date +%s) - age ))
}

# Newest mtime (epoch seconds) among the watched files; 0 when none.
newest_source_mtime() {
    local newest
    # Relative paths: run.sh has cd'd to SCRIPT_DIR. stat fails for
    # tracked-but-deleted files; the rest still count.
    newest="$(git -C "$SCRIPT_DIR" ls-files -z --cached --others --exclude-standard -- "${WATCHED_PATHS[@]}" \
        | { xargs -0 -r stat -c %Y 2>/dev/null || true; } \
        | sort -n | tail -n 1)"
    echo "${newest:-0}"
}

# Does the running UI match what this invocation asked for? astro serves either
# dev or `preview`, and proxies /api to the port FOSS_AUDIT_API_PORT named.
ui_matches_request() {
    local pid="$1" cmd env_port
    cmd="$(proc_cmdline "$pid")"
    [[ "$PRODUCTION_BUILD" == true && "$cmd" != *preview* ]] && return 1
    [[ "$PRODUCTION_BUILD" != true && "$cmd" == *preview* ]] && return 1
    env_port="$(tr '\0' '\n' <"/proc/${pid}/environ" 2>/dev/null | sed -n 's/^FOSS_AUDIT_API_PORT=//p')" || true
    [[ "${env_port:-5191}" == "$API_PORT" ]]
}

# TERM the given PIDs, give the ports up to ~5 s to free, then KILL leftovers.
stop_pids() {
    local pid i
    for pid in "$@"; do kill -TERM "$pid" 2>/dev/null || true; done
    for (( i = 0; i < STOP_GRACE_TENTHS; i++ )); do
        [[ -z "$(listener_pid "$PORT")$(listener_pid "$API_PORT")" ]] && return 0
        sleep 0.1
    done
    for pid in "$@"; do kill -KILL "$pid" 2>/dev/null || true; done
    sleep 0.3
}

# Returns 0 when a fresh instance is already serving (nothing to start).
# Returns 1 when the caller should start normally: either nothing was running,
# or what ran was stale / half-running / differently configured and is now
# stopped. Dies when a port is held by something that is not ours.
reconcile_running() {
    local api ui
    api="$(listener_pid "$API_PORT")"
    ui="$(listener_pid "$PORT")"
    [[ -z "$api" ]] || is_our_api "$api" || die "port ${API_PORT} is already in use (another foss-audit?); try --api-port"
    [[ -z "$ui" ]] || is_our_ui "$ui" || die "port ${PORT} is already in use; try --port"
    [[ -n "${api}${ui}" ]] || return 1

    local newest reason=""
    newest="$(newest_source_mtime)"
    if [[ -z "$api" || -z "$ui" ]]; then
        reason="only one half was running"
    elif ! ui_matches_request "$ui"; then
        reason="it was started with different options (--build / --api-port)"
    elif (( $(proc_start "$api") < newest || $(proc_start "$ui") < newest )); then
        reason="code changed since $(date -d "@${newest}" '+%F %T')"
    elif ! curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:${PORT}/api/health"; then
        reason="it did not answer its health check"
    fi

    if [[ -z "$reason" ]]; then
        echo "foss-audit already running and up to date: http://127.0.0.1:${PORT}/"
        return 0
    fi
    echo "==> Restarting foss-audit: ${reason}"
    local -a pids=()
    [[ -z "$api" ]] || pids+=("$api")
    [[ -z "$ui" ]] || pids+=("$ui")
    stop_pids "${pids[@]}"
    return 1
}
