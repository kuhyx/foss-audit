"""Maven artifacts in the Gradle cache and the Maven local repository.

Both caches are merged into one `group:artifact` list:
~/.gradle/caches/modules-2/files-2.1/<group>/<artifact>/<version>/<sha1>/<file>
and ~/.m2/repository/<group path>/<artifact>/<version>/<artifact>-<version>.*.
Every version with a POM or a JAR/AAR counts, POM-only BOMs and parents
included: they were downloaded too. The license lookup per version lives in
scan_cache_maven_resolve; `requiredBy` comes from the build files, version
catalogs and pom.xml of ~/src projects (scan_cache_maven_decl), and the
remove command from scan_cache_maven_remove.
"""

from __future__ import annotations

from pathlib import Path

from foss_audit import cache_common
from foss_audit.cache_common import CachedArtifact, CachedVersion, to_items
from foss_audit.memo import NO_MEMO, Memo
from foss_audit.model import Item
from foss_audit.scan_cache_maven_decl import declarations
from foss_audit.scan_cache_maven_graph import dependency_graph
from foss_audit.scan_cache_maven_inherit import borrow
from foss_audit.scan_cache_maven_pom import Gav
from foss_audit.scan_cache_maven_portal import fill
from foss_audit.scan_cache_maven_remove import add_removals, cache_dirs
from foss_audit.scan_cache_maven_repos import recorded_repos
from foss_audit.scan_cache_maven_resolve import Store, VersionFiles, resolve_all

HOME = Path.home()
GRADLE = HOME / ".gradle/caches/modules-2/files-2.1"
M2 = HOME / ".m2/repository"
SRC = cache_common.SRC
ARCHIVE_SUFFIXES = frozenset({".jar", ".aar"})


def _add(found: dict[Gav, VersionFiles], gav: Gav, path: Path) -> None:
    files = found.setdefault(gav, VersionFiles())
    if path.suffix == ".pom":
        files.poms.append(path)
    elif path.suffix == ".module":
        files.modules.append(path)
    elif path.suffix in ARCHIVE_SUFFIXES:
        files.archives.append(path)


def gradle_files(root: Path, found: dict[Gav, VersionFiles]) -> None:
    """<group>/<artifact>/<version>/<sha1>/<file> of the Gradle cache."""
    for path in sorted(root.glob("*/*/*/*/*")):
        if path.is_file():
            group, artifact, version = path.parts[-5:-2]
            _add(found, (group, artifact, version), path)


def m2_files(root: Path, found: dict[Gav, VersionFiles]) -> None:
    """<group path>/<artifact>/<version>/<artifact>-<version>* of ~/.m2."""
    for path in sorted(root.rglob("*")):
        parts = path.relative_to(root).parts
        if len(parts) >= 4 and path.is_file() and path.name.startswith(f"{parts[-3]}-{parts[-2]}"):
            _add(found, (".".join(parts[:-3]), parts[-3], parts[-2]), path)


def _archive_order(path: Path) -> tuple[bool, str]:
    """Main artifact first; -sources/-javadoc jars last."""
    return (path.stem.endswith(("-sources", "-javadoc")), path.name)


def cached_versions() -> dict[Gav, VersionFiles]:
    """Every cached version of both caches, merged."""
    found: dict[Gav, VersionFiles] = {}
    if GRADLE.is_dir():
        gradle_files(GRADLE, found)
    if M2.is_dir():
        m2_files(M2, found)
    for files in found.values():
        files.archives.sort(key=_archive_order)
    return {gav: files for gav, files in found.items() if files.poms or files.archives}


def artifacts(versions: dict[Gav, VersionFiles], readings: Memo = NO_MEMO) -> list[CachedArtifact]:
    """One CachedArtifact per group:artifact, licenses resolved per version."""
    repos = recorded_repos(GRADLE.parent, {(g, a) for g, a, _ in versions})
    results = resolve_all(Store(versions, repos, readings=readings), sorted(versions))
    readings.save()
    arts: dict[str, CachedArtifact] = {}
    for (group, artifact, version), found in sorted(results.items()):
        name = f"{group}:{artifact}"
        art = arts.setdefault(
            name, CachedArtifact(name, url=f"https://mvnrepository.com/artifact/{group}/{artifact}")
        )
        art.versions.append(CachedVersion(version, found.license, found.license_from, found.deps))
    # Still blank after the version's own data: other versions, siblings, the plugin portal.
    borrow(list(arts.values()))
    fill(list(arts.values()), versions)
    return list(arts.values())


def scan_maven_cache() -> list[Item]:
    """One Item per group:artifact cached by Gradle or Maven, each with a removal for good."""
    versions = cached_versions()
    arts = artifacts(versions, Memo.for_source("maven-cache"))
    decls = declarations(SRC)
    items = to_items("maven-cache", arts, {name: {d.project for d in found} for name, found in decls.items()})
    add_removals(items, decls, dependency_graph(arts, versions), cache_dirs(versions, GRADLE, M2))
    return items
