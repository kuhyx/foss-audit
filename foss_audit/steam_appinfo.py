"""Read per-app EULAs from Steam's local app cache (appcache/appinfo.vdf).

The store site (and its EULA pages) is blocked in /etc/hosts on purpose, so
the scanner never goes online: the Steam client already keeps every app's
`common/eulas` list (id, name, url) in this binary cache.

Format (v28/v29): a header, then one record per app -- appid, size, 64 bytes
of hashes and timestamps, then a binary KeyValues tree. v29 stores keys as
u32 indexes into a string table whose offset is in the header; v28 stores
them inline. Records are walked by their size field, so only installed apps
are ever parsed and one app's EULA can never be attributed to another.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

APPINFO = Path.home() / ".local/share/Steam/appcache/appinfo.vdf"
MAGIC_V28 = 0x07564428
MAGIC_V29 = 0x07564429
# info_state, last_updated, access token, sha1, change number, binary sha1.
RECORD_HEADER = 4 + 4 + 8 + 20 + 4 + 20
# Binary KeyValues value types; 0x08 closes a map.
KV_MAP, KV_STR, KV_INT, KV_FLOAT, KV_U64, KV_END, KV_I64 = 0, 1, 2, 3, 7, 8, 10
FIXED = {KV_INT: 4, KV_FLOAT: 4, KV_U64: 8, KV_I64: 8}
KvTree = dict[str, "KvTree | str"]


@dataclass(frozen=True)
class Eula:
    """One app-specific EULA listed in the Steam app cache."""

    id: str
    name: str
    url: str


class _Reader:
    """Cursor over one record's KeyValues bytes."""

    def __init__(self, data: bytes, strings: list[str] | None) -> None:
        self.data, self.pos, self.strings = data, 0, strings

    def cstring(self) -> str:
        end = self.data.index(b"\0", self.pos)
        text = self.data[self.pos : end].decode("utf-8", "replace")
        self.pos = end + 1
        return text

    def key(self) -> str:
        if self.strings is None:
            return self.cstring()
        (index,) = struct.unpack_from("<I", self.data, self.pos)
        self.pos += 4
        return self.strings[int(index)]

    def tree(self) -> KvTree:
        out: KvTree = {}
        while True:
            kind = self.data[self.pos]
            self.pos += 1
            if kind == KV_END:
                return out
            name = self.key()
            if kind == KV_MAP:
                out[name] = self.tree()
            elif kind == KV_STR:
                out[name] = self.cstring()
            elif kind in FIXED:
                self.pos += FIXED[kind]
            else:
                raise ValueError(f"unknown KeyValues type {kind}")


def _string_table(data: bytes, offset: int) -> list[str]:
    (count,) = struct.unpack_from("<I", data, offset)
    parts = data[offset + 4 :].split(b"\0", count)[:count]
    return [p.decode("utf-8", "replace") for p in parts]


def _eulas(tree: KvTree) -> list[Eula]:
    common = tree.get("appinfo", {})
    common = common.get("common", {}) if isinstance(common, dict) else {}
    listed = common.get("eulas", {}) if isinstance(common, dict) else {}
    if not isinstance(listed, dict):
        return []
    return [
        Eula(id=e.get("id", ""), name=e.get("name", ""), url=e.get("url", ""))  # type: ignore[arg-type]
        for e in listed.values()
        if isinstance(e, dict) and e.get("url")
    ]


def _parse(data: bytes, wanted: set[int]) -> dict[int, list[Eula]]:
    magic, _universe = struct.unpack_from("<II", data, 0)
    if magic == MAGIC_V29:
        (table_at,) = struct.unpack_from("<q", data, 8)
        strings: list[str] | None = _string_table(data, table_at)
        pos = 16
    elif magic == MAGIC_V28:
        strings, pos = None, 8
    else:
        raise ValueError(f"unsupported appinfo.vdf magic {magic:#x}")
    found: dict[int, list[Eula]] = {}
    while True:
        # The appid-0 terminator has no size field after it.
        (appid,) = struct.unpack_from("<I", data, pos)
        if appid == 0:
            return found
        (size,) = struct.unpack_from("<I", data, pos + 4)
        body = pos + 8
        if appid in wanted:
            kv = data[body + RECORD_HEADER : body + size]
            found[appid] = _eulas(_Reader(kv, strings).tree())
        pos = body + size


def eulas_for(appids: set[int], path: Path | None = None) -> dict[int, list[Eula]]:
    """EULAs of the given apps; {} when the cache is missing or unreadable.

    A corrupt or newer-format cache only loses the EULA detail: the Steam
    Subscriber Agreement still licenses every app, so the scan carries on.
    """
    path = path or APPINFO
    try:
        return _parse(path.read_bytes(), appids)
    except OSError, ValueError, IndexError, KeyError, struct.error:
        return {}
