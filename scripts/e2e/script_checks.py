"""Checks on the "Copy remove commands" script text (remove-script.ts output)."""

from __future__ import annotations

import re
from typing import Any

NULL_TOKEN = re.compile(r"(^|\s)null(\s|$)", re.MULTILINE)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def has_command(lines: list[str], command: str) -> bool:
    """Verbatim, or merged into one `<manager> a b c` line (remove-script.ts)."""
    if command in lines:
        return True
    prefix, _, arg = command.rpartition(" ")
    return any(line.startswith(f"{prefix} ") and arg in line[len(prefix) :].split() for line in lines)


def script_ok(script: str, ids: set[str], items: dict[str, dict[str, Any]]) -> None:
    check(script.startswith("#!/bin/bash\n"), f"script starts {script[:20]!r}")
    check(NULL_TOKEN.search(script) is None, "script contains a bare `null`")
    check(f"for {len(ids)} selected item" in script, "script header has the wrong item count")
    lines = script.splitlines()
    for item_id in sorted(ids):
        command = items[item_id]["removeCommand"]
        wanted = f"# no remove command: {item_id}" if command is None else command
        check(has_command(lines, wanted), f"script lacks {wanted!r} for {item_id}")
