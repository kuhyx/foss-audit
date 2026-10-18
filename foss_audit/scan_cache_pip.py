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

from foss_audit.cache_common import CachedArtifact, CachedVersion, to_items
from foss_audit.model import Item
from foss_audit.scan_cache_pip_meta import Record, known
from foss_audit.scan_cache_pip_net import resolve
from foss_audit.scan_cache_pip_read import read_body, read_dist_dir, read_legacy
from foss_audit.scan_cache_pip_used import checkouts, used_by

HOME = Path.home()
PIP_CACHE = HOME / ".cache/pip"
UV_CACHE = HOME / ".cache/uv"
Reader = Callable[[Path, str], "list[Record] | None"]
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


def all_records() -> tuple[list[Record], int]:
    """Records of every cached distribution, plus how many bodies were unreadable."""
    records: list[Record] = []
    bad = 0
    for path, origin, reader in cache_files():
        found = reader(path, origin)
        if found is None:
            bad += 1
        records += found or []
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
    """One Item per distribution in ~/.cache/pip and ~/.cache/uv."""
    records, _bad = all_records()
    resolved = resolve(per_version(records), checkouts())
    return to_items("pip-cache", artifacts(resolved), used_by())
