"""Programs no package manager accounts for: files in /usr/bin and
/usr/local/bin that no pacman package owns, `sudo npm -g` packages in
/usr/lib/node_modules, and self-updating apps under ~/.config (Discord's
Squirrel installer drops `~/.config/discord/app-<version>/`).

These are what an uninstall leaves behind (`discord.orig`, the original
launcher kept by the compulsive-opening wrapper), what an installer copies
straight into /usr/bin (Unreal Engine tools), and kuhy's own scripts
installed by copy. Own copies are traced to the tracked file they came from,
exactly like ~/.local/bin.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from foss_audit.cited_terms import cited_item, is_elf
from foss_audit.model import Item
from foss_audit.own_license import origin_of
from foss_audit.scan_misc import from_checkout, npm_items, npm_manifests, unknown
from foss_audit.scan_pacman import owned_by_pacman

BIN_ROOTS = (Path("/usr/bin"), Path("/usr/local/bin"))
SYSTEM_NPM = Path("/usr/lib/node_modules")
CONFIG = Path.home() / ".config"
# Libraries, debug symbols and build leftovers an installer drops next to its
# programs; they are parts of the program item, not programs.
NOT_PROGRAM = re.compile(r"\.(so|debug|sym|pdb|dll|target)$|\.so\.")
# Backups of a binary something replaced (wrapper .orig, hand-made .bak).
BACKUP = re.compile(r"^(?P<base>.+?)(\.orig|\.bak(-\d+)?|\.broken-[\w-]+\.bak)$")
APP_DIR = re.compile(r"^app-(?P<version>\d[\w.]*)$")


def _is_program(path: Path) -> bool:
    """An executable regular file with content (0-byte stubs run nothing)."""
    return (
        path.is_file()
        and os.access(path, os.X_OK)
        and path.stat().st_size > 0
        and not NOT_PROGRAM.search(path.name)
    )


def candidates(roots: tuple[Path, ...] | None = None) -> list[Path]:
    """Program files in the roots. A symlink to another root or to a package
    directory is left to that location's own scan; pacman resolves symlinks
    when it checks ownership, so only real files are asked about."""
    found = []
    for root in BIN_ROOTS if roots is None else roots:
        if not root.is_dir():
            continue
        for path in sorted(root.iterdir()):
            if path.is_symlink() or not _is_program(path):
                continue
            found.append(path)
    return found


def _living(base: str, roots: tuple[Path, ...]) -> bool:
    return any((r / base).exists() for r in roots)


def classify(path: Path, roots: tuple[Path, ...] | None = None) -> Item | None:
    """One unowned program; None for a backup of a program that still exists."""
    name, where = path.name, f"{path} (no package owns it)"
    backup = BACKUP.match(name)
    if backup:
        if _living(backup["base"], BIN_ROOTS if roots is None else roots):
            return None
        # The program it backed up is gone; the backup still runs it.
        name, where = backup["base"], f"{path}: backup left after {backup['base']} was removed"
    origin = origin_of(path)
    if origin is not None:
        how = "built from" if is_elf(path) else "copy of"
        item = from_checkout(name, "unowned", origin, f"{how} {origin}")
    else:
        item = cited_item(name, path, where) or unknown(
            name,
            "unowned",
            # The location goes in the note: a curated reason must not hide it.
            note=where,
            # A hand-placed script is kuhy's own; a native binary, or a backup of
            # a removed package's launcher, is someone else's.
            own=not backup and not is_elf(path),
            loose=True,
        )
        item.source = "unowned"
    item.removeCommand = f"sudo rm {path}"
    return item


def scan_unowned_bins() -> list[Item]:
    """Programs in /usr/bin and /usr/local/bin that no pacman package owns."""
    paths = candidates()
    owned = owned_by_pacman([str(p) for p in paths])
    items = [classify(p) for p in paths if str(p) not in owned]
    return [i for i in items if i is not None]


def scan_system_npm() -> list[Item]:
    """`sudo npm -g` packages: /usr/lib/node_modules entries pacman does not own."""
    if not SYSTEM_NPM.is_dir():
        return []
    manifests = npm_manifests(SYSTEM_NPM)
    owned = owned_by_pacman([str(m.parent) for m in manifests])
    stray = [m for m in manifests if str(m.parent) not in owned]
    return npm_items(stray, remove="sudo npm uninstall -g", where=f"{SYSTEM_NPM} (system npm)")


def _app_version(directory: Path) -> str | None:
    try:
        versions = [m["version"] for d in directory.iterdir() if d.is_dir() and (m := APP_DIR.match(d.name))]
    except PermissionError:
        return None
    return max(versions, key=lambda v: [int(x) if x.isdigit() else 0 for x in v.split(".")], default=None)


def scan_app_home() -> list[Item]:
    """Self-updating apps that live in ~/.config/<name>/app-<version>/."""
    if not CONFIG.is_dir():
        return []
    items = []
    for directory in sorted(d for d in CONFIG.iterdir() if d.is_dir()):
        version = _app_version(directory)
        if version is None:
            continue
        items.append(
            unknown(
                directory.name,
                "app-home",
                version=version,
                note=f"{directory}/app-{version}: self-updating install",
                removeCommand=f"rm -rf {directory}",
            )
        )
    return items
