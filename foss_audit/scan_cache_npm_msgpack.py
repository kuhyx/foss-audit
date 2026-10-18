"""Decode the msgpack blobs of pnpm 11's store index (`v11/index.db`).

pnpm 11 packs each `package_index.data` row with msgpackr and its "records"
extension: `d4 72 <id>` defines a record (an array of keys, then one value per
key) and a later lone byte 0x40..0x7f (normally a positive fixint) reuses
record <id>, so repeated `{digest, mode, size}` maps cost one byte of keys.
Records are per blob. Stdlib only: this is the subset pnpm writes, and an
unknown type raises ValueError rather than guessing.
"""

from __future__ import annotations

import struct
from typing import Any

RECORD_EXT = 0x72
RECORD_IDS = range(0x40, 0x80)
# Fixed-width scalars: type byte -> struct format.
SCALARS = {
    0xCA: ">f",
    0xCB: ">d",
    0xCC: ">B",
    0xCD: ">H",
    0xCE: ">I",
    0xCF: ">Q",
    0xD0: ">b",
    0xD1: ">h",
    0xD2: ">i",
    0xD3: ">q",
}
CONSTANTS: dict[int, Any] = {0xC0: None, 0xC2: False, 0xC3: True}
# Length-prefixed str/bin/array/map: type byte -> (kind, length format).
SIZED = {
    0xD9: ("str", ">B"),
    0xDA: ("str", ">H"),
    0xDB: ("str", ">I"),
    0xC4: ("bin", ">B"),
    0xC5: ("bin", ">H"),
    0xC6: ("bin", ">I"),
    0xDC: ("array", ">H"),
    0xDD: ("array", ">I"),
    0xDE: ("map", ">H"),
    0xDF: ("map", ">I"),
}


def _fix_kind(token: int) -> tuple[str, int]:
    """(kind, length) of a fixmap (0x8_), fixarray (0x9_) or fixstr (0xa0-0xbf)."""
    if token <= 0x8F:
        return "map", token & 0x0F
    if token <= 0x9F:
        return "array", token & 0x0F
    return "str", token & 0x1F


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0
        self.records: dict[int, list[str]] = {}

    def take(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise ValueError("msgpack: truncated")
        chunk = self.data[self.pos : self.pos + n]
        self.pos += n
        return chunk

    def unpack(self, fmt: str) -> Any:
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]

    def sized(self, kind: str, n: int) -> Any:
        if kind == "str":
            return self.take(n).decode()
        if kind == "bin":
            return self.take(n)
        if kind == "array":
            return [self.read() for _ in range(n)]
        return {self.read(): self.read() for _ in range(n)}

    def record(self, rid: int) -> dict[str, Any]:
        return {key: self.read() for key in self.records[rid]}

    def read(self) -> Any:
        token = self.take(1)[0]
        if token in RECORD_IDS and token in self.records:
            return self.record(token)
        if token < 0x80 or token >= 0xE0:
            # Positive / negative fixint.
            return token - 0x100 if token >= 0xE0 else token
        if token <= 0xBF:
            return self.sized(*_fix_kind(token))
        return self.typed(token)

    def typed(self, token: int) -> Any:
        if token in CONSTANTS:
            return CONSTANTS[token]
        if token in SCALARS:
            return self.unpack(SCALARS[token])
        if token in SIZED:
            kind, fmt = SIZED[token]
            return self.sized(kind, self.unpack(fmt))
        if token == 0xD4:
            return self.fixext1()
        raise ValueError(f"msgpack: unsupported type 0x{token:02x} at {self.pos - 1}")

    def fixext1(self) -> Any:
        ext, rid = self.take(2)
        if ext != RECORD_EXT:
            raise ValueError(f"msgpack: unsupported extension 0x{ext:02x}")
        keys = self.read()
        self.records[0x40 | (rid & 0x3F)] = [str(k) for k in keys]
        return self.record(0x40 | (rid & 0x3F))


def unpackb(data: bytes) -> Any:
    """The value packed in `data` (records expanded into plain dicts)."""
    return _Reader(data).read()
