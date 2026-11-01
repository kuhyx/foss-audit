"""Memoized reading of one npm package (see memo.py): a Found as a JSON list."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from foss_audit import memo
from foss_audit.cache_common import CachedVersion
from foss_audit.scan_cache_npm_manifest import Found


def encode(found: Found | None) -> list[Any]:
    if found is None:
        return []
    c = found.cached
    return [found.name, found.url, c.version, c.license, c.license_from, list(c.deps)]


def decode(data: list[Any]) -> Found | None:
    if not data:
        return None
    name, url, version, license_id, license_from, deps = data
    return Found(name, url, CachedVersion(version, license_id, license_from, tuple(deps)))


def memoised(store: memo.Memo, key: str, read: Callable[[], Found | None]) -> Found | None:
    """The stored reading for `key`, else `read()` (stored when it came from local files only)."""
    hit = store.get(key)
    if hit is not None:
        return decode(hit)
    found = read()
    if found is None or memo.reusable(found.cached.license, found.cached.license_from):
        store.put(key, encode(found))
    return found
