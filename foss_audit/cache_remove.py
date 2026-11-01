"""Permanent remove commands for package-cache items (pip, npm, pub, cargo).

A cached package comes back on the next build while any ~/src project still
pulls it in, so deleting the cache alone is not removal. For one package:

- every manifest that declares it gets the ecosystem's own remove command, run
  in that manifest's directory;
- every manifest that reaches it through other dependencies (its lockfile's
  graph, plus the dependencies the cache itself records) gets each direct
  parent on such a chain removed, every chain spelled out in `removeVia`;
- a lockfile that lists it although nothing declared reaches it is re-locked,
  unless the manifest has `fallback` roots (pub's SDK packages, whose pubspecs
  are not in the cache): then the SDK pins it, nothing project-side is removed
  and removeVia names the apps;
- its own cache entries are deleted last, once.

Nothing reaches it: it is stale and only its cache entries go. Steps are subshells joined by "; ",
so a failed `cd` never runs a removal elsewhere and no failing step hides the others. The UI only copies it.
"""

from __future__ import annotations

import shlex
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from foss_audit import progress
from foss_audit.cache_common import CachedArtifact, project_files
from foss_audit.model import Item

HOME = Path.home()
Graph = dict[str, set[str]]
# (kind, token): how a dependency is declared and the word its remove command takes.
Decl = tuple[str, str]
# (kind, tokens) -> the command that removes those tokens, run in the manifest's dir.
Render = Callable[[str, list[str]], str]
# (commands, removeVia parts) planned for one manifest.
Found = tuple[list[str], list[str]]
# Package name -> (cache delete step, note on what else it deletes).
CacheStep = Callable[[str], tuple[str, str]]
# Directories that are build output or vendored copies, never a project.
MEMBER_DEPTH = 3
# Marks a removeVia part for a project whose SDK pins the package (collected in plan()).
PINNED = "\0pinned:"
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
    # The package this manifest itself builds, when it has a name.
    name: str = ""

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
        # SDK packages (fallback) are never a parent to remove.
        roots = [r for r in sorted(m.direct) if r != name and r not in m.local and r not in m.fallback]
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

    def _unreached(self, key: Path, group: list[Manifest], name: str, covered: set[str]) -> list[Found]:
        """A lockfile lists `name` but nothing its manifests declare reaches it."""
        local = set().union(*(m.local for m in group))
        # The project's own package (a cached copy of it came from elsewhere): nothing to do.
        if name not in group[0].locked or name in local:
            return []
        # Pulled in by one of its path dependencies, whose own manifest already removes it.
        if through := sorted(local & covered):
            return [([], [f"{shown(key)} lockfile lists {name} through its local {', '.join(through)}"])]
        # Pinned by an SDK package (pub's flutter / flutter_test): removing the SDK
        # is no removal, so only the cache entry goes; plan() names the apps.
        if any(m.fallback for m in group):
            return [([], [PINNED + shown(key)])]
        # A stale entry that re-locking drops (a manifest with `locked` names always has `relock`).
        assert group[0].relock
        folder, command = group[0].relock
        why = f"{shown(folder)} lockfile lists {name} but nothing it declares reaches it"
        return [([f"(cd {shell_path(folder)} && {command})"], [why])]

    def plan(self, name: str, cache_step: str, note: str = "") -> tuple[str, str]:
        """(removeCommand, removeVia) for package `name`."""
        # Manifests sharing one lockfile (a workspace) are planned together.
        groups: dict[Path, list[Manifest]] = {}
        for m in self.manifests:
            groups.setdefault(m.relock[0] if m.relock else m.dir, []).append(m)
        reached = {
            key: [self._steps(m, name, self._parents(m, name)) for m in g] for key, g in groups.items()
        }
        covered = {m.name for k, g in groups.items() for m, (s, _) in zip(g, reached[k], strict=True) if s}
        steps: list[str] = []
        via: list[str] = []
        for key, group in groups.items():
            found = reached[key]
            if not any(more for more, _ in found):
                found = self._unreached(key, group, name, covered)
            steps += [s for more, _ in found for s in more]
            via += [v for _, why in found for v in why]
        if apps := [v.removeprefix(PINNED) for v in via if v.startswith(PINNED)]:
            first = next(i for i, v in enumerate(via) if v.startswith(PINNED))
            via = [v for v in via if not v.startswith(PINNED)]
            via.insert(first, f"pinned by the Flutter SDK; only removable with the app ({', '.join(apps)})")
        if not via:
            via.append("stale: no ~/src project reaches it, so only its cache entries are deleted")
        return joined([*steps, cache_step]), "; ".join(dict.fromkeys([*via, *([note] if note else [])]))


def apply(items: Iterable[Item], planner: Planner, cache_step: CacheStep) -> None:
    """Fill removeCommand and removeVia of every item in place."""
    todo = list(items)
    for item in progress.counted(todo[0].source if todo else "", todo):
        step, note = cache_step(item.name)
        item.removeCommand, item.removeVia = planner.plan(item.name, step, note)
