"""Maven artifacts in the Gradle cache and the Maven local repository.

Both caches are merged into one `group:artifact` list:
~/.gradle/caches/modules-2/files-2.1/<group>/<artifact>/<version>/<sha1>/<file>
and ~/.m2/repository/<group path>/<artifact>/<version>/<artifact>-<version>.*.
Every version with a POM or a JAR/AAR counts, POM-only BOMs and parents
included: they were downloaded too. The license lookup per version lives in
scan_cache_maven_resolve; `requiredBy` comes from the Gradle build files of
~/src projects (dependency strings, `group:, name:` maps, plugin ids).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from foss_audit import cache_common
from foss_audit.cache_common import CachedArtifact, CachedVersion, project_files, project_of, to_items
from foss_audit.model import Item
from foss_audit.scan_cache_maven_inherit import borrow
from foss_audit.scan_cache_maven_pom import Gav
from foss_audit.scan_cache_maven_portal import fill
from foss_audit.scan_cache_maven_repos import recorded_repos
from foss_audit.scan_cache_maven_resolve import Store, VersionFiles, resolve_all

HOME = Path.home()
GRADLE = HOME / ".gradle/caches/modules-2/files-2.1"
M2 = HOME / ".m2/repository"
SRC = cache_common.SRC
BUILD_FILES = (
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    "gradle/libs.versions.toml",
)
ARCHIVE_SUFFIXES = frozenset({".jar", ".aar"})
# "group:artifact" or "group:artifact:version" inside quotes.
COORD = re.compile(r"""["']([\w.\-]+):([\w.\-]+)(?::[^"'\s]*)?["']""")
GROUP_NAME = re.compile(r"""group\s*[:=]\s*["']([\w.\-]+)["']\s*,\s*name\s*[:=]\s*["']([\w.\-]+)["']""")
# A plugin id resolves through its marker artifact <id>:<id>.gradle.plugin.
PLUGIN_ID = re.compile(r"""\bid\s*[(=]?\s*["']([\w.\-]+)["']""")


def _add(found: dict[Gav, VersionFiles], gav: Gav, path: Path) -> None:
    files = found.setdefault(gav, VersionFiles())
    if path.suffix == ".pom":
        files.poms.append(path)
    elif path.suffix == ".module":
        files.module = True
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


def build_file_names(text: str) -> set[str]:
    """`group:artifact` names a Gradle build file or version catalog declares."""
    names = {f"{g}:{a}" for g, a in COORD.findall(text)}
    names |= {f"{g}:{a}" for g, a in GROUP_NAME.findall(text)}
    names |= {f"{pid}:{pid}.gradle.plugin" for pid in PLUGIN_ID.findall(text)}
    return names


def used_by_projects(wanted: Iterable[str], root: Path) -> dict[str, set[str]]:
    """name -> the ~/src projects whose Gradle files declare it."""
    want = set(wanted)
    used: dict[str, set[str]] = {}
    for path in project_files(BUILD_FILES, root=root):
        for name in build_file_names(path.read_text(errors="replace")) & want:
            used.setdefault(name, set()).add(project_of(path, root=root))
    return used


def artifacts(versions: dict[Gav, VersionFiles]) -> list[CachedArtifact]:
    """One CachedArtifact per group:artifact, licenses resolved per version."""
    repos = recorded_repos(GRADLE.parent, {(g, a) for g, a, _ in versions})
    results = resolve_all(Store(versions, repos), sorted(versions))
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
    """One Item per group:artifact cached by Gradle or Maven."""
    arts = artifacts(cached_versions())
    return to_items("maven-cache", arts, used_by_projects((a.name for a in arts), SRC))
