"""removeCommand/removeVia for maven-cache items: gone for good, not just until the next build.

A project that reaches an artifact, by declaring it or by declaring anything
whose cached POM graph pulls it in, would download it again; so the command
first drops from every such project each declaration that reaches it (all
of them, not one chain), then deletes the artifact's cache dirs once. An
artifact no project reaches is stale: the command is just the cache delete.

Per project, `$EDITOR +<line> <file>` steps come first, bottom-up within a
file, so their line numbers still hold; the `sed -i` steps after them match
lines by exact content, so they survive earlier edits and stay a no-op on a
line already gone. Steps are joined by `; ` so one failing step does not hide
the others. Paths under the home directory keep an expandable `~/`.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable
from pathlib import Path

from foss_audit.model import Item
from foss_audit.scan_cache_maven_decl import Decl
from foss_audit.scan_cache_maven_graph import Graph, chain, reach
from foss_audit.scan_cache_maven_pom import Gav
from foss_audit.scan_cache_maven_resolve import VersionFiles

HOME = Path.home()
EDITOR = "${EDITOR:-vi}"
MAX_CHAINS = 5
STALE = "stale: no ~/src project reaches it"
# Special in a sed basic regex delimited by '#'; `]` is literal once `[` is escaped.
BRE_SPECIAL = re.compile(r"([\\.*\[^$#])")
SPACE = "[[:space:]]*"


def shell_path(path: Path) -> str:
    """`path` quoted for a shell, `~/` kept unquoted so it still expands."""
    if path.is_relative_to(HOME):
        return "~/" + shlex.quote(str(path.relative_to(HOME)))
    return shlex.quote(str(path))


def bre(text: str) -> str:
    """`text` as a literal sed basic regex."""
    return BRE_SPECIAL.sub(r"\\\1", text)


def sed_expression(decl: Decl) -> str:
    """Delete the exact line, or drop one member from a [bundles] array line."""
    if decl.edit == "delete":
        return f"\\#^{bre(decl.text)}$#d"
    key = bre(decl.text.split("=", 1)[0].strip().strip("\"'"))
    member = f"[\"']{bre(decl.alias)}[\"']"
    cuts = f"s#{member}{SPACE},{SPACE}##;s#{SPACE},{SPACE}{member}##;s#{member}##"
    # Inside [bundles] only, on that bundle's line, wherever earlier cuts left it.
    return f"\\#^\\[bundles\\]#,\\#^\\[#{{\\#^{SPACE}{key}{SPACE}=#{{{cuts};}};}}"


def project_steps(decls: Iterable[Decl]) -> list[str]:
    """The edits that drop `decls` from one project's files."""
    ordered = sorted(set(decls), key=lambda d: (d.path, d.line, d.alias))
    hand = sorted({(d.path, d.line) for d in ordered if d.edit == "hand"}, key=lambda pl: (pl[0], -pl[1]))
    steps = [f"{EDITOR} +{line} {shell_path(path)}" for path, line in hand]
    seds: dict[Path, dict[str, None]] = {}
    for decl in ordered:
        if decl.edit != "hand":
            seds.setdefault(decl.path, {})[sed_expression(decl)] = None
    for path, expressions in seds.items():
        args = " ".join(f"-e {shlex.quote(e)}" for e in expressions)
        steps.append(f"sed -i {args} {shell_path(path)}")
    return steps


def _via(project: str, name: str, roots: list[str], reached: dict[str, dict[str, str]]) -> str:
    """`~/src/x declares it and via a → b → name, ...`."""
    chains = [" → ".join(chain(reached[root], name)) for root in roots if root != name]
    more = f" and {len(chains) - MAX_CHAINS} more" if len(chains) > MAX_CHAINS else ""
    parts = ["declares it"] if name in roots else []
    if chains:
        parts.append(f"via {', '.join(chains[:MAX_CHAINS])}{more}")
    return f"{project} {' and '.join(parts)}"


def cache_dirs(versions: dict[Gav, VersionFiles], gradle: Path, m2: Path) -> dict[str, list[Path]]:
    """group:artifact -> its dirs in the caches it was found in, Gradle's first."""
    dirs: dict[str, dict[Path, None]] = {}
    for (group, artifact, _), files in sorted(versions.items()):
        for path in [*files.poms, *files.archives]:
            in_gradle = path.is_relative_to(gradle)
            found = gradle / group / artifact if in_gradle else m2.joinpath(*group.split("."), artifact)
            dirs.setdefault(f"{group}:{artifact}", {})[found] = None
    return {name: sorted(found, key=lambda d: not d.is_relative_to(gradle)) for name, found in dirs.items()}


def add_removals(
    items: list[Item], decls: dict[str, list[Decl]], graph: Graph, dirs: dict[str, list[Path]]
) -> None:
    """Fill every item's removeCommand and removeVia."""
    by_project: dict[str, dict[str, list[Decl]]] = {}
    for name, found in decls.items():
        for decl in found:
            by_project.setdefault(decl.project, {}).setdefault(name, []).append(decl)
    reached = {name: reach(name, graph) for name in decls}
    for item in items:
        steps: list[str] = []
        via: list[str] = []
        for project, declared in sorted(by_project.items()):
            roots = sorted(root for root in declared if item.name in reached[root])
            if roots:
                steps += project_steps(decl for root in roots for decl in declared[root])
                via.append(_via(project, item.name, roots, reached))
        steps.append("rm -rf " + " ".join(shell_path(d) for d in dirs[item.name]))
        item.removeCommand = "; ".join(steps)
        item.removeVia = "; ".join(via) or STALE
