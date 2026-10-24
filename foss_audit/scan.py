"""Run every scanner, apply curated verdicts, return one JSON-able result.

CLI: `python -m foss_audit.scan [--summary]` prints the JSON (or just counts).
"""

from __future__ import annotations

import json
import socket
import sys
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from foss_audit import (
    scan_cache_cargo,
    scan_cache_maven,
    scan_cache_npm,
    scan_cache_pip,
    scan_cache_pub,
    scan_desktop,
    scan_docker,
    scan_games,
    scan_misc,
    scan_pacman,
    scan_python,
    scan_steam,
    scan_toolchain,
    scan_unowned,
    scan_userapp,
)
from foss_audit.curated import Curated, apply
from foss_audit.model import Item, ScanError

SCANNERS: dict[str, Callable[[], list[Item]]] = {
    "pacman": scan_pacman.scan,
    "pip-user": scan_python.scan_pip_user,
    "pipx": scan_python.scan_pipx,
    "uv-tool": scan_python.scan_uv_tools,
    "conda": scan_python.scan_conda,
    "npm-global": scan_misc.scan_npm_global,
    "cargo": scan_misc.scan_cargo,
    "flatpak": scan_misc.scan_flatpak,
    "appimage": scan_misc.scan_appimages,
    "opt": scan_misc.scan_opt,
    "local-bin": scan_misc.scan_local_bin,
    "steam": scan_steam.scan_steam,
    "wine": scan_games.scan_wine,
    "waydroid": scan_games.scan_waydroid,
    "unowned": scan_unowned.scan_unowned_bins,
    "npm-system": scan_unowned.scan_system_npm,
    "app-home": scan_unowned.scan_app_home,
    "toolchain": scan_toolchain.scan_toolchains,
    "desktop": scan_desktop.scan_desktop,
    "docker": scan_docker.scan_docker,
    "user-app": scan_userapp.scan_user_apps,
    "maven-cache": scan_cache_maven.scan_maven_cache,
    "pub-cache": scan_cache_pub.scan_pub_cache,
    "npm-cache": scan_cache_npm.scan_npm_cache,
    "cargo-cache": scan_cache_cargo.scan_cargo_cache,
    "pip-cache": scan_cache_pip.scan_pip_cache,
}


def run_scan(
    scanners: dict[str, Callable[[], list[Item]]] = SCANNERS,
) -> dict[str, Any]:
    """Scan everything; one failing source becomes an error entry, not a crash."""
    start = time.monotonic()
    items: list[Item] = []
    errors: list[ScanError] = []
    for source, scanner in scanners.items():
        try:
            items += scanner()
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            errors.append(ScanError(source=source, message=f"{type(exc).__name__}: {exc}"))
    apply(items, Curated.load())
    return {
        "generatedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "durationMs": round((time.monotonic() - start) * 1000),
        "host": socket.gethostname(),
        "items": [i.to_json() for i in items],
        "errors": [vars(e) for e in errors],
    }


def summary(result: dict[str, Any]) -> str:
    """Human-readable counts per verdict and per source."""
    items = result["items"]
    by_verdict = Counter(i["verdict"] for i in items)
    by_source = Counter(i["source"] for i in items)
    lines = [
        f"{len(items)} items in {result['durationMs']} ms",
        f"verdicts: {dict(by_verdict)}",
    ]
    lines.append(f"sources: {dict(by_source)}")
    lines += [f"error {e['source']}: {e['message']}" for e in result["errors"]]
    return "\n".join(lines)


def main(argv: list[str]) -> None:
    """Print the scan as JSON, or a summary with --summary."""

    result = run_scan()
    sys.stdout.write((summary(result) if "--summary" in argv else json.dumps(result)) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
