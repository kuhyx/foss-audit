"""A cache's verdict is scored on the versions ~/src builds reach, not on stale cached ones."""

from __future__ import annotations

from pathlib import Path

from foss_audit import scan_cache_maven
from foss_audit.cache_common import CachedArtifact, CachedVersion, artifact_item, to_items
from foss_audit.scan_cache_maven_decl import Decl

JSON_LICENSE = "The JSON License"


def org_json() -> CachedArtifact:
    versions = [("20240303", "Public Domain"), ("20180813", JSON_LICENSE), ("20160810", JSON_LICENSE)]
    return CachedArtifact("org.json:json", [CachedVersion(v, lic, "pom") for v, lic in versions])


def test_stale_nonfree_versions_do_not_drive_the_verdict() -> None:
    item = artifact_item("maven-cache", org_json(), ["~/src/app"], in_use=frozenset({"20240303"}))
    assert (item.verdict, item.license) == ("foss", "Public Domain")
    assert item.version == "20240303, 20180813, 20160810"
    # Stale versions stay visible as evidence.
    assert "20180813 The JSON License" in item.note
    assert "not scored: 20180813, 20160810" in item.note


def test_a_nonfree_version_in_use_still_wins() -> None:
    item = artifact_item("maven-cache", org_json(), [], in_use=frozenset({"20240303", "20180813"}))
    assert item.verdict == "nonfree"
    assert item.reason.startswith("20180813: ")


def test_unknown_or_unmatched_use_scores_every_cached_version() -> None:
    assert artifact_item("maven-cache", org_json(), []).verdict == "nonfree"
    assert artifact_item("maven-cache", org_json(), [], in_use=frozenset({"1.0"})).verdict == "nonfree"


def test_to_items_takes_the_in_use_map_per_package() -> None:
    items = to_items(
        "maven-cache", [org_json()], {}, in_use={"org.json:json": {"20240303"}, "other:x": {"1"}}
    )
    assert items[0].verdict == "foss"


def decl(text: str, project: str = "~/src/app") -> Decl:
    return Decl(project, Path("build.gradle.kts"), 1, text, "delete")


def test_used_versions_come_from_explicit_declared_versions() -> None:
    decls = {
        "org.json:json": [
            decl('    testImplementation("org.json:json:20240303")'),
            decl('api("org.json:json")'),
        ],
        "g:a": [decl('implementation("g:a:1.0")'), decl("implementation(libs.a)")],
        "g:b": [decl('implementation("g:b")')],
        "g:c": [decl('implementation("g:other:9"); implementation("g:c:2.0")')],
    }
    assert scan_cache_maven.used_versions(decls) == {
        "org.json:json": {"20240303"},
        "g:a": {"1.0"},
        "g:c": {"2.0"},
    }
