"""Chrome/Chromium web-app launchers (`chrome-<appid>-Default.desktop`).

Such a launcher is a bookmark: `Exec=<browser> --app-id=<id>` holds no program
of its own. When the browser binary is gone (a removed wrapper) the entry is a
stale shortcut, so it must not read "Non-free"; it is reported with the
existing dead-launcher flag and a verdict that does not ask for an alternative.
"""

from __future__ import annotations

import re
from pathlib import Path

from foss_audit.model import Item
from foss_audit.remove_cmd import quote
from foss_audit.scan_misc import unknown

APP_ID = re.compile(r"(?:^|\s)--app-id=[a-p]{32}\b")


def _is_web_app(exec_line: str) -> bool:
    """Whether an Exec line opens a browser web app by its extension id."""
    return bool(APP_ID.search(exec_line))


def dangling_item(name: str, launcher: Path, exec_line: str, command: str) -> Item:
    """Item for a launcher whose target is gone; removing the .desktop file fixes it."""
    if not _is_web_app(exec_line):
        return unknown(
            name,
            "desktop",
            note=f"launcher without target: {command}",
            dangling=True,
            removeCommand=f"rm {quote(launcher)}",
        )
    return Item(
        name=name,
        source="desktop",
        verdict="foss",
        note=f"stale web-app launcher, browser missing: {command}",
        dangling=True,
        removeCommand=f"rm {quote(launcher)}",
    )
