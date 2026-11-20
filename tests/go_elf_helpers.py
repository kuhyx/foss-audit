"""Tiny ELF64 files with (or without) the section a Go linker writes its build info to."""

from __future__ import annotations

import struct
from pathlib import Path

MAGIC = b"\xff Go buildinf:"
SENTINEL = b"\x00" * 16


def varint(n: int) -> bytes:
    out = bytearray()
    while n >= 0x80:
        out.append(n & 0x7F | 0x80)
        n >>= 7
    return bytes([*out, n])


def buildinfo(module: str, version: str = "v0.0.0-20261120173713-70bd45b47c3c") -> bytes:
    """The inline-string `.go.buildinfo` blob Go 1.18+ writes (pointer size 8, flag 2)."""
    modinfo = SENTINEL + f"path\t{module}\nmod\t{module}\t{version}\t\n".encode() + SENTINEL
    text = b"go1.27.4"
    head = MAGIC + bytes([8, 2]) + b"\x00" * 16
    return head + varint(len(text)) + text + varint(len(modinfo)) + modinfo


def elf(path: Path, sections: dict[str, bytes], shstrndx: int | None = None) -> Path:
    """Write an ELF64 LE file holding `sections` (named, in order, after a null one)."""
    names = b"\x00" + b"".join(n.encode() + b"\x00" for n in sections) + b".shstrtab\x00"
    body = b""
    headers = [b"\x00" * 64]
    cursor = 64
    name_at = 1
    for name, data in [*sections.items(), (".shstrtab", names)]:
        header = struct.pack("<IIQQQQIIQQ", name_at, 1, 0, 0, cursor, len(data), 0, 0, 1, 0)
        headers.append(header)
        body += data
        cursor += len(data)
        name_at += len(name) + 1
    last = len(headers) - 1 if shstrndx is None else shstrndx
    ehdr = bytearray(64)
    ehdr[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<Q", ehdr, 0x28, cursor)
    struct.pack_into("<HHH", ehdr, 0x3A, 64, len(headers), last)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(ehdr) + body + b"".join(headers))
    path.chmod(0o755)
    return path
