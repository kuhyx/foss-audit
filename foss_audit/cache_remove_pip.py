"""Remove commands for pip-cache items (see cache_remove for the rules).

Projects are the ~/src pyproject.toml and requirements*.txt files (virtualenvs
and build output are not). A pyproject dependency goes with the project's own
tool, run in its directory: `poetry remove [--group g]` for poetry projects,
else `uv remove` with `--optional <extra>` / `--group <group>` (`--frozen`
when there is no uv.lock, so uv only edits pyproject.toml). Requirements files
and `[build-system] requires` have no remove CLI: an anchored, case- and
separator-insensitive `sed -i` deletes the requirement. The graph is the
nearest uv.lock / poetry.lock plus the cached METADATA's Requires-Dist; lock
members (editable/virtual sources) are local. The cache step is
`uv cache clean <name>` for uv's cache (it also drops the unpacked archives)
and `rm -rf` of the exact pip http/http-v2 entries (body and header) and
built wheels: `pip cache remove` only ever touches wheels/. A uv cached
environment holding the package is deleted whole; uv rebuilds it on demand.
"""

from __future__ import annotations

import shlex
import tomllib
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from typing import Any

from foss_audit.cache_common import CachedArtifact
from foss_audit.cache_remove import (
    Graph,
    Manifest,
    Planner,
    apply,
    cache_graph,
    joined,
    nearest,
    projects,
    repo_of,
    rm,
    shell_path,
)
from foss_audit.model import Item
from foss_audit.scan_cache_pip_meta import REQ_NAME, norm

FILES = ("pyproject.toml", "requirements*.txt")
LOCKS = ("uv.lock", "poetry.lock")
# What may follow a requirement's name: a version, marker, extra, URL or nothing.
AFTER_NAME = "([[:space:]<>=!~;@,[]|$)"
LOCAL_SOURCES = frozenset({"editable", "virtual", "directory", "path"})


def _toml(path: Path) -> dict[str, Any] | None:
    try:
        return tomllib.loads(path.read_text(errors="replace"))
    except OSError, ValueError:
        return None


def requirement_regex(name: str) -> str:
    """ERE matching a requirements line for `name`, however its separators are spelled."""
    return "^[[:space:]]*" + "[-_.]+".join(norm(name).split("-")) + "[[:space:]]*" + AFTER_NAME


def render(tool: str, kind: str, names: list[str]) -> str:
    """The command removing `names` declared under `kind` (see `declarations`)."""
    section, _, arg = kind.partition(" ")
    words = " ".join(map(shlex.quote, names))
    if section == "req":
        script = " ".join(f"-e {shlex.quote(f'/{requirement_regex(n)}/Id')}" for n in names)
        return f"sed -i -E {script} {shlex.quote(arg)}"
    if section == "build":
        quoted = [
            f'"{"[-_.]+".join(norm(n).split("-"))}([[:space:]<>=!~;@,[][^"]*)?",?[[:space:]]*' for n in names
        ]
        script = "".join(f"/^requires[[:space:]]*=/,/]/s/{q}//I" for q in quoted)
        return f"sed -i -E {shlex.quote(script)} pyproject.toml"
    flag = {"optional": f" --optional {arg}", "group": f" --group {arg}"}.get(section, "")
    return f"{tool}{flag} {words}"


def _names(reqs: object) -> Iterator[str]:
    for req in reqs if isinstance(reqs, list) else []:
        match = REQ_NAME.match(req) if isinstance(req, str) else None
        if match:
            yield norm(match.group(1))


def _table(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def declarations(data: dict[str, Any]) -> Iterator[tuple[str, str]]:
    """(name, kind) of every dependency a pyproject.toml declares."""
    project = _table(data.get("project"))
    yield from ((n, "main") for n in _names(project.get("dependencies")))
    for extra, reqs in _table(project.get("optional-dependencies")).items():
        yield from ((n, f"optional {extra}") for n in _names(reqs))
    for group, reqs in _table(data.get("dependency-groups")).items():
        yield from ((n, f"group {group}") for n in _names(reqs))
    yield from ((n, "build") for n in _names(_table(data.get("build-system")).get("requires")))
    poetry = _table(_table(data.get("tool")).get("poetry"))
    yield from ((norm(n), "main") for n in _table(poetry.get("dependencies")) if n != "python")
    for group, table in _table(poetry.get("group")).items():
        yield from ((norm(n), f"group {group}") for n in _table(_table(table).get("dependencies")))
    # Poetry < 1.2's dev section; `poetry remove --group dev` still edits it.
    yield from ((norm(n), "group dev") for n in _table(poetry.get("dev-dependencies")))


def read_lock(path: Path) -> tuple[Graph, set[str]]:
    """(graph, local members) of a uv.lock or poetry.lock."""
    graph: Graph = {}
    local: set[str] = set()
    for pkg in (_toml(path) or {}).get("package", []):
        name = norm(str(pkg.get("name")))
        deps = graph.setdefault(name, set())
        if path.name == "poetry.lock":
            deps.update(map(norm, _table(pkg.get("dependencies"))))
            continue
        tables = [pkg.get("dependencies"), *_table(pkg.get("optional-dependencies")).values()]
        tables += _table(pkg.get("dev-dependencies")).values()
        deps.update(
            norm(str(d["name"])) for table in tables if isinstance(table, list) for d in table if "name" in d
        )
        if LOCAL_SOURCES & set(_table(pkg.get("source"))):
            local.add(name)
    return graph, local


def _requirements(path: Path) -> Iterator[str]:
    lines = [line.split("#", 1)[0].strip() for line in path.read_text(errors="replace").splitlines()]
    yield from _names([line for line in lines if line and not line.startswith("-")])


def manifests(root: Path) -> list[Manifest]:
    """One Manifest per ~/src directory with Python project files; its local
    names are its own project and its lockfile's members."""
    by_dir: dict[Path, list[Path]] = {}
    for path in projects(FILES, root, lock="uv.lock"):
        by_dir.setdefault(path.parent, []).append(path)
    found: list[Manifest] = []
    locks: dict[Path, tuple[Graph, set[str]]] = {}
    for folder, paths in by_dir.items():
        lock = nearest(folder, LOCKS, repo_of(folder, root))
        decls: list[tuple[str, str]] = []
        local: set[str] = set()
        poetry = lock is not None and lock.name == "poetry.lock"
        for path in paths:
            if path.name != "pyproject.toml":
                decls += [(n, f"req {path.name}") for n in _requirements(path)]
                continue
            data = _toml(path) or {}
            poetry = poetry or "poetry" in _table(data.get("tool"))
            local.add(norm(str(_table(data.get("project")).get("name", ""))))
            decls += declarations(data)
        tool = "poetry remove" if poetry else "uv remove" + ("" if lock else " --frozen")
        m = Manifest(folder, partial(render, tool), name=min(local - {""}, default=""))
        for name, kind in decls:
            m.declare(name, kind)
        if lock:
            graph, members = locks.setdefault(lock, read_lock(lock))
            m.edges, m.locked = graph, frozenset(graph)
            m.relock = (lock.parent, "poetry lock" if lock.name == "poetry.lock" else "uv lock")
            local |= members
        m.local = frozenset(local - {""})
        found.append(m)
    return found


class CacheFiles:
    """Exact cache entries per distribution, from where the scan read each one."""

    def __init__(self, where: dict[str, list[tuple[str, Path]]], uv_cache: Path) -> None:
        self.where, self.uv_cache = where, uv_cache

    def step(self, name: str) -> tuple[str, str]:
        """`uv cache clean` and/or `rm -rf` of every cache entry holding `name`."""
        paths: list[Path] = []
        notes: list[str] = []
        uv = False
        for origin, path in self.where.get(name, []):
            if origin.endswith(" env"):
                env = next(p for p in path.parents if p.parent.name == "archive-v0")
                paths.append(env)
                notes.append(f"deletes the whole cached uv environment {env.name} (uv rebuilds it on demand)")
            elif origin.startswith("uv"):
                uv = True
            else:
                header = path.with_suffix("")
                paths += [path, *([header] if path.suffix == ".body" and header.is_file() else [])]
        clean = f"uv cache clean --cache-dir {shell_path(self.uv_cache)} {shlex.quote(name)}" if uv else ""
        return joined([clean, rm(paths)]), "; ".join(dict.fromkeys(notes))


def fill(
    items: list[Item],
    arts: list[CachedArtifact],
    where: dict[str, list[tuple[str, Path]]],
    uv: Path,
    root: Path,
) -> None:
    """Set removeCommand and removeVia on every pip-cache item."""
    apply(items, Planner(manifests(root), cache_graph(arts)), CacheFiles(where, uv).step)
