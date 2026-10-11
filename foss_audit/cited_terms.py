"""Native binaries that name their own proprietary terms (claude's binary says
it is "a Beta product per Anthropic's Commercial Terms of Service")."""

from __future__ import annotations

import mmap
from pathlib import Path

from foss_audit.model import Item

# Proprietary terms a native binary names itself (claude: "... a Beta product
# per Anthropic's Commercial Terms of Service"); first match wins.
CITED_TERMS = ((b"Anthropic's Commercial Terms", "LicenseRef-Anthropic-Commercial-Terms"),)


def is_elf(path: Path) -> bool:
    with path.open("rb") as fh:
        return fh.read(4) == b"\x7fELF"


def cited_terms(path: Path) -> str:
    """LicenseRef of the terms an ELF binary cites, "" when it names none.

    mmap, not read(): the claude binary is ~250 MB.
    """
    if not is_elf(path):
        return ""
    with path.open("rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as data:
        return next((ref for marker, ref in CITED_TERMS if data.find(marker) >= 0), "")


def cited_item(name: str, target: Path, link: str) -> Item | None:
    """A nonfree ~/.local/bin binary licensed by the terms it cites, else None."""
    terms = cited_terms(target) if target.is_file() else ""
    if not terms:
        return None
    return Item(
        name=name,
        source="local-bin",
        verdict="nonfree",
        license=terms,
        reason=f"{link}; binary cites {terms.removeprefix('LicenseRef-')}",
    )
