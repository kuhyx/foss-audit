"""scan_cache_pub: ~/.pub-cache hosted + git packages, license read from the package's own files."""

from __future__ import annotations

from pathlib import Path

import pytest

from foss_audit import scan_cache_pub, scan_cache_pub_license, upstream_license
from foss_audit.scan_cache_pub_license import recognise, resolve

MIT = "MIT License\n\nPermission is hereby granted, free of charge, to any person...\n"
BSD3 = (
    "Copyright 2014 The Flutter Authors. All rights reserved.\n\n"
    "Redistribution and use in source and binary forms, with or without modification...\n"
    "* Neither the name of Google Inc. nor the names of its contributors may be used to endorse or promote\n"
)
SYNCFUSION = (
    "Syncfusion<sup>&reg;</sup> License\n\nSyncfusion<sup>&reg;</sup> Flutter Core package is available "
    "under "
    "the Syncfusion Essential Studio program, and can be licensed either under the "
    "Syncfusion<sup>&reg;</sup> Community License Program or the Syncfusion commercial license.\n"
)


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def pkg(root: Path, name: str, version: str, license_text: str | None = MIT, extra: str = "") -> Path:
    write(root / "pubspec.yaml", f"name: {name}\nversion: {version}\n{extra}")
    if license_text is not None:
        write(root / "LICENSE", license_text)
    return root


@pytest.fixture(autouse=True)
def upstream(monkeypatch: pytest.MonkeyPatch) -> dict[str, tuple[str, str]]:
    """Canned upstream answers by URL; a URL not listed fails the test (no network, ever)."""
    answers: dict[str, tuple[str, str]] = {}
    monkeypatch.setattr(upstream_license, "upstream_license", answers.__getitem__)
    return answers


@pytest.fixture
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / ".pub-cache"
    monkeypatch.setattr(scan_cache_pub, "PUB_CACHE", root)
    monkeypatch.setattr(scan_cache_pub, "SRC", tmp_path / "src")
    (tmp_path / "src").mkdir()
    return root


# --- license text recognition ----------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (MIT, "MIT"),
        (BSD3, "BSD-3-Clause"),
        ("Redistribution and use in source and binary forms, are permitted", "BSD-2-Clause"),
        ("Redistribution and use in source and binary forms... 3. All advertising materials", "BSD-4-Clause"),
        ("GNU GENERAL PUBLIC LICENSE\n Version 3, 29 June 2007\n", "GPL-3.0"),
        ("GNU LESSER GENERAL PUBLIC LICENSE\n Version 2.1, February 1999\n", "LGPL-2.1"),
        ("GNU GENERAL PUBLIC LICENSE\n(no version line)\n", "GPL"),
        ("Apache License\nVersion 2.0, January 2004\n", "Apache-2.0"),
        (SYNCFUSION, "LicenseRef-Syncfusion-Community-or-commercial"),
        ("# CC0 1.0 Universal\n\nStatement of Purpose\n", "CC0-1.0"),
        ("Boost Software License - Version 1.0\n", "BSL-1.0"),
        ("## Some Odd License\n", "Some Odd License"),
        ("TODO: Add your license here.\n", ""),
        ("   \n", ""),
    ],
)
def test_recognise(text: str, expected: str) -> None:
    assert recognise(text) == expected


def test_resolve_own_license_file(tmp_path: Path) -> None:
    write(tmp_path / "p/LICENSE", MIT)
    assert resolve(tmp_path / "p", tmp_path / "p") == ("MIT", "LICENSE file")


def test_resolve_prefers_license_over_copying_and_follows_pointer(tmp_path: Path) -> None:
    write(tmp_path / "p/COPYING", "GNU GENERAL PUBLIC LICENSE\nVersion 2\n")
    write(tmp_path / "p/LICENSE", "See UNLICENSE file.\n")
    write(tmp_path / "p/UNLICENSE", "This is free and unencumbered software released into the public domain.")
    assert resolve(tmp_path / "p", tmp_path / "p") == ("Unlicense", "LICENSE file -> UNLICENSE")


def test_resolve_pointer_to_missing_file_keeps_pointer_text(tmp_path: Path) -> None:
    write(tmp_path / "p/LICENSE", "See NOPE file.\n")
    assert resolve(tmp_path / "p", tmp_path / "p") == ("See NOPE file.", "LICENSE file")


def test_resolve_skips_placeholder_and_walks_to_checkout_root(tmp_path: Path) -> None:
    write(tmp_path / "repo/LICENSE", MIT)
    write(tmp_path / "repo/packages/a/LICENSE", "TODO: Add your license here.\n")
    lic, where = resolve(tmp_path / "repo/packages/a", tmp_path / "repo")
    assert (lic, where) == ("MIT", "../../LICENSE file")


def test_resolve_readme_license_line(tmp_path: Path) -> None:
    write(tmp_path / "p/README.md", "# p\n\nThis project is licensed under the MIT License.\n")
    assert resolve(tmp_path / "p", tmp_path / "p") == ("MIT", "README.md")


def test_resolve_nothing_names_every_place_checked(tmp_path: Path) -> None:
    write(tmp_path / "repo/a/README.md", "# a\nno words here\n")
    write(tmp_path / "repo/a/LICENSE", "TODO: Add your license here.\n")
    lic, where = resolve(tmp_path / "repo/a", tmp_path / "repo")
    assert lic == ""
    assert "LICENSE/COPYING/UNLICENSE" in where
    assert "repo/a, repo" in where
    assert "placeholder" in where
    assert "README.md" in where
    assert "no license field" in where


def test_read_is_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scan_cache_pub_license, "MAX_READ", 5)
    assert scan_cache_pub_license.read(write(tmp_path / "f", "0123456789")) == "01234"


# --- whole scan ---------------------------------------------------------------


def test_scan_hosted_and_git_merged_by_name(cache: Path, tmp_path: Path) -> None:
    hosted = cache / "hosted/pub.dev"
    pkg(hosted / "http-1.0.0", "http", "1.0.0", extra="dependencies:\n  meta: any\n")
    pkg(hosted / "http-1.2.0", "http", "1.2.0", BSD3, extra="repository: https://github.com/dart-lang/http\n")
    pkg(hosted / "meta-1.0.0", "meta", "1.0.0", SYNCFUSION)
    write(hosted / ".cache/meta-versions.json", "{}")
    (hosted / "junk-0.1").mkdir()  # no pubspec: name/version from the dir name
    write(hosted / "junk-0.1/LICENSE", MIT)
    write(hosted / "pre_rel-1.0.0-dev.1/LICENSE", MIT)  # no pubspec, pre-release version
    pkg(cache / "hosted/pub.example.com/priv-2.0.0", "priv", "2.0.0")
    git = cache / "git"
    write(git / "cache/dio-abc/config", '[remote "origin"]\n\turl = https://github.com/cfug/dio.git\n')
    co = git / "dio-bcf81dc13a0ebb67fef3b4ac0b1885fc583106f5"
    write(co / "LICENSE", MIT)
    write(co / "pubspec.yaml", "name: dio_workspace\n")  # workspace root: no version, skipped
    write(co / ".git/config", f'[remote "origin"]\n\turl = {git / "cache/dio-abc"}\n')
    pkg(co / "dio", "http", "1.2.0", None)
    pkg(co / "dio/example", "http_example", "0.0.1", None)
    pkg(co / "plugins/cookie_manager", "dio_cookie_manager", "3.0.0", None)
    co2 = git / "dio-1111111111111111111111111111111111111111"
    write(co2 / "LICENSE", MIT)
    pkg(co2 / "dio", "http", "1.2.0", None)  # same version+license as co: one entry
    write(tmp_path / "src/app/pubspec.lock", "packages:\n  http:\n    source: git\n  meta:\n    x: y\n")
    write(tmp_path / "src/other/sub/pubspec.lock", "packages:\n  http:\n    source: hosted\n")

    items = {i.name: i for i in scan_cache_pub.scan_pub_cache()}

    assert set(items) == {"http", "meta", "junk", "pre_rel", "priv", "dio_cookie_manager"}
    assert items["pre_rel"].version == "1.0.0-dev.1"
    http = items["http"]
    assert http.source == "pub-cache"
    assert http.version == "1.2.0 (git), 1.2.0, 1.0.0"
    assert http.url == "https://github.com/dart-lang/http"
    assert http.requiredBy == ["~/src/app", "~/src/other"]
    # 1.0.0 depends on non-free meta, but only the newest version's deps taint.
    assert http.verdict == "foss"
    meta = items["meta"]
    assert meta.verdict == "nonfree"
    assert meta.license == "LicenseRef-Syncfusion-Community-or-commercial"
    assert not meta.reason.startswith("unrecognised")
    assert meta.url == "https://pub.dev/packages/meta"
    assert items["junk"].version == "0.1"
    assert items["priv"].url == "https://pub.example.com/packages/priv"
    assert "license from ../../LICENSE file" in items["dio_cookie_manager"].note
    assert items["dio_cookie_manager"].url == "https://github.com/cfug/dio"


def test_git_remote_direct_ssh_and_missing(cache: Path) -> None:
    direct = write(cache / "git/a-1/.git/config", "[remote]\n  url = https://gitlab.com/x/a\n").parents[1]
    ssh = write(cache / "git/b-1/.git/config", "[remote]\n  url = git@github.com:x/b.git\n").parents[1]
    bare = write(cache / "git/c-1/.git/config", "[core]\n").parents[1]
    assert scan_cache_pub.git_remote(direct) == "https://gitlab.com/x/a"
    assert scan_cache_pub.git_remote(ssh) == ""
    assert scan_cache_pub.git_remote(bare) == ""
    assert scan_cache_pub.git_remote(cache / "git/none") == ""


def test_scan_newest_dep_on_nonfree_is_partial(cache: Path) -> None:
    hosted = cache / "hosted/pub.dev"
    pkg(hosted / "app-2.0.0", "app", "2.0.0", extra="dependencies:\n  bad: any\n")
    pkg(hosted / "bad-1.0.0", "bad", "1.0.0", SYNCFUSION)
    items = {i.name: i for i in scan_cache_pub.scan_pub_cache()}
    assert items["app"].verdict == "foss-partial"


def test_scan_unlicensed_package_says_where_it_looked(cache: Path) -> None:
    pkg(cache / "git/hetu_std-577ad115dce0514afc53e2b3ab7b96bcd88d3be3", "hetu_std", "1.0.0", None)
    (item,) = scan_cache_pub.scan_pub_cache()
    assert (item.verdict, item.license) == ("nonfree", "")
    assert "no license field" in item.reason
    assert item.version == "1.0.0 (git)"


def test_scan_without_cache_is_empty(cache: Path) -> None:
    assert scan_cache_pub.scan_pub_cache() == []


def test_pub_cache_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PUB_CACHE", str(tmp_path / "pc"))
    assert scan_cache_pub.default_pub_cache() == tmp_path / "pc"
    monkeypatch.delenv("PUB_CACHE")
    assert scan_cache_pub.default_pub_cache() == Path.home() / ".pub-cache"
