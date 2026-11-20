"""A directory that only collects separate git clones (~/.local/share/mcp-servers).

Such a directory is not one app: each clone is a different project with its own
upstream and license, so each gets its own item named `<dir>/<clone>`. The
license comes from the clone's LICENSE file (or manifest), else from the
upstream repository its `origin` remote names. kuhy's own clones are skipped.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from foss_audit.licenses import classify_text
from foss_audit.model import Item
from foss_audit.own_license import declared_license, is_kuhy_repo
from foss_audit.scan_misc import unknown
from foss_audit.upstream_license import upstream_license

MIN_CLONES = 2
REMOTE_URL = re.compile(r"^\s*url\s*=\s*(\S+)", re.MULTILINE)


def clones(top: Path) -> list[Path]:
    """The git clones directly inside `top`; empty unless there are at least two."""
    found = sorted(p for p in top.iterdir() if p.is_dir() and not p.is_symlink() and (p / ".git").is_dir())
    return found if len(found) >= MIN_CLONES else []


def remote_url(clone: Path) -> str:
    """The first remote URL in the clone's git config ("" when it has none)."""
    found = REMOTE_URL.search((clone / ".git/config").read_text(errors="replace"))
    return found[1].removesuffix(".git") if found else ""


def clone_item(top: Path, clone: Path, home: Path) -> Item:
    """One clone, licensed by its own files, else by its upstream repository."""
    name, where = f"{top.name}/{clone.name}", f"~/{clone.relative_to(home)}"
    remove = f"rm -rf {shlex.quote(str(clone))}"
    url = remote_url(clone)
    lic, checked = declared_license(clone, clone), "license file"
    if not lic and url:
        lic, checked = upstream_license(url)
    if not lic:
        return unknown(
            name,
            "user-app",
            url=url or None,
            removeCommand=remove,
            reason=f"{where}; no license file shipped; {checked}",
        )
    verdict, why = classify_text(lic)
    reason = "; ".join(r for r in (where, f"{checked}: {lic}", why if why != lic else "") if r)
    return Item(name, "user-app", verdict, license=lic, reason=reason, url=url or None, removeCommand=remove)


def group_items(top: Path, home: Path, linked: list[Path]) -> list[Item] | None:
    """Items for every clone in `top`, or None when `top` is not a group of clones.

    Clones whose files a ~/.local/bin symlink reaches belong to the local-bin scan.
    """
    found = clones(top)
    if not found:
        return None
    return [
        clone_item(top, c, home)
        for c in found
        if not is_kuhy_repo(c) and not any(t.is_relative_to(c) for t in linked)
    ]
