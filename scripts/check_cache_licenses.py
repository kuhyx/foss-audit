#!/usr/bin/env python3
"""Real-machine gate for the package-cache scanners: every package has a license.

Runs each cache scanner against this machine's caches and prints, per source,
the package count, verdict counts, seconds taken and every package whose
license is still unknown: an unrecognised license string, a failed lookup, or
a blank license whose reason does not list where the scanner looked. A
package verified to carry no license anywhere ("no license ...; checked ...")
is a finding, not an unknown: it is listed apart as `unlicensed`. Exit 1 when
a scanner is missing or fails, or when any unknown remains.

Usage: .venv/bin/python scripts/check_cache_licenses.py [--list N]
"""

from __future__ import annotations

import importlib
import sys
import time
from collections import Counter

from foss_audit.model import NO_LICENSE

# Source -> "module:function" of its scanner.
SCANNERS = {
    "maven-cache": "foss_audit.scan_cache_maven:scan_maven_cache",
    "pub-cache": "foss_audit.scan_cache_pub:scan_pub_cache",
    "npm-cache": "foss_audit.scan_cache_npm:scan_npm_cache",
    "cargo-cache": "foss_audit.scan_cache_cargo:scan_cargo_cache",
    "pip-cache": "foss_audit.scan_cache_pip:scan_pip_cache",
}
UNKNOWN_REASONS = ("unrecognised license", "license fetch failed")


def main(argv: list[str]) -> int:
    """Run every cache scanner; non-zero unless all ran and none left an unknown."""
    show = int(argv[argv.index("--list") + 1]) if "--list" in argv else 10
    failed = 0
    for source, target in SCANNERS.items():
        module, func = target.split(":")
        start = time.monotonic()
        try:
            items = getattr(importlib.import_module(module), func)()
        except (ImportError, AttributeError, OSError, RuntimeError, ValueError, KeyError) as exc:
            sys.stdout.write(f"{source}: FAIL {type(exc).__name__}: {exc}\n")
            failed += 1
            continue
        took = time.monotonic() - start
        # Any version (the reason may carry a "<version>: " prefix) proven to
        # declare no license anywhere, with the places checked.
        unlicensed = [i for i in items if f"{NO_LICENSE}; checked " in i.reason]
        unknown = [
            i
            for i in items
            # A non-newest version's reason is prefixed "<version>: ".
            if any(r in i.reason for r in UNKNOWN_REASONS)
            or "fetch failed" in i.reason
            or ((NO_LICENSE in i.reason or not i.license.strip()) and i not in unlicensed)
        ]
        verdicts = dict(Counter(i.verdict for i in items))
        sys.stdout.write(
            f"{source}: {len(items)} packages {verdicts} {took:.1f}s"
            f" unknown={len(unknown)} unlicensed={len(unlicensed)}\n"
        )
        for mark, group in (("?", unknown), ("-", unlicensed)):
            for item in group[:show]:
                sys.stdout.write(f"  {mark} {item.name} {item.version} | {item.license!r} | {item.reason}\n")
        failed += bool(unknown)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
