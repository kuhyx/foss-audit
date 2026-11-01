"""Dependency chains from a manifest's declared roots, for the remove-command planner."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

Graph = dict[str, set[str]]
Decl = tuple[str, str]
Render = Callable[[str, list[str]], str]


@dataclass
class Manifest:
    """One project directory and what it declares, plus the lockfile it resolves into."""

    dir: Path
    render: Render
    direct: dict[str, list[Decl]] = field(default_factory=dict)
    edges: Graph = field(default_factory=dict)
    locked: frozenset[str] = frozenset()
    relock: tuple[Path, str] | None = None
    fallback: tuple[str, ...] = ()
    local: frozenset[str] = frozenset()
    name: str = ""

    def declare(self, name: str, kind: str, token: str | None = None) -> None:
        decls = self.direct.setdefault(name, [])
        if (kind, token or name) not in decls:
            decls.append((kind, token or name))


class Reach:
    """Shortest chains from a manifest's roots; the lockfile wins over the cache's own edges."""

    def __init__(self, cache_edges: Graph) -> None:
        self.cache_edges = cache_edges
        self._walks: dict[tuple[int, str], dict[str, str]] = {}
        self._reaching: dict[int, dict[str, list[str]]] = {}

    def walk(self, m: Manifest, root: str) -> dict[str, str]:
        """Node -> its predecessor on a shortest chain from `root` (breadth first)."""
        key = (id(m), root)
        if key not in self._walks:
            prev = {root: ""}
            queue = deque([root])
            while queue:
                node = queue.popleft()
                edges = m.edges[node] if node in m.edges else self.cache_edges.get(node, set())
                for nxt in sorted(edges):
                    if nxt not in prev and nxt not in m.local:
                        prev[nxt] = node
                        queue.append(nxt)
            self._walks[key] = prev
        return self._walks[key]

    def chain(self, m: Manifest, root: str, name: str) -> list[str]:
        prev, chain = self.walk(m, root), [name]
        while prev[chain[-1]]:
            chain.append(prev[chain[-1]])
        return chain[::-1]

    def roots_reaching(self, m: Manifest) -> dict[str, list[str]]:
        """Node -> the declared roots (sorted) whose chains reach it; one pass per manifest."""
        if id(m) not in self._reaching:
            reaching: dict[str, list[str]] = {}
            for root in (r for r in sorted(m.direct) if r not in m.local and r not in m.fallback):
                for node in self.walk(m, root):
                    reaching.setdefault(node, []).append(root)
            self._reaching[id(m)] = reaching
        return self._reaching[id(m)]

    def parents(self, m: Manifest, name: str) -> list[tuple[str, str]]:
        roots = (r for r in self.roots_reaching(m).get(name, ()) if r != name)
        return [(r, " → ".join(self.chain(m, r, name))) for r in roots]
