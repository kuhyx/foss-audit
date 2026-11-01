"""Maven, pip, pub and cargo readings are memoized the same way: hit, miss on change, bypass."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

from foss_audit import scan_cache_cargo, scan_cache_maven_memo, scan_cache_pip, scan_cache_pub
from foss_audit.memo import Memo
from foss_audit.scan_cache_maven_memo import memoised_archive_license
from foss_audit.scan_cache_pip_meta import Record
from foss_audit.scan_cache_pip_read import read_dist_dir
from foss_audit.scan_cache_pub import cached_license

MIT = "MIT License\n\nPermission is hereby granted, free of charge, to any person...\n"


# --- maven: the JAR/AAR license reading ------------------------------------


def jar(path: Path, license_text: str = MIT) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/LICENSE", license_text)
    return path


@pytest.fixture
def archive_calls(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    seen: list[Path] = []
    real = scan_cache_maven_memo.archive_license

    def spy(paths: list[Path], group: str, artifact: str) -> tuple[str, str]:
        seen.extend(paths)
        return real(paths, group, artifact)

    monkeypatch.setattr(scan_cache_maven_memo, "archive_license", spy)
    return seen


def test_maven_archive_hit_skips_opening_the_jar(tmp_path: Path, archive_calls: list[Path]) -> None:
    path, file = jar(tmp_path / "a.jar"), tmp_path / "m.json"
    first = Memo(file)
    answer = memoised_archive_license(first, [path], "g", "a")
    first.save()
    assert answer[0] == "MIT"
    assert memoised_archive_license(Memo(file), [path], "g", "a") == answer
    assert archive_calls == [path]


def test_maven_changed_jar_or_missing_license_is_read_again(
    tmp_path: Path, archive_calls: list[Path]
) -> None:
    path, file = jar(tmp_path / "a.jar"), tmp_path / "m.json"
    run = Memo(file)
    memoised_archive_license(run, [path], "g", "a")
    run.save()
    jar(path, "no license in here")
    changed = Memo(file)
    assert memoised_archive_license(changed, [path], "g", "a")[0] == ""
    changed.save()
    assert memoised_archive_license(Memo(file), [path], "g", "a")[0] == ""  # a blank answer is stable too
    assert len(archive_calls) == 2


# --- pip: wheel and response bodies ----------------------------------------


def record(name: str = "x") -> Record:
    return Record(name, "1", "MIT", "METADATA", ("dep",), "https://x", extra_deps=("e",), meta=True)


def test_pip_body_reading_is_remembered_even_when_unreadable(tmp_path: Path) -> None:
    body, bad, file = tmp_path / "a.body", tmp_path / "b.body", tmp_path / "m.json"
    for path in (body, bad):
        path.write_text("x")
    calls: list[Path] = []

    def reader(path: Path, origin: str) -> list[Record] | None:
        calls.append(path)
        return None if path == bad else [record()]

    run = Memo(file)
    first = [scan_cache_pip.read_cached(p, "pip", reader, run) for p in (body, bad)]
    run.save()
    again = Memo(file)
    assert (
        [scan_cache_pip.read_cached(p, "pip", reader, again) for p in (body, bad)]
        == first
        == [[record()], None]
    )
    assert calls == [body, bad]
    os.utime(body, ns=(7, 7))
    scan_cache_pip.read_cached(body, "pip", reader, again)
    assert calls == [body, bad, body]


def test_pip_unpacked_dist_info_is_always_read(tmp_path: Path) -> None:
    folder = tmp_path / "x-1.dist-info"
    folder.mkdir()
    meta = folder / "METADATA"
    meta.write_text("Metadata-Version: 2.1\nName: x\nVersion: 1\nLicense-Expression: MIT\n")
    run = Memo(tmp_path / "m.json")
    [found] = scan_cache_pip.read_cached(meta, "uv", read_dist_dir, run) or []
    assert found.license == "MIT"
    run.save()
    assert not (tmp_path / "m.json").exists() or '"entries":{}' in (tmp_path / "m.json").read_text()


# --- pub: license of a package dir -----------------------------------------


def test_pub_license_is_remembered_per_directory_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package, file = tmp_path / "hosted" / "p-1.0.0", tmp_path / "m.json"
    package.mkdir(parents=True)
    (package / "LICENSE").write_text(MIT)
    calls: list[Path] = []
    real = scan_cache_pub.resolve

    def spy(directory: Path, stop: Path) -> tuple[str, str]:
        calls.append(directory)
        return real(directory, stop)

    monkeypatch.setattr(scan_cache_pub, "resolve", spy)
    run = Memo(file)
    first = cached_license(run, package, package)
    run.save()
    assert cached_license(Memo(file), package, package) == first
    assert first[0] == "MIT"
    assert len(calls) == 1
    (package / "LICENSE").unlink()
    os.utime(package, ns=(9, 9))
    assert cached_license(Memo(file), package, package)[0] == ""
    assert len(calls) == 2


def test_pub_license_of_a_monorepo_package_keys_on_every_directory_up_to_the_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "git" / "repo-abc"
    package = checkout / "packages" / "p"
    package.mkdir(parents=True)
    (checkout / "LICENSE").write_text(MIT)
    run = Memo(tmp_path / "m.json")
    assert cached_license(run, package, checkout)[1] == "../../LICENSE file"
    run.save()
    os.utime(checkout, ns=(3, 3))  # the checkout root changed: a new key
    assert cached_license(Memo(tmp_path / "m.json"), package, checkout)[0] == "MIT"


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
