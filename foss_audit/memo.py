"""Persistent memo of the raw per-artifact license readings of the package caches.

One JSON file per `*-cache` source in ~/.cache/foss-audit/memo/ (FOSS_AUDIT_MEMO_DIR
overrides) maps a key to one artifact's reading. Keys are immutable identities or
path+size+mtime, so a changed artifact misses by itself; MEMO_VERSION drops
everything when a reading's logic changes. Items are never memoized: curated
verdicts, requiredBy and remove commands are recomputed each scan.

Each worker process writes only its own file (tmp + rename), so no lock is needed.
A run keeps the entries it used, so gone artifacts leave the memo. A missing,
damaged or unwritable file is an empty memo. `?refresh=full` sets the bypass.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

MEMO_VERSION = 1
ENV_DIR = "FOSS_AUDIT_MEMO_DIR"
VOLATILE = ("upstream", "fetch failed", "license URL")
MALFORMED = (TypeError, ValueError, KeyError, IndexError, AttributeError)

_bypass = False


def set_bypass(flag: bool) -> None:
    global _bypass  # noqa: PLW0603 - one flag per scan worker process
    _bypass = flag


def memo_dir() -> Path:
    return Path(os.environ.get(ENV_DIR) or Path.home() / ".cache/foss-audit/memo")


def stat_key(path: Path) -> str:
    """`path` with its size and mtime: a rewritten file gets a new key."""
    try:
        info = path.stat()
    except OSError:
        return f"{path}|gone"
    return f"{path}|{info.st_size}|{info.st_mtime_ns}"


def require_text(*values: object) -> None:
    """Raise TypeError unless every stored field is a string (a decoder's shape check)."""
    if not all(isinstance(value, str) for value in values):
        raise TypeError("memo entry holds a non-string")


def reusable(license_id: str, license_from: str) -> bool:
    """True for a license found in the artifact's own files; network lookups can change without it."""
    return bool(license_id) and not any(word in license_from for word in VOLATILE)


class Memo:
    """key -> JSON value for one source; `path` None is a memo that stores nothing."""

    def __init__(self, path: Path | None, *, bypass: bool = False) -> None:
        self._path = path
        self._bypass = bypass
        self._lock = threading.Lock()
        self._entries: dict[str, Any] = {} if bypass or path is None else _load(path)
        self._loaded = frozenset(self._entries)
        self._touched: set[str] = set()
        self._dirty = False

    @classmethod
    def for_source(cls, source: str) -> Memo:
        return cls(memo_dir() / f"{source}.json", bypass=_bypass)

    def get(self, key: str) -> Any | None:
        """The stored value (kept on save), or None."""
        with self._lock:
            if key not in self._entries:
                return None
            self._touched.add(key)
            return self._entries[key]

    def recall[T](self, key: str, decode: Callable[[Any], T]) -> tuple[bool, T | None]:
        """(True, decode(stored)) for a stored entry; a malformed one is dropped and reads as a miss."""
        raw = self.get(key)
        if raw is None:
            return False, None
        try:
            return True, decode(raw)
        except MALFORMED:
            with self._lock:
                self._touched.discard(key)
                del self._entries[key]
            return False, None

    def put(self, key: str, value: Any) -> None:
        if self._path is None:
            return
        with self._lock:
            self._entries[key] = value
            self._touched.add(key)
            self._dirty = True

    def save(self) -> None:
        """Write the entries used this run; nothing when they are exactly the stored ones."""
        if self._path is None or not (self._bypass or self._dirty or self._touched != self._loaded):
            return
        with self._lock:
            entries = {key: self._entries[key] for key in self._touched}
        tmp = self._path.with_name(f"{self._path.name}.{os.getpid()}.tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps({"version": MEMO_VERSION, "entries": entries}, separators=(",", ":")))
            tmp.replace(self._path)
        except OSError:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)


def _load(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text())
    except OSError, ValueError:
        return {}
    entries = doc.get("entries") if isinstance(doc, dict) and doc.get("version") == MEMO_VERSION else None
    return entries if isinstance(entries, dict) else {}


NO_MEMO = Memo(None)
