#!/bin/bash
# shellcheck shell=bash
#
# Toolchain helpers for run.sh: find a usable node, and run the pinned pnpm
# through a corepack shim. Sourced, not executed; copied from
# awesome-mcp-explorer's run.sh and kept verbatim in behaviour.
#
# Expects from the caller: REQUIRED_NODE_MAJOR, COREPACK_SHIM_DIR (assigned
# here; the caller's cleanup removes it) and a `die` function.

# --- node (same discovery as awesome-mcp-explorer's run.sh) -------------------
#
# A too-old `node` on PATH is the normal case, not the broken one: nvm pins one
# version per shell. Look at every node on the box first; install only when
# none of them qualifies.

node_major_of() {
    local binary="$1"
    [[ -x "$binary" ]] || { echo 0; return; }
    "$binary" -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0
}

list_node_candidates() {
    local bin
    for bin in "${NVM_DIR:-${HOME}/.nvm}/versions/node"/*/bin \
               "${HOME}/.local/share/fnm/node-versions"/*/installation/bin; do
        [[ -x "${bin}/node" ]] && printf '%s\n' "${bin}/node"
    done | sort -Vr

    command -v node 2>/dev/null || true
    printf '%s\n' /usr/local/bin/node /usr/bin/node
}

find_usable_node() {
    local candidate
    while IFS= read -r candidate; do
        if (( $(node_major_of "$candidate") >= REQUIRED_NODE_MAJOR )); then
            printf '%s\n' "$candidate"
            return 0
        fi
    done < <(list_node_candidates)
    return 1
}

use_node() {
    local binary="$1"
    PATH="$(dirname "$binary"):${PATH}"
    export PATH
    hash -r 2>/dev/null || true
    echo "==> Using node $("$binary" -v) — ${binary}"
}

install_node_via_nvm() {
    local nvm_sh="${NVM_DIR:-${HOME}/.nvm}/nvm.sh"
    [[ -s "$nvm_sh" ]] || die "no node >= ${REQUIRED_NODE_MAJOR} and no nvm to install one with. Install nvm or run: sudo pacman -S nodejs"

    echo "==> No node >= ${REQUIRED_NODE_MAJOR} found; installing the latest LTS via nvm"
    # nvm is a shell function and reads variables it does not define.
    set +u
    # shellcheck source=/dev/null
    . "$nvm_sh"
    nvm install --lts
    set -u
}

check_node() {
    local binary
    if binary="$(find_usable_node)"; then
        use_node "$binary"
        return
    fi
    install_node_via_nvm
    binary="$(find_usable_node)" \
        || die "nvm install --lts finished but still no node >= ${REQUIRED_NODE_MAJOR}"
    use_node "$binary"
}

# --- pnpm via corepack ---------------------------------------------------------
#
# pnpm is pinned by package.json's `packageManager` and run through a
# run-scoped corepack shim, so a wrong-major pnpm earlier on PATH can never
# touch node_modules (ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY).

setup_pnpm() {
    command -v corepack >/dev/null 2>&1 \
        || die "corepack not found; it ships with Node >= ${REQUIRED_NODE_MAJOR}"
    COREPACK_SHIM_DIR="$(mktemp -d)"
    corepack enable --install-directory "$COREPACK_SHIM_DIR" pnpm \
        || die "could not enable pnpm via corepack"
    PATH="${COREPACK_SHIM_DIR}:${PATH}"
    export PATH
    hash -r 2>/dev/null || true
    export COREPACK_ENABLE_DOWNLOAD_PROMPT=0
    corepack install >/dev/null 2>&1 || true
    echo "==> Using pnpm $(pnpm --version) (pinned in package.json)"
}

install_dependencies() {
    echo "==> Installing dependencies"
    pnpm install --prefer-offline
}
