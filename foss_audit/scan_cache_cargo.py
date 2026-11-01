"""Scan the cargo registry cache and git checkouts: one Item per crate name.

Every version's license is read from the crate itself: the `[package] license`
SPDX expression in its Cargo.toml, else the `license-file` it names, else any
LICENSE*/COPYING* file at the crate root. An extracted ~/.cargo/registry/src
dir is preferred over its .crate (a gzip tar, streamed, never extracted). The
cache is untrusted: everything is read-only and size-capped, nothing runs.

Measured offline (2026-10-18): all 1933 cached versions resolve this way, so
there is no crates.io fallback; a crate that does not resolve says where it
looked instead. A git checkout without a license also asks its upstream
repository for its current one (scan_cache_cargo_git, upstream_license).
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path
from typing import Any

from foss_audit import cache_common, cache_remove_cargo, memo, progress
from foss_audit.cache_common import CachedArtifact, CachedVersion, project_files, project_of, to_items
from foss_audit.memo import NO_MEMO, Memo
from foss_audit.model import Item
from foss_audit.own_license import identify
from foss_audit.scan_cache_cargo_git import GitUrls
from foss_audit.scan_cache_cargo_read import (
    READ_ERRORS,
    Manifest,
    read_crate,
    read_dir,
    read_git_checkout,
    table,
)
from foss_audit.upstream_license import with_upstream

CARGO = Path.home() / ".cargo"
SRC = cache_common.SRC
# Fallback only (unreadable manifest): "<name>-<semver...>" with dashes in names.
# A memo key (None: never memoized) and the reader of one copy (None: no package in it).
Copy = tuple[str | None, Callable[[], Manifest | None]]
STEM = re.compile(r"^(?P<name>.+?)-(?P<version>\d+\.\d+\.\d+.*)$")


def license_of(m: Manifest) -> tuple[str, str]:
    """(license, where it came from); ("", every place checked) when nothing."""
    if m.error:
        return "", m.error
    declared = m.package.get("license")
    if isinstance(declared, str) and declared.strip():
        return declared, f"Cargo.toml license ({m.where})"
    tried = [f"Cargo.toml license ({m.where})" + (" workspace-inherited" if declared else "")]
    named = m.package.get("license-file")
    if isinstance(named, str):
        found = identify(m.texts.get(named, ""))
        if found:
            return found, f"license-file {named} ({m.where})"
        tried.append(f"license-file {named}")
    ids = sorted({identify(t) for rel, t in m.texts.items() if rel != named} - {""})
    if ids:
        return " AND ".join(ids), f"LICENSE/COPYING files ({m.where})"
    tried.append("LICENSE*/COPYING* files in the crate root")
    return "", ", ".join(tried)


def runtime_deps(deps: dict[str, Any]) -> tuple[str, ...]:
    """`[dependencies]` crate names: renames resolved, optional ones dropped."""
    names: set[str] = set()
    for key, spec in deps.items():
        fields = table(spec)
        if fields.get("optional") is not True:
            names.add(str(fields.get("package", key)))
    return tuple(sorted(names))


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def identity(m: Manifest) -> tuple[str, str]:
    """(name, version) from Cargo.toml; the directory/file stem when unreadable."""
    parsed = STEM.match(m.stem)
    name = _text(m.package.get("name")) or (parsed["name"] if parsed else m.stem)
    version = _text(m.package.get("version")) or (parsed["version"] if parsed else m.stem)
    return name, version


def copies() -> Iterator[Copy]:
    """Every cached crate copy: src dirs first, then .crates, then git checkouts."""
    registry = CARGO / "registry"
    extracted = {(p.parent.name, p.name) for p in registry.glob("src/*/*") if p.is_dir()}
    crates = [
        c
        for c in sorted(registry.glob("cache/*/*.crate"))
        if (c.parent.name, c.name.removesuffix(".crate")) not in extracted
    ]
    tomls = sorted(CARGO.glob("git/checkouts/*/*/Cargo.toml"))
    shared = progress.counter("cargo-cache")
    shared.add_total(len(extracted) + len(crates) + len(tomls))
    for index, stem in sorted(extracted):
        shared.advance()
        folder = registry / "src" / index / stem
        yield (
            f"{memo.stat_key(folder)}|{memo.stat_key(folder / 'Cargo.toml')}",
            partial(read_dir, folder, "src dir"),
        )
    for crate in crates:
        shared.advance()
        yield memo.stat_key(crate), partial(read_crate, crate)
    for toml in tomls:
        shared.advance()
        yield None, partial(read_git_checkout, toml)


def _decode(hit: list[Any]) -> list[Any]:
    name, version, license_id, where, deps, home = hit
    memo.require_text(name, version, license_id, where, home, *deps)
    return list(hit)


def cached_artifacts(readings: Memo = NO_MEMO) -> list[CachedArtifact]:
    """One artifact per crate name; the first copy of each version wins.

    A registry copy's reading (name, version, license, deps, home page) is memoized; a git
    checkout is always read, since its license may come from its upstream repository.
    """
    arts: dict[str, CachedArtifact] = {}
    seen: set[tuple[str, str]] = set()
    git_urls = GitUrls(CARGO, SRC)
    for key, load in copies():
        stored = readings.recall(key, _decode)[1] if key else None
        manifest = None if stored else load()
        if stored:
            head = (stored[0], stored[1])
        elif manifest:
            head = identity(manifest)
        else:  # a workspace-only git root
            continue
        if head in seen:
            continue
        seen.add(head)
        name, version = head
        if stored is None:
            assert manifest is not None
            lic, where = license_of(manifest)
            if manifest.git:  # last fallback: the upstream repository's current license
                lic, where = with_upstream(lic, where, git_urls.find(*manifest.git, manifest.package))
            home = _text(manifest.package.get("repository")) or _text(manifest.package.get("homepage"))
            stored = [name, version, lic, where, list(runtime_deps(manifest.deps)), home or ""]
            if key:
                readings.put(key, stored)
        art = arts.setdefault(name, CachedArtifact(name, url=f"https://crates.io/crates/{name}"))
        art.versions.append(CachedVersion(version, stored[2], stored[3], tuple(stored[4])))
        newest = max(art.versions, key=lambda v: cache_common.version_key(v.version))
        if newest.version == version:
            art.url = stored[5] or f"https://crates.io/crates/{name}"
    return [arts[n] for n in sorted(arts)]


def lock_users() -> dict[str, set[str]]:
    """Crate name -> ~/src projects whose Cargo.lock lists it."""
    used: dict[str, set[str]] = {}
    for lock in project_files(["Cargo.lock"], SRC):
        try:
            packages = tomllib.loads(lock.read_text()).get("package", [])
        except READ_ERRORS:
            continue
        for pkg in packages:
            used.setdefault(str(pkg.get("name")), set()).add(project_of(lock, SRC))
    return used


def scan_cargo_cache() -> list[Item]:
    """Every crate in ~/.cargo's registry cache and git checkouts, each with its remove command."""
    readings = Memo.for_source("cargo-cache")
    arts = cached_artifacts(readings)
    readings.save()
    items = to_items("cargo-cache", arts, lock_users())
    cache_remove_cargo.fill(items, arts, CARGO, SRC)
    return items
