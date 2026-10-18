"""Dart/Flutter packages in the pub cache (~/.pub-cache, or $PUB_CACHE).

Two layouts hold package sources:
- hosted/<server>/<name>-<version>/: one dir per downloaded version (pub.dev
  and any other hosted server);
- git/<repo>-<sha>/: one checkout per git dependency ref. A checkout may be a
  monorepo, so every pubspec.yaml with a `version:` at most MAX_GIT_DEPTH dirs
  down counts as a package; workspace roots (no version) and example/test
  apps do not.

Name, version and runtime deps come from each pubspec.yaml; the license from
the package's own files (scan_cache_pub_license). Measured on kuhy's machine:
every hosted version ships a LICENSE file (pub refuses to publish without
one), so hosted packages need no network fallback. A git package whose checkout
has none falls back to its upstream repository's current license
(upstream_license: forge-agnostic, cached 30 days), and says so in license_from;
those lookups (a git fetch each) run on a bounded thread pool.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from foss_audit.cache_common import (
    SRC,
    CachedArtifact,
    CachedVersion,
    project_files,
    project_of,
    to_items,
    version_key,
)
from foss_audit.model import Item
from foss_audit.scan_cache_pub_license import read, resolve
from foss_audit.scan_cache_pub_parse import Pubspec, lock_packages, parse_pubspec
from foss_audit.upstream_license import with_upstream

MAX_GIT_DEPTH = 3
UPSTREAM_WORKERS = 16
# Sample and test apps inside a git checkout, not packages anyone depends on.
ORIGIN_URL = re.compile(r"^\s*url\s*=\s*(\S+)", re.MULTILINE)
NOT_PACKAGES = frozenset({"example", "examples", "test", "tests", "integration_test", "benchmark"})


def default_pub_cache() -> Path:
    """$PUB_CACHE when set, else ~/.pub-cache (pub's own default on Linux)."""
    return Path(os.environ.get("PUB_CACHE") or Path.home() / ".pub-cache")


PUB_CACHE = default_pub_cache()


def _dirs(parent: Path) -> list[Path]:
    """Sub-directories, minus pub's own dot-dirs (hosted/pub.dev/.cache)."""
    if not parent.is_dir():
        return []
    return sorted(p for p in parent.iterdir() if p.is_dir() and not p.name.startswith("."))


def _spec(directory: Path) -> Pubspec:
    pubspec = directory / "pubspec.yaml"
    return parse_pubspec(read(pubspec)) if pubspec.is_file() else Pubspec()


def hosted_versions() -> Iterator[tuple[Pubspec, CachedVersion, str]]:
    """(pubspec, version, fallback url) for every hosted/<server>/<name>-<version>."""
    for server in _dirs(PUB_CACHE / "hosted"):
        for directory in _dirs(server):
            spec = _spec(directory)
            # Without a pubspec, split "<name>-<version>" at the first dash: names have none.
            name, _, version = directory.name.partition("-")
            spec.name, spec.version = spec.name or name, spec.version or version
            lic, where = resolve(directory, directory)
            fallback = f"https://{server.name}/packages/{spec.name}"
            yield spec, CachedVersion(spec.version, lic, where, spec.deps), fallback


def _origin(config: Path) -> str:
    found = ORIGIN_URL.search(read(config)) if config.is_file() else None
    return found.group(1) if found else ""


def git_remote(checkout: Path) -> str:
    """The upstream URL of a checkout: its origin is pub's bare mirror in
    git/cache/, whose own origin is the real repository. Config files only."""
    origin = _origin(checkout / ".git/config")
    if Path(origin).parent == PUB_CACHE / "git/cache":
        origin = _origin(Path(origin) / "config")
    return origin.removesuffix(".git") if origin.startswith("https://") else ""


def _git_packages(checkout: Path) -> Iterator[Path]:
    for level in range(MAX_GIT_DEPTH + 1):
        for pubspec in sorted(checkout.glob("/".join(["*"] * level + ["pubspec.yaml"]))):
            if not NOT_PACKAGES & set(pubspec.relative_to(checkout).parts) and pubspec.is_file():
                yield pubspec.parent


def git_versions() -> list[tuple[Pubspec, CachedVersion, str]]:
    """(pubspec, version, fallback url) for every package in git/<repo>-<sha>/ checkouts."""
    found: list[tuple[Pubspec, tuple[str, str], str]] = []
    for checkout in _dirs(PUB_CACHE / "git"):
        if checkout.name == "cache":  # bare mirrors pub clones from
            continue
        remote = git_remote(checkout)
        for directory in _git_packages(checkout):
            spec = _spec(directory)
            if spec.name and spec.version:  # not a workspace root
                found.append((spec, resolve(directory, checkout), remote))
    with ThreadPoolExecutor(UPSTREAM_WORKERS) as pool:
        licensed = list(pool.map(lambda job: with_upstream(job[1][0], job[1][1], job[2]), found))
    return [
        (
            spec,
            CachedVersion(f"{spec.version} (git)", *lic, spec.deps),
            remote or f"https://pub.dev/packages/{spec.name}",
        )
        for (spec, _, remote), lic in zip(found, licensed, strict=True)
    ]


def artifacts() -> list[CachedArtifact]:
    """One artifact per package name across hosted servers and git checkouts.

    Git checkouts of the same version and license (kuhyx/utils at 30 refs) are
    one entry; a hosted and a git copy of a name share one artifact, since
    to_items keys items by name.
    """
    by_name: dict[str, CachedArtifact] = {}
    urls: dict[str, list[tuple[str, str, str]]] = {}
    for spec, version, fallback in [*hosted_versions(), *git_versions()]:
        art = by_name.setdefault(spec.name, CachedArtifact(spec.name))
        if all((v.version, v.license) != (version.version, version.license) for v in art.versions):
            art.versions.append(version)
        urls.setdefault(spec.name, []).append((version.version, spec.url, fallback))
    for name, art in by_name.items():
        # The newest version's own repository/homepage, else its pub.dev page.
        newest = sorted(urls[name], key=lambda u: version_key(u[0]), reverse=True)
        art.url = next((own for _, own, _ in newest if own), newest[0][2])
    return list(by_name.values())


def used_by() -> dict[str, set[str]]:
    """Package name -> ~/src projects whose pubspec.lock lists it."""
    users: dict[str, set[str]] = {}
    for lock in project_files(["pubspec.lock"], root=SRC):
        for name in lock_packages(read(lock)):
            users.setdefault(name, set()).add(project_of(lock, root=SRC))
    return users


def scan_pub_cache() -> list[Item]:
    """One Item per cached Dart/Flutter package, worst license over its versions."""
    return to_items("pub-cache", artifacts(), used_by())
