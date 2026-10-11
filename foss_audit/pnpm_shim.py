"""Trace pnpm's generated ~/.local/bin shims to the package they launch.

`pnpm add -g` writes a sh shim whose exec lines look like
`exec node "$basedir_abs/../share/pnpm/global/v11/<hash>/node_modules/@scope/pkg/dist/cli.js"`.
The shim itself carries no license; the package it runs does.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from foss_audit.licenses import classify_text
from foss_audit.model import Item
from foss_audit.own_license import license_for_path

SHIM_READ_LIMIT = 65536
EXEC_TARGET = re.compile(r'^\s*exec\s[^\n"]*"\$basedir\w*/([^"\n]*node_modules/[^"\n]*)"', re.MULTILINE)


def shim_target(shim: Path) -> Path | None:
    """The node_modules file a pnpm shim execs, resolved against the shim's directory."""
    with shim.open("rb") as fh:
        text = fh.read(SHIM_READ_LIMIT).decode(errors="replace")
    match = EXEC_TARGET.search(text)
    return None if match is None else Path(os.path.normpath(shim.parent / match.group(1)))


def package_dir(target: Path) -> Path:
    """The package root of a file under node_modules (two segments for @scope/name)."""
    parts = target.parts
    start = len(parts) - 1 - parts[::-1].index("node_modules")
    depth = 2 if parts[start + 1].startswith("@") else 1
    return Path(*parts[: start + 1 + depth])


def pnpm_item(entry: Path, shim: Path) -> Item | None:
    """The ~/.local/bin Item for a pnpm shim, licensed by the package it launches.

    Never own (a global install is someone else's package) and never loose (the
    shim is generated, not hand-placed); None when `shim` is not a pnpm shim.
    """
    target = shim_target(shim)
    if target is None:
        return None
    lic, _ = license_for_path(target)
    verdict, reason = classify_text(lic)
    how = f"pnpm shim -> {package_dir(target)}"
    return Item(
        name=entry.name,
        source="local-bin",
        verdict=verdict,
        license=lic,
        reason=f"{how}; {reason}" if reason else how,
    )
