"""Cargo readings are memoized (registry copies, not git checkouts); garbled entries heal in every source."""

# ruff: noqa: F811  (the archive_calls fixture is imported)

from __future__ import annotations

from pathlib import Path

import pytest

from foss_audit import scan_cache_cargo, scan_cache_pip
from foss_audit.memo import Memo
from foss_audit.scan_cache_maven_memo import memoised_archive_license
from foss_audit.scan_cache_pip_meta import Record
from foss_audit.scan_cache_pub import cached_license
from tests.test_memo import garble
from tests.test_memo_sources import MIT, archive_calls, jar, record  # noqa: F401, F811

# --- cargo: registry copies are memoized, git checkouts are not ------------


def cargo_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(scan_cache_cargo, "CARGO", tmp_path / ".cargo")
    monkeypatch.setattr(scan_cache_cargo, "SRC", tmp_path / "src")
    return tmp_path / ".cargo"


def crate_dir(root: Path, stem: str, license_line: str = 'license = "MIT"') -> Path:
    path = root / "registry/src/idx" / stem
    path.mkdir(parents=True)
    name, _, version = stem.rpartition("-")
    (path / "Cargo.toml").write_text(
        f'[package]\nname = "{name}"\nversion = "{version}"\n{license_line}\nrepository = "https://r/{name}"\n'
    )
    return path


def test_cargo_registry_copy_hit_skips_the_reader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cargo, file = cargo_home(tmp_path, monkeypatch), tmp_path / "m.json"
    crate_dir(cargo, "serde-1.0.0")
    calls: list[Path] = []
    real = scan_cache_cargo.read_dir

    def spy(path: Path, where: str) -> object:
        calls.append(path)
        return real(path, where)

    monkeypatch.setattr(scan_cache_cargo, "read_dir", spy)
    run = Memo(file)
    first = scan_cache_cargo.cached_artifacts(run)
    run.save()
    second = scan_cache_cargo.cached_artifacts(Memo(file))
    assert len(calls) == 1
    assert [(a.name, a.url, a.versions) for a in second] == [(a.name, a.url, a.versions) for a in first]
    assert second[0].url == "https://r/serde"


def test_cargo_changed_manifest_is_read_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cargo, file = cargo_home(tmp_path, monkeypatch), tmp_path / "m.json"
    folder = crate_dir(cargo, "serde-1.0.0")
    run = Memo(file)
    scan_cache_cargo.cached_artifacts(run)
    run.save()
    (folder / "Cargo.toml").write_text('[package]\nname = "serde"\nversion = "1.0.0"\nlicense = "GPL-3.0"\n')
    [art] = scan_cache_cargo.cached_artifacts(Memo(file))
    assert art.versions[0].license == "GPL-3.0"


def test_cargo_git_checkouts_are_never_memoized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cargo, file = cargo_home(tmp_path, monkeypatch), tmp_path / "m.json"
    checkout = cargo / "git/checkouts/db-1/abc"
    checkout.mkdir(parents=True)
    (checkout / "Cargo.toml").write_text('[package]\nname = "g"\nversion = "0.1.0"\nlicense = "MIT"\n')
    workspace = cargo / "git/checkouts/db-2/def"
    workspace.mkdir(parents=True)
    (workspace / "Cargo.toml").write_text("[workspace]\nmembers = []\n")
    run = Memo(file)
    [art] = scan_cache_cargo.cached_artifacts(run)
    run.save()
    assert art.versions[0].license_from.endswith("(git checkout db-1/abc)")
    assert not file.exists() or '"entries":{}' in file.read_text()


def test_a_bypassing_memo_reads_everything(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cargo, file = cargo_home(tmp_path, monkeypatch), tmp_path / "m.json"
    crate_dir(cargo, "serde-1.0.0")
    run = Memo(file)
    scan_cache_cargo.cached_artifacts(run)
    run.save()
    calls: list[Path] = []
    real = scan_cache_cargo.read_dir
    monkeypatch.setattr(scan_cache_cargo, "read_dir", lambda p, w: (calls.append(p), real(p, w))[1])
    scan_cache_cargo.cached_artifacts(Memo(file, bypass=True))
    assert len(calls) == 1


def test_garbled_entries_are_read_again_by_every_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, archive_calls: list[Path]
) -> None:
    jar_path = jar(tmp_path / "a.jar")
    package = tmp_path / "hosted" / "p-1.0.0"
    package.mkdir(parents=True)
    (package / "LICENSE").write_text(MIT)
    body = tmp_path / "a.body"
    body.write_text("x")
    cargo = cargo_home(tmp_path, monkeypatch)
    crate_dir(cargo, "serde-1.0.0")
    reader_calls: list[Path] = []

    def reader(path: Path, origin: str) -> list[Record] | None:
        reader_calls.append(path)
        return [record()]

    def everything(run: Memo) -> list[object]:
        return [
            memoised_archive_license(run, [jar_path], "g", "a"),
            cached_license(run, package, package),
            scan_cache_pip.read_cached(body, "pip", reader, run),
            [(a.name, a.versions) for a in scan_cache_cargo.cached_artifacts(run)],
        ]

    file = tmp_path / "m.json"
    run = Memo(file)
    first = everything(run)
    run.save()
    garble(file)
    assert everything(Memo(file)) == first
    assert len(archive_calls) == 2
    assert len(reader_calls) == 2
