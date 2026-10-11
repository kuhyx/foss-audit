"""Build binary appinfo.vdf files (v28 inline keys, v29 string table) for tests."""

from __future__ import annotations

import struct
from typing import Any

V28, V29 = 0x07564428, 0x07564429
HEADER = b"\0" * 60  # info_state .. binary sha1: the parser skips it


class Builder:
    """Encode KeyValues trees; v29 collects keys into a string table."""

    def __init__(self, magic: int = V29) -> None:
        self.magic = magic
        self.strings: list[str] = []

    def key(self, name: str) -> bytes:
        if self.magic == V28:
            return name.encode() + b"\0"
        if name not in self.strings:
            self.strings.append(name)
        return struct.pack("<I", self.strings.index(name))

    def tree(self, data: dict[str, Any]) -> bytes:
        out = b""
        for name, value in data.items():
            if isinstance(value, dict):
                out += b"\x00" + self.key(name) + self.tree(value)
            elif isinstance(value, int):
                out += b"\x02" + self.key(name) + struct.pack("<i", value)
            elif isinstance(value, bytes):  # raw (type byte, payload) for odd types
                out += value[:1] + self.key(name) + value[1:]
            else:
                out += b"\x01" + self.key(name) + value.encode() + b"\0"
        return out + b"\x08"

    def file(self, apps: dict[int, dict[str, Any]]) -> bytes:
        body = b""
        for appid, tree in apps.items():
            record = HEADER + self.tree(tree)
            body += struct.pack("<II", appid, len(record)) + record
        body += struct.pack("<I", 0)
        if self.magic == V28:
            return struct.pack("<II", V28, 1) + body
        table_at = 16 + len(body)
        table = struct.pack("<I", len(self.strings)) + b"".join(s.encode() + b"\0" for s in self.strings)
        return struct.pack("<IIq", V29, 1, table_at) + body + table


def eula_app(appid: int, *eulas: tuple[str, str]) -> dict[str, Any]:
    """An appinfo tree whose common/eulas lists the given (name, url) pairs."""
    listed = {str(i): {"id": f"{appid}_eula_{i}", "name": n, "url": u} for i, (n, u) in enumerate(eulas)}
    return {"appinfo": {"appid": appid, "common": {"name": "x", "eulas": listed}}}
