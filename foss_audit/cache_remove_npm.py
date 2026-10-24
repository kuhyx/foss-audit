"""Remove commands for npm-cache items (see cache_remove for the rules).

Projects are the ~/src lockfiles. A pnpm-lock.yaml's `importers` say what each
workspace project declares: `pnpm remove` runs in that project's directory;
its `packageManagerDependencies` (pnpm fetching itself) go with
`npm pkg delete packageManager`. A package-lock.json's `packages[""]` and
workspace entries do the same for `npm uninstall` (`-w <path>` for a
workspace, run from the root); a lockfileVersion 1 lock takes the root's
declarations from package.json. The graph is the lock's snapshots / node_modules
entries plus every cached package.json's dependencies; `link:` and workspace
packages are local. The cache step lives in cache_remove_npm_store.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Any

from foss_audit import scan_cache_npm
from foss_audit.cache_common import CachedArtifact
from foss_audit.cache_remove import Graph, Manifest, Planner, apply, cache_graph, projects
from foss_audit.cache_remove_npm_store import NpmCache
from foss_audit.model import Item

# Importer sections and the kind of remove command each takes.
SECTIONS = {
    "dependencies": "pnpm",
    "devDependencies": "pnpm",
    "optionalDependencies": "pnpm",
    "packageManagerDependencies": "pm",
}
EDGES = ("dependencies", "optionalDependencies")
NPM_DECLARED = ("dependencies", "devDependencies", "optionalDependencies")
NPM_EDGES = ("dependencies", "optionalDependencies", "peerDependencies")
# indent, optional quote, key, inline value of one YAML mapping line.
KEY = re.compile(r"""^( *)(['"]?)(.+?)\2:(?: (.*))?$""")
Lock = tuple[dict[str, dict[str, str]], Graph, set[str]]


def render(kind: str, names: list[str]) -> str:
    """The command removing `names` declared under `kind`."""
    words = " ".join(map(shlex.quote, names))
    if kind == "pm":
        return "npm pkg delete packageManager"
    if kind == "pnpm":
        return f"pnpm remove {words}"
    return " ".join(["npm uninstall", *([kind] if kind != "npm" else []), words])


def pnpm_lock(text: str) -> Lock:
    """(importer path -> {dependency: kind}, graph, local names) of a pnpm-lock.yaml."""
    importers: dict[str, dict[str, str]] = {}
    graph: Graph = {}
    local: set[str] = set()
    top = importer = sub = dep = pkg = ""
    for raw in text.splitlines():
        # YAML writes a key over 1024 chars explicitly: "  ? 'key'" then "  : dependencies:".
        line = (
            f"  {raw[4:]}:" if raw.startswith("  ? ") else f"    {raw[4:]}" if raw.startswith("  : ") else raw
        )
        match = KEY.match(line)
        if not match:
            continue
        indent, key, value = len(match[1]), match[3], match[4] or ""
        if indent == 0:
            top, sub = key, ""
        elif top == "importers" and indent == 2:
            importer = key
        elif top == "importers" and indent == 4:
            sub = key
        elif top == "importers" and indent == 6 and sub in SECTIONS:
            dep = key
            importers.setdefault(importer, {})[key] = SECTIONS[sub]
        elif top == "importers" and indent == 8 and key == "version" and value.startswith("link:"):
            local.add(dep)
        elif top in ("packages", "snapshots") and indent == 2:
            name = scan_cache_npm.LOCK_KEY.match(line)
            pkg = name.group(1) if name else ""
            graph.setdefault(pkg, set())
        elif top in ("packages", "snapshots") and indent == 4:
            sub = key
        elif top in ("packages", "snapshots") and indent == 6 and sub in EDGES:
            graph[pkg].add(key)
        elif top in SECTIONS and indent == 2:  # lockfile v5/v6 of a single project
            importers.setdefault(".", {})[key] = SECTIONS[top]
    graph.pop("", None)
    return importers, graph, local


def _keys(spec: dict[str, Any], sections: tuple[str, ...]) -> set[str]:
    return {k for s in sections if isinstance(spec.get(s), dict) for k in spec[s]}


def _v1(deps: object, graph: Graph) -> None:
    for name, spec in deps.items() if isinstance(deps, dict) else ():
        if isinstance(spec, dict):
            graph.setdefault(name, set()).update(_table(spec.get("requires")))
            _v1(spec.get("dependencies"), graph)


def _table(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def package_lock(doc: dict[str, Any], folder: Path) -> Lock:
    """(importer -> {dependency: kind}, graph, local names) of a package-lock.json."""
    importers: dict[str, dict[str, str]] = {}
    graph: Graph = {}
    local: set[str] = set()
    for key, raw in _table(doc.get("packages")).items():
        spec = _table(raw)
        if "node_modules/" in key:
            name = key.rpartition("node_modules/")[2]
            graph.setdefault(name, set()).update(_keys(spec, NPM_EDGES))
            if spec.get("link"):
                local.add(name)
            continue
        kind = f"-w {shlex.quote(key)}" if key else "npm"
        importers[key] = dict.fromkeys(sorted(_keys(spec, NPM_DECLARED)), kind)
        local.add(str(spec.get("name", "")))
    if "packages" not in doc:
        _v1(doc.get("dependencies"), graph)
        try:
            manifest = json.loads((folder / "package.json").read_text(errors="replace"))
        except OSError, ValueError:
            manifest = {}
        importers[""] = dict.fromkeys(sorted(_keys(_table(manifest), NPM_DECLARED)), "npm")
    return importers, graph, local - {""}


def manifests(root: Path) -> list[Manifest]:
    """One Manifest per lockfile importer (pnpm) or lockfile (npm); local names are its lock's."""
    found: list[Manifest] = []
    for lock in projects(scan_cache_npm.LOCKFILES, root):
        text = lock.read_text(errors="replace")
        pnpm = lock.name.endswith(".yaml")
        if pnpm:
            importers, graph, members = pnpm_lock(text)
            listed = scan_cache_npm.pnpm_lock_names(text)
            dirs = {lock.parent / imp: list(decls.items()) for imp, decls in importers.items()}
        else:
            try:
                doc = json.loads(text)
            except ValueError:
                continue
            if not isinstance(doc, dict):
                continue
            importers, graph, members = package_lock(doc, lock.parent)
            listed = scan_cache_npm.package_lock_names(text)
            # npm runs every workspace's removal from the root (`-w <path>`).
            dirs = {lock.parent: [pair for decls in importers.values() for pair in decls.items()]}
        relock = "pnpm install --lockfile-only" if pnpm else "npm install --package-lock-only"
        for folder, decls in dirs.items():
            m = Manifest(folder, render)
            for name, kind in decls:
                m.declare(name, kind)
            m.edges, m.locked, m.relock = graph, frozenset(listed), (lock.parent, relock)
            m.local = frozenset(members)
            found.append(m)
    return found


def fill(items: list[Item], arts: list[CachedArtifact], root: Path, cacache: Path, store: Path) -> None:
    """Set removeCommand and removeVia on every npm-cache item."""
    apply(items, Planner(manifests(root), cache_graph(arts)), NpmCache(cacache, store).step)
