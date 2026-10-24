"""Shell-safe building blocks for the remove commands scanners attach to items.

The UI only copies these commands, so they must paste into bash/zsh as-is:
paths are quoted, but a leading `~/` stays outside the quotes so it still expands.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from foss_audit.model import Item


def shell_path(path: Path, home: Path) -> str:
    """`path` for a shell command: `~/<quoted rest>` below `home`, else fully quoted."""
    if path.is_relative_to(home) and path != home:
        return "~/" + shlex.quote(str(path.relative_to(home)))
    return shlex.quote(str(path))


def quote(path: Path) -> str:
    """Single-quote a path for a copy-pasteable shell command."""
    return "'" + str(path).replace("'", "'\\''") + "'"


def sudo_for(path: Path) -> str:
    """ "sudo " when another user (root, for most of /opt) owns `path`, else ""."""
    return "" if path.stat().st_uid == os.getuid() else "sudo "


def module_name(package: Path) -> str:
    """The npm name of a package dir under node_modules (`@scope/name` or `name`)."""
    scope = package.parent.name
    return f"{scope}/{package.name}" if scope.startswith("@") else package.name


def removing(item: Item, command: str, via: str = "") -> Item:
    """`item` with its remove command and the short why behind its shape."""
    item.removeCommand, item.removeVia = command, via
    return item
