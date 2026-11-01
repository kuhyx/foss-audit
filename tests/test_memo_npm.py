"""npm-cache readings are memoized: a hit skips the reader, a changed file or version misses."""

# ruff: noqa: F811  (the autouse no_network fixture is imported)
from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from foss_audit import cache_remove_npm_store, memo, progress, scan_cache_npm_cacache, scan_cache_npm_pnpm
from foss_audit.cache_remove_npm_store import NpmCache
from foss_audit.memo import Memo
from foss_audit.scan_cache_npm_cacache import scan_cacache, tarballs
from foss_audit.scan_cache_npm_pnpm import scan_pnpm_store
from tests.npm_helpers import REG, cache_entry, json_files, no_network, pkg_json, put, tgz, write_json  # noqa: F401
from tests.test_scan_cache_npm_store import make_db, mp


class Calls:
    """Counts how often the real readers run."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.pnpm = self.tarball = 0
        real_package, real_tarball = scan_cache_npm_pnpm.package, scan_cache_npm_cacache.read_tarball

        def package(*args: object) -> object:
            self.pnpm += 1
            return real_package(*args)  # type: ignore[arg-type]

        def read_tarball(*args: object) -> object:
            self.tarball += 1
            return real_tarball(*args)  # type: ignore[arg-type]

        monkeypatch.setattr(scan_cache_npm_pnpm, "package", package)
        monkeypatch.setattr(scan_cache_npm_cacache, "read_tarball", read_tarball)
        monkeypatch.setattr(cache_remove_npm_store, "read_tarball", read_tarball)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    return Calls(monkeypatch)


@pytest.fixture
def store(tmp_path: Path) -> Path:
    """A pnpm v10 store with one licensed package index."""
    root = tmp_path / "pnpm" / "v10"
    files = json_files(root, {"package.json": pkg_json(name="a", version="1.0.0", license="MIT")})
    write_json(root / "index/ab/hash-a@1.0.0.json", {"name": "a", "version": "1.0.0", "files": files})
    return tmp_path / "pnpm"


def scanned(memo_file: Path, scan: Callable[[Memo], list[object]]) -> list[object]:
    run = Memo(memo_file)
    found = scan(run)
    run.save()
    return found


def test_pnpm_hit_skips_the_reader_and_returns_the_same(store: Path, tmp_path: Path, calls: Calls) -> None:
    memo_file = tmp_path / "m.json"
    first = scanned(memo_file, lambda m: list(scan_pnpm_store(store, m)))
    second = scanned(memo_file, lambda m: list(scan_pnpm_store(store, m)))
    assert (calls.pnpm, first) == (1, second)


def test_pnpm_changed_index_file_is_read_again(store: Path, tmp_path: Path, calls: Calls) -> None:
    memo_file = tmp_path / "m.json"
    scanned(memo_file, lambda m: list(scan_pnpm_store(store, m)))
    index = next((store / "v10").glob("index/*/*.json"))
    os.utime(index, ns=(5, 5))
    scanned(memo_file, lambda m: list(scan_pnpm_store(store, m)))
    assert calls.pnpm == 2


def test_pnpm_unlicensed_reading_is_never_stored(tmp_path: Path, calls: Calls) -> None:
    root = tmp_path / "pnpm" / "v10"
    files = json_files(root, {"package.json": pkg_json(name="b", version="1.0.0")})
    write_json(root / "index/ab/b.json", {"name": "b", "version": "1.0.0", "files": files})
    memo_file = tmp_path / "m.json"
    for _ in range(2):
        scanned(memo_file, lambda m: list(scan_pnpm_store(tmp_path / "pnpm", m)))
    assert calls.pnpm == 2


def test_pnpm_database_rows_are_keyed_by_their_row_key(tmp_path: Path, calls: Calls) -> None:
    v11 = tmp_path / "pnpm" / "v11"
    entry = {"digest": put(v11, pkg_json(name="d", version="2.0.0", license="ISC")).hex(), "mode": 420}
    good = {"files": {"package.json": entry}, "manifest": {"name": "d", "version": "2.0.0"}}
    make_db(v11, [("sha512-x\td@2.0.0", mp(good)), ("sha512-y\tbad@1", b"\xc1")])
    memo_file = tmp_path / "m.json"
    for _ in range(2):
        scanned(memo_file, lambda m: list(scan_pnpm_store(tmp_path / "pnpm", m)))
    assert calls.pnpm == 1  # the undecodable row never reaches the reader
    assert any("|db|" in key for key in json.loads(memo_file.read_text())["entries"])


def test_a_memo_version_bump_reads_everything_again(
    store: Path, tmp_path: Path, calls: Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    memo_file = tmp_path / "m.json"
    scanned(memo_file, lambda m: list(scan_pnpm_store(store, m)))
    monkeypatch.setattr(memo, "MEMO_VERSION", memo.MEMO_VERSION + 1)
    scanned(memo_file, lambda m: list(scan_pnpm_store(store, m)))
    assert calls.pnpm == 2


def cacache_with(tmp_path: Path, license_id: str = "MIT") -> Path:
    cache = tmp_path / "npm"
    cache_entry(cache, REG + "t/-/t-1.tgz", tgz([("package/package.json", pkg_json(license=license_id))]))
    git = tgz([("repo-abc/package.json", pkg_json(name="g", version="1.0.0", license="MIT"))])
    cache_entry(cache, "pacote:tarball:github:u/g#abc", git)
    return cache


def test_cacache_hit_skips_the_tarball_reader(tmp_path: Path, calls: Calls) -> None:
    cache, memo_file = cacache_with(tmp_path), tmp_path / "m.json"
    first = scanned(memo_file, lambda m: list(scan_cacache(set(), cache, m)))
    second = scanned(memo_file, lambda m: list(scan_cacache(set(), cache, m)))
    assert (calls.tarball, first) == (2, second)


def test_cacache_rewritten_entry_has_a_new_integrity_and_is_read_again(tmp_path: Path, calls: Calls) -> None:
    cache, memo_file = cacache_with(tmp_path), tmp_path / "m.json"
    scanned(memo_file, lambda m: list(scan_cacache(set(), cache, m)))
    cache_entry(cache, REG + "t/-/t-1.tgz", tgz([("package/package.json", pkg_json(license="ISC"))]))
    got = scanned(memo_file, lambda m: list(scan_cacache(set(), cache, m)))
    assert calls.tarball == 3  # t, g, then only the rewritten t
    assert {(f.name, f.cached.license) for f in got} == {("t", "ISC"), ("g", "MIT")}  # type: ignore[attr-defined]


def test_names_for_the_remove_step_are_remembered(tmp_path: Path, calls: Calls) -> None:
    cache, root = cacache_with(tmp_path), tmp_path / "pnpm"
    v10 = root / "v10"
    files = json_files(v10, {"package.json": pkg_json(name="a", version="1.0.0", license="MIT")})
    write_json(v10 / "index/ab/hash-a@1.0.0.json", {"name": "a", "version": "1.0.0", "files": files})
    memo_file = tmp_path / "m.json"
    listing = list(tarballs(cache))
    built = []
    for _ in range(2):
        run = Memo(memo_file)
        built.append(NpmCache(cache, root, run, listing))
        run.save()
    assert calls.tarball == 1  # the git archive's name is read once
    assert built[0].paths == built[1].paths
    assert built[1].step("a")[0].startswith("rm -rf ")
    stored = json.loads(memo_file.read_text())["entries"]
    assert any(key.startswith("name|") for key in stored)
    assert built[1].clean.keys() == {"t", "g"}


def test_memo_hits_still_advance_the_progress_counter(
    store: Path, tmp_path: Path, ticks: dict[str, tuple[int, int | None]]
) -> None:
    memo_file = tmp_path / "m.json"
    for _ in range(2):
        scanned(memo_file, lambda m: list(scan_pnpm_store(store, m)))
        assert ticks["npm-cache"] == (1, 1)
        ticks.clear()
        progress.reset()
