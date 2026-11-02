"""The /api/scan body: encoded and gzipped once per result, with a `scanning` tail.

The two remove fields are ~80% of a real scan's bytes and only matter once an item
is opened or acted on, so the body leaves them out; `removes` serves them by id.
"""

from __future__ import annotations

import json
import threading
import zlib
from typing import Any

GZIP_LEVEL = 6
REMOVE_FIELDS = ("removeCommand", "removeVia")


def accepts_gzip(header: str | None) -> bool:
    allowed: dict[str, bool] = {}
    for part in (header or "").split(","):
        name, _, params = part.partition(";")
        quality = params.strip().removeprefix("q=") if params.strip().startswith("q=") else "1"
        try:
            allowed[name.strip().lower()] = float(quality) > 0
        except ValueError:
            allowed[name.strip().lower()] = False
    return allowed.get("gzip", allowed.get("*", False))


def _without_remove(result: dict[str, Any]) -> dict[str, Any]:
    """`result` with every item's remove fields dropped; the input is left whole."""
    items = result.get("items")
    if not isinstance(items, list):
        return result
    slim = [{key: value for key, value in item.items() if key not in REMOVE_FIELDS} for item in items]
    return {**result, "items": slim}


def _tail(scanning: bool) -> bytes:
    return b'"scanning":true}' if scanning else b'"scanning":false}'


class EncodedScan:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self._lock = threading.Lock()
        self._head: bytes | None = None
        self._by_id: dict[str, dict[str, Any]] | None = None
        self._zipped: tuple[bytes, Any] | None = None
        self._zipped_tails: dict[bool, bytes] = {}

    def removes(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        """`{id: {removeCommand, removeVia}}` for the ids this result has; others are omitted."""
        with self._lock:
            if self._by_id is None:
                items = self.result.get("items")
                self._by_id = {item["id"]: item for item in items} if isinstance(items, list) else {}
            by_id = self._by_id
        return {
            item_id: {
                "removeCommand": by_id[item_id].get("removeCommand"),
                "removeVia": by_id[item_id].get("removeVia", ""),
            }
            for item_id in ids
            if item_id in by_id
        }

    def prewarm(self) -> None:
        def work() -> None:
            self.parts(scanning=False, zipped=True)

        threading.Thread(target=work, daemon=True).start()

    def parts(self, *, scanning: bool, zipped: bool) -> tuple[bytes, bytes]:
        """(shared bytes, tail): the big part is cached and never copied."""
        with self._lock:
            if self._head is None:
                text = json.dumps(_without_remove(self.result), separators=(",", ":"))
                self._head = text[:-1].encode() + (b"," if self.result else b"")
            if not zipped:
                return self._head, _tail(scanning)
            if self._zipped is None:
                compressor = zlib.compressobj(GZIP_LEVEL, zlib.DEFLATED, 31)
                self._zipped = (compressor.compress(self._head), compressor)
            head, compressor = self._zipped
            if scanning not in self._zipped_tails:
                fork = compressor.copy()
                self._zipped_tails[scanning] = fork.compress(_tail(scanning)) + fork.flush()
            return head, self._zipped_tails[scanning]
