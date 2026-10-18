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
import tarfile
import tomllib
import zlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from foss_audit import cache_common
from foss_audit.cache_common import CachedArtifact, CachedVersion, project_files, project_of, to_items
from foss_audit.model import Item
from foss_audit.own_license import LICENSE_FILE, identify
from foss_audit.scan_cache_cargo_git import GitUrls
from foss_audit.upstream_license import with_upstream

CARGO = Path.home() / ".cargo"
SRC = cache_common.SRC
# Manifests and license texts are small; anything bigger is not read whole.
MAX_READ = 512 * 1024
# Fallback only (unreadable manifest): "<name>-<semver...>" with dashes in names.
STEM = re.compile(r"^(?P<name>.+?)-(?P<version>\d+\.\d+\.\d+.*)$")
READ_ERRORS = (OSError, EOFError, tarfile.TarError, zlib.error, UnicodeDecodeError, tomllib.TOMLDecodeError)


@dataclass
class Manifest:
    """What one crate copy says about itself, plus the license texts it holds."""

    where: str
    stem: str
    package: dict[str, Any] = field(default_factory=dict)
    deps: dict[str, Any] = field(default_factory=dict)
    texts: dict[str, str] = field(default_factory=dict)
    error: str = ""
    # (db dir, rev dir) of a git checkout under ~/.cargo/git/checkouts, else None.
    git: tuple[str, str] | None = None


def _decode(data: bytes) -> str:
    return data[:MAX_READ].decode("utf-8", errors="replace")


def _table(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse(m: Manifest, text: str) -> None:
    data = tomllib.loads(text)
    m.package = _table(data.get("package"))
    m.deps = _table(data.get("dependencies"))


def _needs_files(m: Manifest) -> bool:
    return not isinstance(m.package.get("license"), str)


def _wanted(m: Manifest) -> Callable[[str], bool]:
    """Relative paths whose text the license fallback reads."""
    named = m.package.get("license-file")
    return lambda rel: rel == named or ("/" not in rel and bool(LICENSE_FILE.match(rel)))


def _members(path: Path) -> Iterator[tuple[str, tarfile.TarFile, tarfile.TarInfo]]:
    """(path below the crate's top dir, archive, member) for each regular file."""
    with tarfile.open(path, "r|gz") as tf:
        for member in tf:
            top, _, rel = member.name.partition("/")
            if member.isfile() and top == path.name.removesuffix(".crate"):
                yield rel, tf, member


def _read(tf: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    handle = tf.extractfile(member)
    return _decode(handle.read(MAX_READ)) if handle else ""


def read_crate(path: Path) -> Manifest:
    """Cargo.toml (stream stops there), then license texts only when needed."""
    m = Manifest(".crate", path.name.removesuffix(".crate"))
    try:
        for rel, tf, member in _members(path):
            if rel == "Cargo.toml":
                _parse(m, _read(tf, member))
                break
        if _needs_files(m):
            # A second pass: COPYING/LICENSE may sit before Cargo.toml in the tar.
            wanted = _wanted(m)
            m.texts = {rel: _read(tf, member) for rel, tf, member in _members(path) if wanted(rel)}
    except READ_ERRORS as exc:
        m.error = f"unreadable {path.name}: {type(exc).__name__}: {exc}"
    return m


def read_dir(path: Path, where: str) -> Manifest:
    """An extracted crate or git checkout (read-only, no path escapes)."""
    m = Manifest(where, path.name)
    try:
        _parse(m, _decode((path / "Cargo.toml").read_bytes()))
        if _needs_files(m):
            wanted = _wanted(m)
            names = [p.name for p in path.iterdir()] + [str(m.package.get("license-file", ""))]
            for rel in filter(wanted, names):
                file = (path / rel).resolve()
                if file.is_file() and file.is_relative_to(path.resolve()):
                    m.texts[rel] = _decode(file.read_bytes())
    except READ_ERRORS as exc:
        m.error = f"unreadable {path}/Cargo.toml: {type(exc).__name__}: {exc}"
    return m


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
        table = _table(spec)
        if table.get("optional") is not True:
            names.add(str(table.get("package", key)))
    return tuple(sorted(names))


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def identity(m: Manifest) -> tuple[str, str]:
    """(name, version) from Cargo.toml; the directory/file stem when unreadable."""
    parsed = STEM.match(m.stem)
    name = _text(m.package.get("name")) or (parsed["name"] if parsed else m.stem)
    version = _text(m.package.get("version")) or (parsed["version"] if parsed else m.stem)
    return name, version


def manifests() -> Iterator[Manifest]:
    """Every cached crate copy: src dirs first, then .crates, then git checkouts."""
    registry = CARGO / "registry"
    extracted = {(p.parent.name, p.name) for p in registry.glob("src/*/*") if p.is_dir()}
    for index, stem in sorted(extracted):
        yield read_dir(registry / "src" / index / stem, "src dir")
    for crate in sorted(registry.glob("cache/*/*.crate")):
        if (crate.parent.name, crate.name.removesuffix(".crate")) not in extracted:
            yield read_crate(crate)
    for toml in sorted(CARGO.glob("git/checkouts/*/*/Cargo.toml")):
        m = read_dir(toml.parent, f"git checkout {toml.parent.parent.name}/{toml.parent.name}")
        if m.package or m.error:  # a workspace-only root has no [package]
            m.git = (toml.parent.parent.name, toml.parent.name)
            yield m


def cached_artifacts() -> list[CachedArtifact]:
    """One artifact per crate name; the first copy of each version wins."""
    arts: dict[str, CachedArtifact] = {}
    seen: set[tuple[str, str]] = set()
    git_urls = GitUrls(CARGO, SRC)
    for m in manifests():
        name, version = identity(m)
        if (name, version) in seen:
            continue
        seen.add((name, version))
        lic, where = license_of(m)
        if m.git:  # last fallback: the upstream repository's current license
            lic, where = with_upstream(lic, where, git_urls.find(*m.git, m.package))
        art = arts.setdefault(name, CachedArtifact(name, url=f"https://crates.io/crates/{name}"))
        art.versions.append(CachedVersion(version, lic, where, runtime_deps(m.deps)))
        newest = max(art.versions, key=lambda v: cache_common.version_key(v.version))
        if newest.version == version:
            home = _text(m.package.get("repository")) or _text(m.package.get("homepage"))
            art.url = home or f"https://crates.io/crates/{name}"
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
    """Every crate in ~/.cargo's registry cache and git checkouts."""
    return to_items("cargo-cache", cached_artifacts(), lock_users())
