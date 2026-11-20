"""The Go module a native binary was built from, read from its build info.

A Go linker writes the main package path and module into the `.go.buildinfo`
ELF section (`go version -m` prints it). ~/.local/bin copies of a compiled Go
program match no tracked file by name or content, but that module path names
the kuhyx checkout whose LICENSE covers them. Read in pure Python from the ELF
section table: no external tool, and only the section table plus one small
section are read, whatever the binary's size.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path
from typing import BinaryIO

from foss_audit.own_license import REPO_SLUG, checkout_for_url

SECTION = b".go.buildinfo"
MAGIC = b"\xff Go buildinf:"
# Bounds on what is read: a real table is ~30 entries of 64 bytes, a real
# buildinfo section ~500 bytes.
MAX_TABLE_BYTES = 1 << 18
MAX_SECTION_BYTES = 1 << 16
ELF64_LE = b"\x7fELF\x02\x01"
MAIN_PATH = re.compile(rb"path\t(\S+)\n")


def _read_at(fh: BinaryIO, offset: int, size: int) -> bytes:
    fh.seek(offset)
    data = fh.read(size)
    if len(data) != size:
        raise ValueError("truncated")
    return data


def _section(path: Path) -> bytes:
    """The `.go.buildinfo` section bytes of a 64-bit little-endian ELF, else b""."""
    with path.open("rb") as fh:
        head = _read_at(fh, 0, 64)
        if head[:6] != ELF64_LE:
            return b""
        (shoff,) = struct.unpack_from("<Q", head, 0x28)
        shentsize, shnum, shstrndx = struct.unpack_from("<HHH", head, 0x3A)
        if shentsize != 64 or not shstrndx < shnum or shnum * shentsize > MAX_TABLE_BYTES:
            return b""
        table = _read_at(fh, shoff, shnum * shentsize)
        rows = [struct.unpack_from("<IIQQQQ", table, i * shentsize) for i in range(shnum)]
        names_off, names_size = rows[shstrndx][4], rows[shstrndx][5]
        names = _read_at(fh, names_off, min(names_size, MAX_TABLE_BYTES))
        for row in rows:
            if names[row[0] :].split(b"\x00", 1)[0] == SECTION:
                return _read_at(fh, row[4], min(row[5], MAX_SECTION_BYTES))
    return b""


def main_path(path: Path) -> str:
    """The main package path in a Go binary's build info; "" for anything else."""
    try:
        blob = _section(path)
    except OSError, ValueError, struct.error:
        return ""
    found = MAIN_PATH.search(blob) if blob.startswith(MAGIC) else None
    return found.group(1).decode(errors="replace") if found else ""


def go_checkout(path: Path) -> tuple[str, Path] | None:
    """(module path, local checkout) for a binary built from a github.com/kuhyx module."""
    module = main_path(path)
    if not REPO_SLUG.search(module):
        return None
    checkout = checkout_for_url(module)
    return (module, checkout) if checkout else None
