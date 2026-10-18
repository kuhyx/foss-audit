"""Maven fallbacks after a version's own data: other versions, group siblings, the plugin portal."""

from __future__ import annotations

from pathlib import Path

import pytest

from foss_audit import scan_cache_maven_portal as portal
from foss_audit import upstream_license
from foss_audit.cache_common import CachedArtifact, CachedVersion
from foss_audit.scan_cache_maven_inherit import borrow
from foss_audit.scan_cache_maven_resolve import VersionFiles
from tests.maven_helpers import offline, write, zip_bytes


def art(name: str, *versions: tuple[str, str]) -> CachedArtifact:
    return CachedArtifact(
        name, [CachedVersion(v, lic, "pom" if lic else "pom (no <licenses>)") for v, lic in versions]
    )


def got(artifact: CachedArtifact, version: str) -> tuple[str, str]:
    cv = next(v for v in artifact.versions if v.version == version)
    return cv.license, cv.license_from


# --- b: another version of the same artifact ---------------------------------------


def test_nearest_newer_licensed_version_wins() -> None:
    lib = art("g:lib", ("0.9", "GPL-3.0"), ("1.0", ""), ("1.5", ""), ("2.0", "MIT"), ("3.0", "Apache-2.0"))
    borrow([lib])
    assert got(lib, "1.0") == ("MIT", "license of 2.0, not 1.0 (pom); 1.0 itself: pom (no <licenses>)")
    assert got(lib, "1.5")[0] == "MIT"
    assert got(lib, "0.9") == ("GPL-3.0", "pom")


def test_older_version_when_no_newer_one_has_a_license() -> None:
    lib = art("g:lib", ("0.1.0-rc2", ""), ("0.0.9", "MIT"), ("0.0.1", "GPL-3.0"))
    borrow([lib])
    assert got(lib, "0.1.0-rc2")[1].startswith("license of 0.0.9, not 0.1.0-rc2")


# --- c: a sibling artifact in the same group -----------------------------------------


def test_sibling_of_the_same_version_first_then_nearest_newer() -> None:
    lone = art("org.slf4j:jcl-over-slf4j", ("1.5.6", ""))
    same = art("org.slf4j:slf4j-api", ("1.5.6", ""), ("1.7.5", "MIT"))
    other = art("org.slf4j:slf4j-ext", ("1.5.6", "MIT License"))
    borrow([lone, same, other, art("org.other:x", ("1.5.6", "Proprietary"))])
    assert got(lone, "1.5.6") == (
        "MIT License",
        "license of org.slf4j:slf4j-ext 1.5.6 (pom); 1.5.6 itself: pom (no <licenses>)",
    )
    # b runs first: the artifact's own newer version beats any sibling.
    assert got(same, "1.5.6")[1].startswith("license of 1.7.5, not 1.5.6")


def test_sibling_nearest_older_and_name_order() -> None:
    lone = art("g:a", ("2.0", ""))
    borrow([lone, art("g:c", ("1.0", "MIT")), art("g:b", ("1.5", "MIT"), ("0.5", "MIT"))])
    assert got(lone, "2.0")[1].startswith("license of g:b 1.5 (pom)")


def test_siblings_that_disagree_lend_nothing() -> None:
    lone = art("com.google.android.gms:x", ("1", ""))
    borrow(
        [
            lone,
            art("com.google.android.gms:y", ("1", "Apache-2.0")),
            art("com.google.android.gms:z", ("1", "Android Software Development Kit License")),
        ]
    )
    lic, where = got(lone, "1")
    assert lic == ""
    assert where.endswith(
        "no other version of it declares one; com.google.android.gms siblings disagree"
        " (com.google.android.gms:y 1 Apache-2.0,"
        " com.google.android.gms:z 1 Android Software Development Kit License)"
    )


def test_nothing_to_borrow_says_where_it_looked() -> None:
    lone = art("g:a", ("1", ""), ("2", ""))
    borrow([lone, art("h:b", ("1", "MIT"))])
    assert got(lone, "1") == (
        "",
        "pom (no <licenses>); no other version of it declares one; no g sibling declares one",
    )


# --- d: a Gradle plugin's source repository, from the plugin portal -------------------

PAGE = "https://plugins.gradle.org/plugin/com.x.plugin"
HTML = (
    b'<p class="website"><a id="website" href="https://example.org/x">site</a></p>'
    b'<p class="vcs">Sources:\n  <a id="vcsUrl" href="https://github.com/x/X">https://github.com/x/X</a></p>'
)


@pytest.fixture
def plugin(tmp_path: Path) -> tuple[CachedArtifact, dict[tuple[str, str, str], VersionFiles]]:
    jar = write(
        tmp_path / "x-plugin-1.0.jar",
        zip_bytes(
            {"META-INF/gradle-plugins/com.x.plugin.properties": b"implementation-class=X", "X.class": b""}
        ),
    )
    files = {("com.x.plugin", "x-plugin", "1.0"): VersionFiles(archives=[jar])}
    return art("com.x.plugin:x-plugin", ("1.0", "")), files


def test_plugin_ids_from_the_jar(tmp_path: Path) -> None:
    jar = write(
        tmp_path / "a.jar", zip_bytes({"META-INF/gradle-plugins/a.b.properties": b"", "META-INF/x": b""})
    )
    assert portal.plugin_ids([tmp_path / "missing.jar", write(tmp_path / "bad.jar", b"no zip"), jar]) == [
        "a.b"
    ]


def test_source_link_prefers_the_vcs_url() -> None:
    assert portal.source_link(HTML) == "https://github.com/x/X"
    assert (
        portal.source_link(b'<a id="website" href="https://gitlab.com/o/r/-/tree/main">')
        == "https://gitlab.com/o/r"
    )
    assert portal.source_link(b'<a id="website" href="https://example.org/x">') == ""


def test_plugin_takes_its_portal_source_repository_license(
    plugin: tuple[CachedArtifact, dict[tuple[str, str, str], VersionFiles]], monkeypatch: pytest.MonkeyPatch
) -> None:
    lib, files = plugin
    asked = offline(monkeypatch, {PAGE: HTML})
    repos: list[str] = []

    def fake(url: str, ref: str = "") -> tuple[str, str]:
        repos.append(url)
        return "Apache-2.0", f"upstream {url} HEAD: LICENSE file"

    monkeypatch.setattr(upstream_license, "upstream_license", fake)
    portal.fill([lib, art("g:licensed", ("1", "MIT"))], files)
    assert (asked, repos) == ([PAGE], ["https://github.com/x/X"])
    assert got(lib, "1.0") == (
        "Apache-2.0",
        f"gradle plugin portal {PAGE} sources -> upstream https://github.com/x/X HEAD: LICENSE file"
        " (default branch, not 1.0); 1.0 itself: pom (no <licenses>)",
    )


@pytest.mark.parametrize(
    ("pages", "answer", "tail"),
    [
        ({}, ("", ""), f"gradle plugin portal {PAGE}: fetch failed: offline {PAGE}"),
        ({PAGE: b"<html/>"}, ("", ""), f"gradle plugin portal {PAGE} (no source repository link)"),
        (
            {PAGE: HTML},
            ("", "upstream https://github.com/x/X HEAD: no license file"),
            f"gradle plugin portal {PAGE} sources -> upstream https://github.com/x/X HEAD: no license file",
        ),
    ],
)
def test_plugin_portal_misses_are_listed(
    plugin: tuple[CachedArtifact, dict[tuple[str, str, str], VersionFiles]],
    monkeypatch: pytest.MonkeyPatch,
    pages: dict[str, bytes],
    answer: tuple[str, str],
    tail: str,
) -> None:
    lib, files = plugin
    offline(monkeypatch, pages)
    monkeypatch.setattr(upstream_license, "upstream_license", lambda url, ref="": answer)
    portal.fill([lib], files)
    assert got(lib, "1.0") == ("", f"pom (no <licenses>); {tail}")


def test_not_a_plugin_is_not_looked_up(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = offline(monkeypatch)
    lib = art("g:a", ("1", ""))
    portal.fill([lib], {})
    assert asked == []
    assert got(lib, "1") == ("", "pom (no <licenses>)")


def test_a_failed_fetch_borrows_nothing(
    plugin: tuple[CachedArtifact, dict[tuple[str, str, str], VersionFiles]], monkeypatch: pytest.MonkeyPatch
) -> None:
    lib, files = plugin
    lib.versions[0].license_from = "pom (license fetch failed: offline)"
    asked = offline(monkeypatch)
    borrow([lib, art("com.x.plugin:sibling", ("1.0", "MIT"))])
    portal.fill([lib], files)
    assert asked == []
    assert got(lib, "1.0") == ("", "pom (license fetch failed: offline)")
