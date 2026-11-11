#!/bin/bash

# ============================================================================
# Deploy foss-audit for real: update the live checkout (~/src/foss-audit),
# build it, install and restart the systemd --user unit that serves it, point the
# dmenu/rofi launcher at the running UI, then health-check the live URLs.
#
#   scripts/deploy.sh
#
# Idempotent. Exits non-zero unless the API and the UI both answer and the UI
# serves the build of the checkout's HEAD (dist/version.txt).
# Env: FOSS_AUDIT_DIR (default ~/src/foss-audit), HEALTH_TIMEOUT_SEC (45).
# ============================================================================

set -euo pipefail

readonly REPO="${FOSS_AUDIT_DIR:-${HOME}/src/foss-audit}"
readonly UNIT=foss-audit.service
readonly UNIT_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
readonly LAUNCHER="${XDG_DATA_HOME:-${HOME}/.local/share}/applications/foss-audit.desktop"
readonly UI_URL="http://127.0.0.1:5190"
readonly API_URL="http://127.0.0.1:5191"
readonly HEALTH_TIMEOUT_SEC="${HEALTH_TIMEOUT_SEC:-45}"

die() {
    echo "deploy: $1" >&2
    exit 1
}

update_checkout() {
    [[ -d "${REPO}/.git" ]] || die "${REPO} is not a git checkout"
    [[ -z "$(git -C "$REPO" status --porcelain)" ]] || die "${REPO} has uncommitted changes"
    git -C "$REPO" pull --ff-only --quiet || die "git pull --ff-only failed in ${REPO} (diverged?)"
}

# Writes $2 to $1 only when it differs; returns 0 when the file changed.
write_if_changed() {
    local target="$1" content="$2"
    if [[ -f "$target" ]] && [[ "$(cat "$target")" == "$content" ]]; then
        return 1
    fi
    mkdir -p "$(dirname "$target")"
    printf '%s\n' "$content" >"$target"
}

install_unit() {
    local unit
    unit="$(sed "s|@REPO@|${REPO}|g" "${REPO}/scripts/foss-audit.service")"
    if write_if_changed "${UNIT_DIR}/${UNIT}" "$unit"; then
        systemctl --user daemon-reload
    fi
    systemctl --user enable --quiet "$UNIT"
}

# The service owns the servers now, so the launcher only opens the UI; run.sh's
# own launcher (Terminal=true, dev mode) would fight the unit for the ports.
install_launcher() {
    write_if_changed "$LAUNCHER" "[Desktop Entry]
Type=Application
Name=FOSS audit
Comment=Which installed programs are FOSS, and the FOSS alternatives for the rest
Exec=xdg-open ${UI_URL}/
Terminal=false
Categories=System;" || true
    if command -v desktop-file-validate >/dev/null 2>&1; then
        desktop-file-validate "$LAUNCHER" || die "generated ${LAUNCHER} failed validation"
    fi
}

healthy() {
    local want="$1"
    curl -fs -o /dev/null --max-time 2 "${API_URL}/api/health" \
        && curl -fs -o /dev/null --max-time 2 "${UI_URL}/api/health" \
        && [[ "$(curl -fs --max-time 2 "${UI_URL}/version.txt")" == "$want" ]] \
        && systemctl --user is-active --quiet "$UNIT"
}

wait_healthy() {
    local want deadline
    want="$(git -C "$REPO" rev-parse --short HEAD)"
    deadline=$(( SECONDS + HEALTH_TIMEOUT_SEC ))
    while (( SECONDS < deadline )); do
        if healthy "$want"; then
            echo "deploy: foss-audit ${want} live at ${UI_URL}/"
            return 0
        fi
        sleep 1
    done
    journalctl --user -u "$UNIT" -n 20 --no-pager >&2 || true
    die "health check failed after ${HEALTH_TIMEOUT_SEC}s (want build ${want} at ${UI_URL})"
}

main() {
    update_checkout
    install_unit
    install_launcher
    # Build with the old servers stopped: never rebuild a dist that is being
    # served, and the API's startup scan would starve the build of CPU.
    systemctl --user stop "$UNIT"
    nice -n 10 "${REPO}/run.sh" --build-only >/dev/null || die "build failed (run: ${REPO}/run.sh --build-only)"
    systemctl --user start "$UNIT"
    wait_healthy
}

main "$@"
