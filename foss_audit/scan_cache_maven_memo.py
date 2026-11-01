"""Memoized JAR/AAR license reading (see memo.py): opening archives is the slow part of a scan."""

from __future__ import annotations

from pathlib import Path

from foss_audit import memo
from foss_audit.scan_cache_maven_jar import archive_license


def memoised_archive_license(
    readings: memo.Memo, paths: list[Path], group: str, artifact: str
) -> tuple[str, str]:
    """`archive_license`, remembered per artifact and the size and mtime of each archive."""
    key = f"{group}:{artifact}|" + ";".join(memo.stat_key(path) for path in paths)
    hit = readings.get(key)
    if hit is not None:
        return hit[0], hit[1]
    found = archive_license(paths, group, artifact)
    readings.put(key, list(found))
    return found
