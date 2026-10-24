"""Permanent remove commands for package-cache items (pip, npm, pub, cargo).

A cached package comes back on the next build while any ~/src project still
pulls it in, so deleting the cache alone is not removal. For one package:

- every manifest that declares it gets the ecosystem's own remove command, run
  in that manifest's directory;
- every manifest that reaches it through other dependencies (its lockfile's
  graph, plus the dependencies the cache itself records) gets each direct
  parent on such a chain removed, every chain spelled out in `removeVia`;
- a lockfile that lists it although nothing declared reaches it is blamed on
  the manifest's `fallback` roots (pub's SDK packages, whose pubspecs are not
  in the cache), else re-locked;
- its own cache entries are deleted last, once.

Nothing reaches it: it is stale and only its cache entries go. Steps are
subshells joined by "; ", so a failed `cd` never runs a removal elsewhere and
one failing step never hides the others. The UI only copies the command.
"""

from __future__ import annotations

import shlex
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from foss_audit.cache_common import CachedArtifact, project_files
from foss_audit.model import Item

HOME = Path.home()
Graph = dict[str, set[str]]
# (kind, token): how a dependency is declared and the word its remove command takes.
Decl = tuple[str, str]
# (kind, tokens) -> the command that removes those tokens, run in the manifest's dir.
Render = Callable[[str, list[str]], str]
# Package name -> (cache delete step, note on what else it deletes).
CacheStep = Callable[[str], tuple[str, str]]
# Directories that are build output or vendored copies, never a project.
MEMBER_DEPTH = 3
NOT_PROJECT = frozenset({"node_modules", "target", "build", "ephemeral", "flutter_assets"})


def shell_path(path: Path) -> str:
    """A path for a copied command: `~/...` stays expandable, the rest is quoted."""
    try:
        rel = path.relative_to(HOME)
    except ValueError:
        return shlex.quote(str(path))
    return "~/" + shlex.quote(str(rel)) if rel.parts else "~"


def shown(path: Path) -> str:
    """A path for `removeVia`: under ~ when it is."""
    return shell_path(path) if path.is_relative_to(HOME) else str(path)


def rm(paths: Iterable[Path]) -> str:
    """`rm -rf` of exact paths (never a glob: zsh aborts on one that matches nothing)."""
    unique = sorted(set(paths))
    return "rm -rf " + " ".join(map(shell_path, unique)) if unique else ""


def joined(steps: Iterable[str]) -> str:
    """Non-empty, distinct steps in order, joined so each runs whatever the others do."""
    return "; ".join(dict.fromkeys(s for s in steps if s))


def projects(names: Iterable[str], root: Path, lock: str = "") -> list[Path]:
    """Project files under ~/src, minus build output, vendored copies and hidden
    dirs (.claude/worktrees/* checkouts are throwaway copies of their repo).

    Workspace members may sit deeper than project_files looks
    (~/src/a/b/ws/crates/x/Cargo.toml): below every `lock` file found, up to
    MEMBER_DEPTH more levels are searched too (bounded globs, no walk).
    """
    wanted = list(names)
    found = project_files(wanted, root)
    for lockfile in project_files([lock], root) if lock else []:
        for level in range(1, MEMBER_DEPTH + 1):
            found += [p for n in wanted for p in lockfile.parent.glob("/".join(["*"] * level + [n]))]
    return sorted(
        p
        for p in set(found)
        if p.is_file()
        and not any(part in NOT_PROJECT or part[0] == "." for part in p.relative_to(root).parts)
    )


def nearest(start: Path, names: Iterable[str], top: Path) -> Path | None:
    """The first of `names` in `start` or a parent dir, stopping at `top`."""
    wanted = list(names)
    for folder in [start, *start.parents]:
        hit = next((folder / n for n in wanted if (folder / n).is_file()), None)
        if hit or folder == top or not folder.is_relative_to(top):
            return hit
    return None  # pragma: no cover - the loop always reaches `top` or `/`


def repo_of(path: Path, root: Path) -> Path:
    """The ~/src/<repo> directory a path lies in."""
    return root / path.relative_to(root).parts[0]


def cache_graph(arts: Iterable[CachedArtifact]) -> Graph:
    """Package -> every runtime dependency any of its cached versions names."""
    graph: Graph = {}
    for art in arts:
        for version in art.versions:
            graph.setdefault(art.name, set()).update(version.deps)
    return graph


@dataclass
class Manifest:
    """One project directory and what it declares, plus the lockfile it resolves into."""

    dir: Path
    render: Render
    direct: dict[str, list[Decl]] = field(default_factory=dict)
    edges: Graph = field(default_factory=dict)
    locked: frozenset[str] = frozenset()
    # (directory, command) that rewrites the lockfile.
    relock: tuple[Path, str] | None = None
    fallback: tuple[str, ...] = ()
    # Its workspace members and path dependencies, never blamed as a parent. Per
    # manifest: a name that is local in one repo is a registry package in another.
    local: frozenset[str] = frozenset()

    def declare(self, name: str, kind: str, token: str | None = None) -> None:
        """Record that this manifest declares `name` under `kind`."""
        decls = self.direct.setdefault(name, [])
        if (kind, token or name) not in decls:
            decls.append((kind, token or name))


class Planner:
    """Remove command and removeVia for each package of one ecosystem."""

    def __init__(self, manifests: Iterable[Manifest], cache_edges: Graph) -> None:
        self.manifests = sorted(manifests, key=lambda m: m.dir)
        self.cache_edges = cache_edges
        self._reach: dict[tuple[int, str], dict[str, str]] = {}

    def _walk(self, m: Manifest, root: str) -> dict[str, str]:
        """Node -> its predecessor on a shortest chain from `root` (breadth first)."""
        key = (id(m), root)
        if key not in self._reach:
            prev = {root: ""}
            queue = deque([root])
            while queue:
                node = queue.popleft()
                # The lockfile is authoritative for what it lists; the cache's own
                # dependency data (any version) fills in what it does not.
                edges = m.edges[node] if node in m.edges else self.cache_edges.get(node, set())
                for nxt in sorted(edges):
                    if nxt not in prev and nxt not in m.local:
                        prev[nxt] = node
                        queue.append(nxt)
            self._reach[key] = prev
        return self._reach[key]

    def _chain(self, m: Manifest, root: str, name: str) -> list[str]:
        prev, chain = self._walk(m, root), [name]
        while prev[chain[-1]]:
            chain.append(prev[chain[-1]])
        return chain[::-1]

    def _parents(self, m: Manifest, name: str) -> list[tuple[str, str]]:
        """(direct parent, how it reaches `name`) for every chain into `name`."""
        roots = [r for r in sorted(m.direct) if r != name and r not in m.local]
        return [(r, " → ".join(self._chain(m, r, name))) for r in roots if name in self._walk(m, r)]

    @staticmethod
    def _steps(m: Manifest, name: str, parents: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
        """(commands, removeVia parts) removing `name` and `parents` from one manifest."""
        where = shown(m.dir)
        wanted: dict[str, list[str]] = {}
        via: list[str] = []
        for kind, token in m.direct.get(name, []):
            wanted.setdefault(kind, []).append(token)
            via.append(f"{where} declares {name}")
        for parent, chain in parents:
            for kind, token in m.direct.get(parent, []):
                wanted.setdefault(kind, []).append(token)
            via.append(f"{where} via {chain}")
        steps = [f"(cd {shell_path(m.dir)} && {m.render(kind, toks)})" for kind, toks in wanted.items()]
        return steps, via

    def _group(self, group: list[Manifest], name: str) -> tuple[list[str], list[str]]:
        """Steps for the manifests sharing one lockfile (a workspace)."""
        found = [self._steps(m, name, self._parents(m, name)) for m in group]
        # The project's own package (a cached copy of it came from elsewhere) is never re-locked.
        own = any(name in m.local for m in group)
        if not any(steps for steps, _ in found) and name in group[0].locked and not own:
            # Listed by the lockfile, reached by nothing declared: an SDK package's
            # dependency (pub), else a stale lock entry that re-locking drops.
            sdk = f"(SDK, its pubspec is not in the cache) → {name}"
            found = [self._steps(m, name, [(r, f"{r} {sdk}") for r in m.fallback]) for m in group]
            if not any(steps for steps, _ in found) and group[0].relock:
                folder, command = group[0].relock
                why = f"{shown(folder)} lockfile lists {name} but nothing it declares reaches it"
                found = [([f"(cd {shell_path(folder)} && {command})"], [why])]
        return [s for steps, _ in found for s in steps], [v for _, via in found for v in via]

    def plan(self, name: str, cache_step: str, note: str = "") -> tuple[str, str]:
        """(removeCommand, removeVia) for package `name`."""
        groups: dict[Path, list[Manifest]] = {}
        for m in self.manifests:
            groups.setdefault(m.relock[0] if m.relock else m.dir, []).append(m)
        steps: list[str] = []
        via: list[str] = []
        for group in groups.values():
            more, why = self._group(group, name)
            steps += more
            via += why
        if not via:
            via.append("stale: no ~/src project reaches it, so only its cache entries are deleted")
        return joined([*steps, cache_step]), "; ".join(dict.fromkeys([*via, *([note] if note else [])]))


def apply(items: Iterable[Item], planner: Planner, cache_step: CacheStep) -> None:
    """Fill removeCommand and removeVia of every item in place."""
    for item in items:
        step, note = cache_step(item.name)
        item.removeCommand, item.removeVia = planner.plan(item.name, step, note)
