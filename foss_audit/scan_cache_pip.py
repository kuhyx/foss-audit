"""Scan pip's and uv's download caches: one Item per cached Python distribution.

Every cached wheel, sdist and PEP 658 metadata body is read for its own
METADATA/PKG-INFO (see `scan_cache_pip_read`); bodies that are index pages or
no distribution at all are skipped. Distributions are grouped by PEP 503 name
and every cached version keeps the license its own metadata declares, so
`cache_common.to_items` can take the worst one.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

from foss_audit import cache_remove_pip, memo, progress
from foss_audit.cache_common import SRC, CachedArtifact, CachedVersion, to_items
from foss_audit.memo import NO_MEMO, Memo
from foss_audit.model import Item
from foss_audit.scan_cache_pip_meta import Record, known
from foss_audit.scan_cache_pip_net import resolve
from foss_audit.scan_cache_pip_read import read_body, read_dist_dir, read_legacy
from foss_audit.scan_cache_pip_used import checkouts, used_by

HOME = Path.home()
PIP_CACHE = HOME / ".cache/pip"
UV_CACHE = HOME / ".cache/uv"
Reader = Callable[[Path, str], "list[Record] | None"]
# Distribution name -> (origin label, cache file) of every copy read.
Where = dict[str, list[tuple[str, Path]]]
# (cache root, bounded glob, origin label, reader). selfcheck/ only holds pip's
# version-check state and uv's simple-v*/wheels-v* only index pages and
# pointers into archive-v0, so none of those name a distribution.
SOURCES: tuple[tuple[str, str, str, Reader], ...] = (
    ("pip", "http-v2/*/*/*/*/*/*.body", "pip http-v2", read_body),
    ("pip", "http/*/*/*/*/*/*", "pip http", read_legacy),
    ("pip", "wheels/*/*/*/*/*.whl", "pip wheels", read_body),
    ("uv", "archive-v0/*/*.dist-info/METADATA", "uv archive-v0", read_dist_dir),
    ("uv", "archive-v0/*/lib/python*/site-packages/*.dist-info/METADATA", "uv archive-v0 env", read_dist_dir),
    ("uv", "sdists-v*/*/*/*/*.dist-info/METADATA", "uv sdists", read_dist_dir),
    ("uv", "sdists-v*/*/*/*/*/*.dist-info/METADATA", "uv sdists", read_dist_dir),
    ("uv", "sdists-v*/*/*/*/*/*/*.dist-info/METADATA", "uv sdists", read_dist_dir),
    ("uv", "sdists-v*/*/*/*/src/PKG-INFO", "uv sdists", read_dist_dir),
    ("uv", "sdists-v*/*/*/*/*/src/PKG-INFO", "uv sdists", read_dist_dir),
)


def cache_files() -> Iterator[tuple[Path, str, Reader]]:
    """Every cached file worth reading, with its origin label and reader."""
    roots = {"pip": PIP_CACHE, "uv": UV_CACHE}
    for root, pattern, origin, reader in SOURCES:
        for path in sorted(roots[root].glob(pattern)):
            if path.is_file():
                yield path, origin, reader


def read_cached(path: Path, origin: str, reader: Reader, readings: Memo) -> list[Record] | None:
    """`reader(path, origin)`, remembered by the file's size and mtime. An unpacked dist-info
    is read afresh: its license files and editable sources lie outside the one file."""
    if reader is read_dist_dir:
        return reader(path, origin)
    key = f"{origin}|{memo.stat_key(path)}"
    hit = readings.get(key)
    if hit is not None:
        return None if hit["records"] is None else [Record.from_json(r) for r in hit["records"]]
    found = reader(path, origin)
    readings.put(key, {"records": None if found is None else [r.to_json() for r in found]})
    return found


def read_all(readings: Memo = NO_MEMO) -> tuple[list[Record], int, Where]:
    """Records of every cached distribution, how many bodies were unreadable, and
    the (origin, file) each distribution was read from (for its remove command)."""
    records: list[Record] = []
    bad = 0
    where: Where = {}
    for path, origin, reader in progress.counted("pip-cache", list(cache_files())):
        found = read_cached(path, origin, reader, readings)
        if found is None:
            bad += 1
        for record in found or []:
            where.setdefault(record.name, []).append((origin, path))
        records += found or []
    return records, bad, where


def all_records() -> tuple[list[Record], int]:
    """Records of every cached distribution, plus how many bodies were unreadable."""
    records, bad, _where = read_all()
    return records, bad


def best(records: list[Record]) -> Record:
    """Of several copies of one version, the one with a recognised license;
    a meta-package when any copy shows it ships no code."""
    chosen = next(
        (r for r in records if known(r.license)), next((r for r in records if r.license), records[0])
    )
    return replace(chosen, meta=any(r.meta for r in records))


def per_version(records: list[Record]) -> list[Record]:
    """One record per (name, version): the best of its cached copies."""
    grouped: dict[tuple[str, str], list[Record]] = {}
    for record in records:
        grouped.setdefault((record.name, record.version), []).append(record)
    return [best(copies) for _, copies in sorted(grouped.items())]


def artifacts(records: list[Record]) -> list[CachedArtifact]:
    """One CachedArtifact per distribution, one CachedVersion per record."""
    arts: dict[str, CachedArtifact] = {}
    for r in records:
        art = arts.setdefault(r.name, CachedArtifact(name=r.name, url=r.url))
        art.versions.append(CachedVersion(r.version, r.license, r.license_from, r.deps, r.extra_deps, r.meta))
    return list(arts.values())


def scan_pip_cache() -> list[Item]:
    """One Item per distribution in ~/.cache/pip and ~/.cache/uv, each with its remove command."""
    readings = Memo.for_source("pip-cache")
    records, _bad, where = read_all(readings)
    readings.save()
    arts = artifacts(resolve(per_version(records), checkouts()))
    items = to_items("pip-cache", arts, used_by())
    cache_remove_pip.fill(items, arts, where, UV_CACHE, SRC)
    return items
