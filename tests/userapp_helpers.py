"""Shared fixtures-free helpers for the user-app scanner tests."""

from __future__ import annotations

from pathlib import Path

from foss_audit.model import Item

ELF = b"\x7fELF" + b"\0" * 12
MIT = "MIT License\n\nPermission is hereby granted, free of charge, to any person...\n"
GPL2 = "The GNU General Public License (GPL)\n\nVersion 2, June 1991\n"


def write(path: Path, data: bytes | str = ELF, mode: int = 0o755) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data)
    path.chmod(mode)
    return path


def by_name(items: list[Item]) -> dict[str, Item]:
    return {i.name: i for i in items}
