"""cache_common: per-package verdicts over versions, dependency taint, project usage."""

from __future__ import annotations

from pathlib import Path

import pytest

from foss_audit import cache_common
from foss_audit.cache_common import (
    CachedArtifact,
    CachedVersion,
    artifact_item,
    fetch_cached,
    project_files,
    project_of,
    to_items,
    version_key,
)


def art(name: str, *versions: tuple[str, str], deps: tuple[str, ...] = ()) -> CachedArtifact:
    return CachedArtifact(name, [CachedVersion(v, lic, "pom", deps) for v, lic in versions])


def test_version_key_sorts_numerically() -> None:
    assert sorted(["1.10", "1.9", "1.9a"], key=version_key) == ["1.9", "1.9a", "1.10"]


def test_free_package_lists_versions_newest_first() -> None:
    item = artifact_item("maven-cache", art("g:a", ("1.9", "MIT"), ("1.10", "MIT")), ["~/src/x"])
    assert (item.verdict, item.version, item.license) == ("foss", "1.10, 1.9", "MIT")
    assert item.requiredBy == ["~/src/x"]
    assert item.note == "license from pom"


def test_worst_version_wins_and_is_named() -> None:
    item = artifact_item("maven-cache", art("g:a", ("1.0", "BUSL proprietary"), ("2.0", "MIT")), [])
    assert item.verdict == "nonfree"
    assert item.reason.startswith("1.0: ")
    assert "licenses differ by version: 2.0 MIT; 1.0 BUSL proprietary" in item.note
    assert "no ~/src lockfile" in item.note


def test_newest_nonfree_reason_is_not_prefixed() -> None:
    item = artifact_item("maven-cache", art("g:a", ("1.0", "ML Kit Terms of Service")), [])
    assert item.verdict == "nonfree"
    assert not item.reason.startswith("1.0")


def test_missing_license_says_where_it_looked() -> None:
    blank = CachedArtifact("g:a", [CachedVersion("1", "", "pom, parent g:p:1, jar META-INF")])
    item = artifact_item("maven-cache", blank, [])
    assert item.verdict == "nonfree"
    assert "checked pom, parent g:p:1, jar META-INF" in item.reason


def test_runtime_dependency_on_nonfree_makes_partial() -> None:
    items = to_items(
        "maven-cache",
        [
            art("firebase", ("1", "Apache-2.0"), deps=("gms", "firebase")),
            art("gms", ("1", "Android Software Development Kit License")),
            art("okio", ("1", "Apache-2.0"), deps=("kotlin",)),
        ],
        {"okio": {"~/src/todo"}},
    )
    by_name = {i.name: i for i in items}
    assert (by_name["firebase"].verdict, by_name["firebase"].reason) == (
        "foss-partial",
        "depends on non-free gms",
    )
    assert by_name["gms"].verdict == "nonfree"
    assert (by_name["okio"].verdict, by_name["okio"].requiredBy) == ("foss", ["~/src/todo"])


def test_project_files_bounded_and_skip_node_modules(tmp_path: Path) -> None:
    (tmp_path / "a/app").mkdir(parents=True)
    (tmp_path / "a/app/pubspec.lock").write_text("")
    (tmp_path / "a/node_modules/x").mkdir(parents=True)
    (tmp_path / "a/node_modules/x/pubspec.lock").write_text("")
    (tmp_path / "b/1/2/3/4").mkdir(parents=True)
    (tmp_path / "b/1/2/3/4/pubspec.lock").write_text("")
    (tmp_path / "c").mkdir()
    (tmp_path / "c/pubspec.lock").mkdir()
    assert project_files(["pubspec.lock"], tmp_path, 4) == [tmp_path / "a/app/pubspec.lock"]
    assert project_of(tmp_path / "a/app/pubspec.lock", tmp_path) == "~/src/a"


def test_fetch_cached_fetches_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, int]] = []

    def fake_get(url: str, timeout: int) -> bytes:
        calls.append((url, timeout))
        return b"<pom/>"

    monkeypatch.setattr(cache_common.http_fetch, "get", fake_get)
    assert fetch_cached("https://x/a.pom", tmp_path) == b"<pom/>"
    assert fetch_cached("https://x/a.pom", tmp_path) == b"<pom/>"
    assert calls == [("https://x/a.pom", cache_common.FETCH_TIMEOUT_S)]


# --- meta-packages: no license of their own, their dependencies agree ----------------


def blank(name: str, deps: tuple[str, ...] = (), extra: tuple[str, ...] = ()) -> CachedArtifact:
    return CachedArtifact(name, [CachedVersion("1", "", "METADATA", deps, extra, meta=True)])


def test_meta_package_takes_the_license_its_dependencies_agree_on() -> None:
    items = to_items(
        "pip-cache",
        [
            blank("meta", deps=("a",), extra=("b", "c", "not-cached")),
            art("a", ("1", "NVIDIA Proprietary Software")),
            art("b", ("1", "LicenseRef-NVIDIA-Proprietary")),
            art("c", ("1", "NVIDIA Proprietary Software")),
        ],
        {},
    )
    meta = {i.name: i for i in items}["meta"]
    assert (meta.verdict, meta.license) == ("nonfree", "NVIDIA Proprietary Software")
    assert "license from its dependencies a, b, c (declares none itself; checked METADATA)" in meta.note
    assert "no license" not in meta.reason


def test_meta_package_names_at_most_five_dependencies() -> None:
    deps = tuple(f"d{n}" for n in range(7))
    items = to_items("pip-cache", [blank("meta", deps), *(art(d, ("1", "MIT")) for d in deps)], {})
    meta = {i.name: i for i in items}["meta"]
    assert meta.license == "MIT"
    assert "from its dependencies d0, d1, d2, d3, d4 and 2 more (declares" in meta.note


def test_dependencies_that_disagree_lend_the_worst_verdict_and_every_license() -> None:
    # cuda-toolkit: ten NVIDIA-proprietary dependencies and one Apache one.
    nvidia = [f"nvidia-{n}" for n in "abc"]
    items = to_items(
        "pip-cache",
        [
            blank("meta", extra=(*nvidia, "nvidia-nvtx")),
            *(art(d, ("1", "NVIDIA Proprietary Software")) for d in nvidia),
            art("nvidia-nvtx", ("1", "Apache 2.0")),
        ],
        {},
    )
    meta = {i.name: i for i in items}["meta"]
    assert (meta.verdict, meta.license) == ("nonfree", "NVIDIA Proprietary Software + Apache 2.0")
    assert meta.reason == "NVIDIA Proprietary Software"
    assert (
        "license from its dependencies nvidia-a, nvidia-b, nvidia-c, nvidia-nvtx (declares none itself; "
        "checked METADATA)" in meta.note
    )


def test_a_mixed_inheritance_is_not_passed_on_by_a_free_package() -> None:
    # The worst verdict is the meta-package's own; a package that depends on it is tainted as usual.
    items = to_items(
        "pip-cache",
        [
            blank("meta", extra=("a", "b")),
            art("a", ("1", "Proprietary")),
            art("b", ("1", "MIT")),
            art("user", ("1", "MIT"), deps=("meta",)),
        ],
        {},
    )
    by = {i.name: i for i in items}
    assert (by["meta"].verdict, by["meta"].license) == ("nonfree", "Proprietary + MIT")
    assert (by["user"].verdict, by["user"].reason) == ("foss-partial", "depends on non-free meta")


@pytest.mark.parametrize("dep_license", ["", "UNKNOWN", "Copyright Someone"])
def test_an_unknown_dependency_blocks_inheritance(dep_license: str) -> None:
    items = to_items(
        "pip-cache", [blank("meta", ("a", "b")), art("a", ("1", "MIT")), art("b", ("1", dep_license))], {}
    )
    meta = {i.name: i for i in items}["meta"]
    assert meta.license == ""
    assert meta.reason.endswith("checked METADATA; dependency b has no known license")


def test_no_cached_dependency_means_nothing_to_inherit() -> None:
    items = to_items("pip-cache", [blank("meta", ("gone", "meta")), blank("solo")], {})
    assert {i.reason for i in items} == {"no license (all rights reserved); checked METADATA"}


def test_an_inherited_license_is_not_passed_on() -> None:
    items = to_items(
        "pip-cache", [blank("top", ("mid",)), blank("mid", ("leaf",)), art("leaf", ("1", "MIT"))], {}
    )
    by_name = {i.name: i for i in items}
    assert by_name["mid"].license == "MIT"
    assert by_name["top"].license == ""
    assert by_name["top"].reason.endswith("dependency mid has no known license")


def test_a_package_that_ships_code_never_inherits() -> None:
    code = CachedArtifact("tkwidgets", [CachedVersion("1", "", "package.json", ("chalk",))])
    items = to_items("npm-cache", [code, art("chalk", ("1", "MIT"))], {})
    assert {i.name: i for i in items}[
        "tkwidgets"
    ].reason == "no license (all rights reserved); checked package.json"
