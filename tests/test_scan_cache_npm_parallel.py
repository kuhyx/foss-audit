"""npm-cache scanner: packages are read in parallel, so their upstream lookups overlap."""

# ruff: noqa: F811  (the autouse no_network fixture is imported)
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from foss_audit import upstream_license
from foss_audit.scan_cache_npm_cacache import scan_cacache
from foss_audit.scan_cache_npm_pnpm import scan_pnpm_store
from tests.npm_helpers import (  # noqa: F401
    REG,
    cache_entry,
    json_files,
    no_network,
    pkg_json,
    tgz,
    write_json,
)

NAMES = ("one", "two")


def meeting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every upstream lookup waits for the other: a serial scan times out."""
    barrier = threading.Barrier(len(NAMES), timeout=5)

    def lookup(url: str, ref: str = "") -> tuple[str, str]:
        barrier.wait()
        return "MIT", f"upstream {url} HEAD: LICENSE file"

    monkeypatch.setattr(upstream_license, "upstream_license", lookup)


def manifest(name: str) -> bytes:
    return pkg_json(name=name, version="1.0.0", repository=f"github:o/{name}")


def test_pnpm_packages_are_read_in_parallel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    meeting(monkeypatch)
    v10 = tmp_path / "v10"
    for name in NAMES:
        doc = {"name": name, "version": "1.0.0", "files": json_files(v10, {"package.json": manifest(name)})}
        write_json(v10 / f"index/ab/hash-{name}@1.0.0.json", doc)
    got = [(f.name, f.cached.license) for f in scan_pnpm_store(tmp_path)]
    assert got == [("one", "MIT"), ("two", "MIT")]


def test_cacache_tarballs_are_read_in_parallel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    meeting(monkeypatch)
    for name in NAMES:
        cache_entry(
            tmp_path, f"{REG}{name}/-/{name}-1.0.0.tgz", tgz([("package/package.json", manifest(name))])
        )
    got = [(f.name, f.cached.license) for f in scan_cacache(set(), tmp_path)]
    assert got == [("one", "MIT"), ("two", "MIT")]
