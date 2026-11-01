"""Remove commands for cargo-cache items (see cache_remove for the rules).

Projects are the ~/src Cargo.toml manifests (build output under target/ is
not one). A dependency is removed with `cargo remove <key>` in the crate that
declares it, `<key>` being the manifest key (a renamed dependency's
`package =` is only its crates.io name), plus `--dev`, `--build` and
`--target <cfg>` for those tables. The graph is the nearest Cargo.lock's
`dependencies` plus every cached crate's own [dependencies]; workspace
members and path dependencies are never blamed. The cache step deletes the
exact .crate files, extracted src dirs and git checkouts of the crate.
"""

from __future__ import annotations

import shlex
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from foss_audit.cache_common import CachedArtifact
from foss_audit.cache_remove import Planner, apply, cache_graph, nearest, projects, repo_of, rm
from foss_audit.cache_remove_reach import Manifest
from foss_audit.model import Item

SECTIONS = {"dependencies": "", "dev-dependencies": "--dev", "build-dependencies": "--build"}
RELOCK = "cargo update --workspace"


def _table(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _toml(path: Path) -> dict[str, Any] | None:
    try:
        return tomllib.loads(path.read_text(errors="replace"))
    except OSError, tomllib.TOMLDecodeError:
        return None


def render(kind: str, keys: list[str]) -> str:
    """`cargo remove [flags] <keys>`."""
    return " ".join(["cargo remove", *([kind] if kind else []), *map(shlex.quote, keys)])


def declarations(data: dict[str, Any]) -> Iterator[tuple[str, str, str, bool]]:
    """(crate name, cargo remove flags, manifest key, is a path dependency) per declared dependency."""
    tables = [("", data), *((t, _table(spec)) for t, spec in _table(data.get("target")).items())]
    for target, table in tables:
        for section, flag in SECTIONS.items():
            where = " ".join(f for f in (flag, f"--target {shlex.quote(target)}" if target else "") if f)
            for key, spec in _table(table.get(section)).items():
                dep = _table(spec)
                yield str(dep.get("package", key)), where, key, "path" in dep


def read_lock(path: Path) -> tuple[dict[str, set[str]], set[str], set[str]]:
    """(graph, every name listed, workspace members) of one Cargo.lock."""
    packages = (_toml(path) or {}).get("package", [])
    graph: dict[str, set[str]] = {}
    members: set[str] = set()
    for pkg in packages:
        name = str(pkg.get("name"))
        graph.setdefault(name, set()).update(str(d).split()[0] for d in pkg.get("dependencies", []))
        if "source" not in pkg:
            members.add(name)
    return graph, set(graph), members


def manifests(root: Path) -> list[Manifest]:
    """Every ~/src crate manifest; its local crates are its path deps and its lock's members."""
    found: list[Manifest] = []
    locks: dict[Path, tuple[dict[str, set[str]], set[str], set[str]]] = {}
    for path in projects(["Cargo.toml"], root, lock="Cargo.lock"):
        data = _toml(path)
        if data is None:
            continue
        m = Manifest(path.parent, render, name=str(_table(data.get("package")).get("name", "")))
        local = {m.name}
        for name, flags, key, is_path in declarations(data):
            m.declare(name, flags, key)
            if is_path:
                local.add(name)
        lock = nearest(path.parent, ["Cargo.lock"], repo_of(path, root))
        if lock:
            graph, listed, members = locks.setdefault(lock, read_lock(lock))
            m.edges, m.locked, m.relock = graph, frozenset(listed), (lock.parent, RELOCK)
            local |= members
        m.local = frozenset(local - {""})
        found.append(m)
    return found


class CacheFiles:
    """Exact cache paths per crate: .crate files, extracted sources, git checkouts."""

    def __init__(self, cargo: Path, arts: list[CachedArtifact]) -> None:
        registry = cargo / "registry"
        self.stems: dict[str, list[Path]] = {}
        for path in [*registry.glob("cache/*/*.crate"), *registry.glob("src/*/*")]:
            self.stems.setdefault(path.name.removesuffix(".crate"), []).append(path)
        self.git: dict[str, list[Path]] = {}
        for toml in cargo.glob("git/checkouts/*/*/Cargo.toml"):
            name = _table((_toml(toml) or {}).get("package")).get("name")
            if isinstance(name, str):
                self.git.setdefault(name, []).append(toml.parent)
        self.versions = {a.name: [v.version for v in a.versions] for a in arts}

    def step(self, name: str) -> tuple[str, str]:
        """`rm -rf` of every cached copy of crate `name`."""
        stems = {name, *(f"{name}-{v}" for v in self.versions.get(name, []))}
        paths = [p for stem in stems for p in self.stems.get(stem, [])] + self.git.get(name, [])
        return rm(paths), ""


def fill(items: list[Item], arts: list[CachedArtifact], cargo: Path, root: Path) -> None:
    """Set removeCommand and removeVia on every cargo-cache item."""
    apply(items, Planner(manifests(root), cache_graph(arts)), CacheFiles(cargo, arts).step)
