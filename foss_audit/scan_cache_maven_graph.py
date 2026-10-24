"""The cached Maven dependency graph a removal walks to find who pulls an artifact in.

Edges are each artifact's runtime dependencies over ALL its cached versions
(a version no project uses any more only over-reports, never hides a user) plus
the `<parent>` POM of every cached POM: a parent is downloaded because its
child is, so it is that child's to remove. Import-scoped BOMs inside a POM's
dependencyManagement are not edges (parse_pom does not read them).
"""

from __future__ import annotations

from collections import deque

from foss_audit.cache_common import CachedArtifact
from foss_audit.scan_cache_maven_pom import Gav, parse_pom
from foss_audit.scan_cache_maven_resolve import VersionFiles

Graph = dict[str, set[str]]


def dependency_graph(arts: list[CachedArtifact], versions: dict[Gav, VersionFiles]) -> Graph:
    """group:artifact -> the group:artifacts its cached POMs depend on or inherit from."""
    graph = {art.name: {dep for cv in art.versions for dep in cv.deps} for art in arts}
    for (group, artifact, _), files in sorted(versions.items()):
        for path in files.poms:
            pom = parse_pom(path.read_bytes())
            if pom is not None and pom.parent is not None:
                graph.setdefault(f"{group}:{artifact}", set()).add(f"{pom.parent[0]}:{pom.parent[1]}")
    return graph


def reach(root: str, graph: Graph) -> dict[str, str]:
    """Every name `root` pulls in -> the one before it on a shortest chain ("" for root)."""
    before = {root: ""}
    queue = deque([root])
    while queue:
        node = queue.popleft()
        for dep in sorted(graph.get(node, ())):
            if dep not in before:
                before[dep] = node
                queue.append(dep)
    return before


def chain(before: dict[str, str], name: str) -> list[str]:
    """The shortest chain from the root of `before` down to `name`."""
    path = [name]
    while before[path[-1]]:
        path.append(before[path[-1]])
    return path[::-1]
