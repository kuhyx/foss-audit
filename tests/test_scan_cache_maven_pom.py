"""POM parsing and JAR/AAR license lookup of the Maven cache scanner."""

from __future__ import annotations

from pathlib import Path

import pytest

from foss_audit import scan_cache_maven_jar as jar
from foss_audit.scan_cache_maven_pom import gav_name, header_license, parse_pom, pom_path
from tests.maven_helpers import APACHE_TEXT, NS, dep, pom, write, zip_bytes


def test_parse_pom_rejects_invalid_xml() -> None:
    assert parse_pom(b"<project") is None


@pytest.mark.parametrize("ns", [True, False])
def test_licenses_with_and_without_namespace(ns: bool) -> None:
    data = pom(licenses=(("MIT", "u"), ("", "https://x/l")), body="<licenses/>")
    got = parse_pom(data if ns else data.replace(NS.encode(), b""))
    assert got is not None
    assert got.licenses == ("MIT", "https://x/l")
    assert got.unnamed_urls == ("https://x/l",)


def test_empty_license_element_is_skipped() -> None:
    got = parse_pom(pom(licenses=(("", ""),)))
    assert got is not None
    assert got.licenses == ()


def test_runtime_deps_and_properties() -> None:
    deps = "".join(
        [
            dep("${project.groupId}", "core"),
            dep("x", "${lib.name}", extra="<scope>runtime</scope>"),
            dep("x", "c", extra="<scope>compile</scope>"),
            dep("x", "t", extra="<scope>test</scope>"),
            dep("x", "o", extra="<optional>true</optional>"),
            dep("${unknown}", "skip"),
            "<dependency><artifactId>nogroup</artifactId></dependency>",
            dep("x", "c"),
        ]
    )
    body = f"<properties><lib.name>lib</lib.name><empty/></properties><dependencies>{deps}</dependencies>"
    got = parse_pom(pom(("org.g", "a", "1"), body=body))
    assert got is not None
    assert got.deps == ("org.g:core", "x:lib", "x:c")
    assert got.group == "org.g"
    assert got.marker is None


def test_group_and_parent_inherited() -> None:
    data = b"<project><parent><groupId>p</groupId><artifactId>pa</artifactId><version>2</version></parent>"
    data += b"<artifactId>a</artifactId><scm><url>https://github.com/o/r</url></scm></project>"
    got = parse_pom(data)
    assert got is not None
    assert got.parent == ("p", "pa", "2")
    assert got.group == "p"
    assert got.source_urls == ("https://github.com/o/r",)


@pytest.mark.parametrize("version", ["${revision}", ""])
def test_unresolvable_parent_is_dropped(version: str) -> None:
    got = parse_pom(pom(parent=("p", "pa", version)))
    assert got is not None
    assert got.parent is None


def test_plugin_marker_points_at_its_one_dependency() -> None:
    body = f"<packaging>pom</packaging><dependencies>{dep('o', 'plugin', '3')}</dependencies>"
    got = parse_pom(pom(("o.id", "o.id.gradle.plugin", "3"), body=body))
    assert got is not None
    assert got.marker == ("o", "plugin", "3")


@pytest.mark.parametrize(
    "deps", [dep("o", "p", "") + "", dep("o", "p") + dep("o", "q")], ids=["no-version", "two-deps"]
)
def test_marker_needs_exactly_one_versioned_dependency(deps: str) -> None:
    got = parse_pom(pom(("o", "o.gradle.plugin", "3"), body=f"<dependencies>{deps}</dependencies>"))
    assert got is not None
    assert got.marker is None


def test_header_license() -> None:
    assert header_license(pom(header=f"<!-- {APACHE_TEXT} -->")) == "Apache-2.0"
    assert header_license(pom(header="<!-- generated -->")) == ""
    assert header_license(pom()) == ""


def test_paths_and_names() -> None:
    assert pom_path(("a.b", "c", "1")) == "a/b/c/1/c-1.pom"
    assert gav_name(("a", "b", "1")) == "a:b:1"


def archive(tmp_path: Path, name: str, entries: dict[str, bytes]) -> Path:
    return write(tmp_path / name, zip_bytes(entries))


def test_embedded_pom_of_this_artifact_wins(tmp_path: Path) -> None:
    other = "META-INF/maven/x/shaded/pom.xml"
    own = "META-INF/maven/g/a/pom.xml"
    path = archive(
        tmp_path, "a.jar", {other: pom(licenses=(("GPL", ""),)), own: pom(licenses=(("MIT", ""),))}
    )
    assert jar.archive_license([path], "g", "a") == ("MIT", "embedded pom in a.jar")


def test_license_file_then_notice(tmp_path: Path) -> None:
    entries = {
        "META-INF/maven/g/a/pom.xml": b"<broken",
        "lib/LICENSE": b"bundled, ignored",
        "NOTICE": APACHE_TEXT.encode(),
        "META-INF/LICENSE.txt": b"Custom terms\n",
    }
    path = archive(tmp_path, "a.jar", entries)
    assert jar.archive_license([path], "g", "a") == ("Apache-2.0", "NOTICE in a.jar")


def test_nothing_found_lists_every_place(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jar, "MAX_ENTRY", 20)
    big = archive(tmp_path, "big.jar", {"LICENSE": b"x" * 50, "COPYING": b"Custom terms"})
    bare = archive(tmp_path, "bare.jar", {"META-INF/maven/g/a/pom.xml": pom()})
    bad = write(tmp_path / "bad.jar", b"not a zip")
    lic, where = jar.archive_license([big, bare, bad], "g", "a")
    assert lic == ""
    assert where == (
        "COPYING in big.jar (unrecognised: Custom terms); LICENSE in big.jar (too large); "
        "big.jar (no embedded pom or LICENSE/NOTICE); bare.jar (no embedded pom or LICENSE/NOTICE); "
        "bad.jar unreadable (File is not a zip file)"
    )


def test_aar_classes_jar(tmp_path: Path) -> None:
    inner = zip_bytes({"META-INF/LICENSE": APACHE_TEXT.encode()})
    path = archive(tmp_path, "a.aar", {"classes.jar": inner, "R.txt": b""})
    assert jar.archive_license([path], "g", "a") == ("Apache-2.0", "META-INF/LICENSE in a.aar!classes.jar")
    outer = archive(tmp_path, "b.aar", {"classes.jar": inner, "LICENSE": APACHE_TEXT.encode()})
    assert jar.archive_license([outer], "g", "a") == ("Apache-2.0", "LICENSE in b.aar")


def test_aar_classes_jar_too_large(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jar, "MAX_NESTED", 4)
    path = archive(tmp_path, "a.aar", {"classes.jar": zip_bytes({"LICENSE": b"x"})})
    assert jar.archive_license([path], "g", "a") == (
        "",
        "a.aar!classes.jar (too large); a.aar (no embedded pom or LICENSE/NOTICE)",
    )
