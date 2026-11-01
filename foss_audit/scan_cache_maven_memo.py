"""Memoized JAR/AAR license reading (see memo.py): opening archives is the slow part of a scan."""

from __future__ import annotations

from pathlib import Path

from foss_audit import memo
from foss_audit.scan_cache_maven_jar import archive_license


def _decode(hit: list[str]) -> tuple[str, str]:
    license_id, where = hit
    memo.require_text(license_id, where)
    return license_id, where


def memoised_archive_license(
    readings: memo.Memo, paths: list[Path], group: str, artifact: str
) -> tuple[str, str]:
    """`archive_license`, remembered per artifact and the size and mtime of each archive."""
    key = f"{group}:{artifact}|" + ";".join(memo.stat_key(path) for path in paths)
    stored, hit = readings.recall(key, _decode)
    if stored and hit is not None:
        return hit
    found = archive_license(paths, group, artifact)
    readings.put(key, list(found))
    return found
