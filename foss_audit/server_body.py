"""The /api/scan body: encoded and gzipped once per result, with a `scanning` tail."""

from __future__ import annotations

import json
import threading
import zlib
from typing import Any

GZIP_LEVEL = 6


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


def _tail(scanning: bool) -> bytes:
    return b'"scanning":true}' if scanning else b'"scanning":false}'


class EncodedScan:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self._lock = threading.Lock()
        self._head: bytes | None = None
        self._zipped: tuple[bytes, Any] | None = None
        self._zipped_tails: dict[bool, bytes] = {}

    def prewarm(self) -> None:
        def work() -> None:
            self.parts(scanning=False, zipped=True)

        threading.Thread(target=work, daemon=True).start()

    def parts(self, *, scanning: bool, zipped: bool) -> tuple[bytes, bytes]:
        """(shared bytes, tail): the big part is cached and never copied."""
        with self._lock:
            if self._head is None:
                text = json.dumps(self.result, separators=(",", ":"))
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
