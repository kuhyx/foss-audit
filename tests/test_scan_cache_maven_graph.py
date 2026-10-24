"""The cached POM graph removal walks: runtime deps of every version, plus <parent> POMs."""

from __future__ import annotations

from pathlib import Path

from foss_audit.cache_common import CachedArtifact, CachedVersion
from foss_audit.scan_cache_maven_graph import dependency_graph
from foss_audit.scan_cache_maven_remove import cache_dirs
from foss_audit.scan_cache_maven_resolve import VersionFiles
from tests.maven_helpers import gradle_file, m2_file, pom


def test_graph_unions_versions_and_adds_parents(tmp_path: Path) -> None:
    child, newer = ("org.x", "child", "1"), ("org.x", "child", "2")
    path = gradle_file(tmp_path, child, "child-1.pom", pom(child, parent=("org.x", "parent", "3")))
    broken = gradle_file(tmp_path, newer, "child-2.pom", b"<not xml")
    versions_of = [CachedVersion("1", "", "", ("org.y:a",)), CachedVersion("2", "", "", ("org.y:b",))]
    arts = [
        CachedArtifact("org.x:child", versions_of),
        CachedArtifact("org.x:parent", [CachedVersion("3", "", "")]),
    ]
    versions = {child: VersionFiles(poms=[path]), newer: VersionFiles(poms=[broken])}
    assert dependency_graph(arts, versions) == {
        "org.x:child": {"org.y:a", "org.y:b", "org.x:parent"},
        "org.x:parent": set(),
    }


def test_cache_dirs_per_root(tmp_path: Path) -> None:
    gradle, m2 = tmp_path / "files-2.1", tmp_path / "repository"
    gav, two, only = ("org.x", "lib", "1"), ("org.x", "lib", "2"), ("org.x", "only", "1")
    versions = {
        gav: VersionFiles(
            poms=[gradle_file(gradle, gav, "lib-1.pom", b"")], archives=[m2_file(m2, gav, ".jar", b"")]
        ),
        two: VersionFiles(archives=[m2_file(m2, two, ".jar", b"")]),
        only: VersionFiles(archives=[m2_file(m2, only, ".aar", b"")]),
    }
    assert cache_dirs(versions, gradle, m2) == {
        "org.x:lib": [gradle / "org.x/lib", m2 / "org/x/lib"],
        "org.x:only": [m2 / "org/x/only"],
    }
