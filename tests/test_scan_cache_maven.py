"""scan_maven_cache: Gradle cache + ~/.m2 merged into one item per group:artifact."""

from __future__ import annotations

from pathlib import Path

import pytest

from foss_audit import scan_cache_maven as scan
from foss_audit.scan_cache_maven_decl import build_file_names
from tests.maven_helpers import dep, gradle_file, m2_file, offline, pom, write, zip_bytes

LIB = ("org.x", "lib", "1.0")
GPL = (("GPL-3.0", ""),)


@pytest.fixture
def caches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    gradle = tmp_path / ".gradle/caches/modules-2/files-2.1"
    m2 = tmp_path / ".m2/repository"
    src = tmp_path / "src"
    monkeypatch.setattr(scan, "GRADLE", gradle)
    monkeypatch.setattr(scan, "M2", m2)
    monkeypatch.setattr(scan, "SRC", src)
    return gradle, m2, src


def test_both_caches_merge(caches: tuple[Path, Path, Path]) -> None:
    gradle, m2, _ = caches
    gradle_file(gradle, LIB, "lib-1.0.pom", pom(LIB, GPL))
    gradle_file(gradle, LIB, "lib-1.0.module", b"{}")
    gradle_file(gradle, LIB, "lib-1.0-sources.jar", b"")
    gradle_file(gradle, LIB, "lib-1.0.jar", b"")
    gradle_file(gradle, LIB, "lib-1.0.so", b"")
    (gradle / "org.x/lib/1.0/0123abcd/dir").mkdir()
    gradle_file(gradle, ("org.x", "only", "1"), "only-1.module", b"{}")
    m2_file(m2, ("org.x", "lib", "2.0"), ".pom", pom(("org.x", "lib", "2.0"), GPL))
    m2_file(m2, ("org.x", "lib", "2.0"), ".aar", b"")
    m2_file(m2, LIB, ".pom", pom(LIB, GPL))
    write(m2 / "org/x/lib/2.0/_remote.repositories", b"")
    write(m2 / "org/x/lib/maven-metadata.xml", b"")
    write(m2 / "top.pom", b"")
    found = scan.cached_versions()
    assert sorted(found) == [LIB, ("org.x", "lib", "2.0")]
    assert [p.name for p in found[LIB].archives] == ["lib-1.0.jar", "lib-1.0-sources.jar"]
    assert len(found[LIB].poms) == 2
    assert [p.name for p in found[LIB].modules] == ["lib-1.0.module"]


def test_no_caches(caches: tuple[Path, Path, Path]) -> None:
    assert scan.cached_versions() == {}


def test_build_file_names() -> None:
    text = """
        implementation("org.x:lib:1.0")
        api 'org.y:other'
        compile group: 'org.z', name: 'zed', version: '1'
        id("com.android.application") version "8" apply false
        id 'org.jetbrains.kotlin.android'
        url "https://example.com/maven"
    """
    assert build_file_names(text) == {
        "org.x:lib",
        "org.y:other",
        "org.z:zed",
        "com.android.application:com.android.application.gradle.plugin",
        "org.jetbrains.kotlin.android:org.jetbrains.kotlin.android.gradle.plugin",
    }


def test_catalog_module_and_group_name() -> None:
    toml = 'a = { module = "org.x:lib", version.ref = "x" }\nb = { group = "org.z", name = "zed" }\n'
    assert build_file_names(toml) == {"org.x:lib", "org.z:zed"}


def test_scan_end_to_end(
    caches: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch, ticks: dict[str, tuple[int, int | None]]
) -> None:
    gradle, m2, src = caches
    offline(monkeypatch)
    nonfree = ("com.google.android.gms", "play-services-base", "18.0.0")
    tos = (("Android Software Development Kit License", ""),)
    gradle_file(gradle, nonfree, "play-services-base-18.0.0.pom", pom(nonfree, tos))
    body = f"<dependencies>{dep(nonfree[0], nonfree[1], nonfree[2])}</dependencies>"
    gradle_file(gradle, LIB, "lib-1.0.pom", pom(LIB, (("MIT", ""),), body=body))
    old = ("org.x", "lib", "0.9")
    gradle_file(
        gradle, old, "lib-0.9.jar", zip_bytes({"LICENSE": b"Permission is hereby granted, free of charge"})
    )
    bare = ("org.x", "bare", "1")
    m2_file(m2, bare, ".jar", zip_bytes({"a.class": b""}))
    silent = ("org.x", "silent", "1")
    m2_file(m2, silent, ".pom", pom(silent))
    write(src / "app/android/app/build.gradle.kts", b'dependencies { implementation("org.x:lib:1.0") }')
    write(src / "other/build.gradle", b"apply plugin: 'java'")
    items = {i.name: i for i in scan.scan_maven_cache()}
    assert set(items) == {
        "org.x:lib",
        "org.x:bare",
        "org.x:silent",
        "com.google.android.gms:play-services-base",
    }
    lib = items["org.x:lib"]
    assert (lib.verdict, lib.version, lib.license) == ("foss-partial", "1.0, 0.9", "MIT")
    assert lib.reason == "depends on non-free com.google.android.gms:play-services-base"
    assert lib.requiredBy == ["~/src/app"]
    assert ticks["maven-cache"][0] == ticks["maven-cache"][1] > 0
    assert lib.url == "https://mvnrepository.com/artifact/org.x/lib"
    assert items["com.google.android.gms:play-services-base"].verdict == "nonfree"
    missing = items["org.x:bare"]
    assert missing.verdict == "nonfree"
    assert missing.reason.startswith(
        "no license (all rights reserved); checked pom (license fetch failed: https://repo1"
    )
    assert "bare-1.jar (no embedded pom or LICENSE/NOTICE)" in missing.reason
    # A failed fetch is not proof of no license, so only `silent` borrows its sibling's.
    silent_item = items["org.x:silent"]
    assert (silent_item.verdict, silent_item.license) == ("foss", "MIT")
    assert "license from license of org.x:lib 1.0 (pom); 1 itself: pom (no <licenses>)" in silent_item.note
    # Every item says how to remove it for good.
    assert all(i.removeCommand for i in items.values())
    assert lib.removeVia == "~/src/app declares it"
    gms = items["com.google.android.gms:play-services-base"]
    assert gms.requiredBy == []
    assert gms.removeVia == "~/src/app via org.x:lib → com.google.android.gms:play-services-base"
    assert str(gms.removeCommand).startswith("sed -i -e ")
    assert silent_item.removeVia == "stale: no ~/src project reaches it"
    assert silent_item.removeCommand == f"rm -rf {m2 / 'org/x/silent'}"
