"""Maven, pip, pub and cargo readings are memoized the same way: hit, miss on change, bypass."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

from foss_audit import scan_cache_maven_memo, scan_cache_pip, scan_cache_pub
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
