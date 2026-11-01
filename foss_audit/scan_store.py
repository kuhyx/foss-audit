"""Reading and atomically writing a saved scan result."""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any


def load_scan_file(path: Path) -> dict[str, Any]:
    result = json.loads(path.read_text())
    if not isinstance(result, dict) or "items" not in result:
        raise ValueError("not a foss_audit.scan result (no top-level `items`)")
    return result


def load_saved(path: Path) -> dict[str, Any] | None:
    try:
        return load_scan_file(path)
    except OSError, ValueError:
        return None


def save_atomic(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(result))
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise
