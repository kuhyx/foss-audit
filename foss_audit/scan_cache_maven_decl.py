"""Where each ~/src project declares a Maven artifact, line by line, and how to cut it.

Read from the Gradle build and settings files, every `gradle/*.versions.toml`
catalog and Maven `pom.xml`, at most four levels under ~/src:

- a dependency string `"g:a[:v]"`, a `group: "g", name: "a"` map, a plugin
  `id("x")` (its marker artifact `x:x.gradle.plugin`) or a catalog accessor
  (`libs.x.y`, `libs.plugins.z`);
- a catalog's own entry for the alias, and its name inside bundles;
- a pom.xml `<dependency>`/`<plugin>` block.

Each `Decl` says how a removal edits its line: "delete" when the line holds
exactly one whole dependency statement (so deleting it removes exactly that),
"unbundle" to drop one name from a single-line bundle array, else "hand": a
statement spread over several lines, opening a block, sharing its line, or an
assignment, which only a human can cut safely.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from foss_audit.cache_common import project_files, project_of
from foss_audit.scan_cache_maven_catalog import SETTINGS, Edit, Ref, depth, read_catalog, references, visible

GRADLE_FILES = ("build.gradle", "build.gradle.kts", *SETTINGS)
CATALOGS = "gradle/*.versions.toml"
# "group:artifact" or "group:artifact:version" inside quotes.
COORD = re.compile(r"""["']([\w.\-]+):([\w.\-]+)(?::[^"'\s]*)?["']""")
GROUP_NAME = re.compile(r"""group\s*[:=]\s*["']([\w.\-]+)["']\s*,\s*name\s*[:=]\s*["']([\w.\-]+)["']""")
# A plugin id resolves through its marker artifact <id>:<id>.gradle.plugin.
PLUGIN_ID = re.compile(r"""\bid\s*[(=]?\s*["']([\w.\-]+)["']""")
ASSIGNMENT = re.compile(r"^\s*(?:(?:val|var|def)\s|[\w.]+\s*=(?!=))")
POM_BLOCK = re.compile(r"<(dependency|plugin|extension)>(.*?)</\1>", re.DOTALL)
MAVEN_PLUGINS = "org.apache.maven.plugins"


@dataclass(frozen=True)
class Decl:
    """One line of a project file that declares an artifact."""

    project: str
    path: Path
    line: int
    text: str
    edit: Edit
    # "unbundle": the bundle member to drop from the array on `text`.
    alias: str = ""


def matches(text: str) -> list[Ref]:
    """Dependency strings, group/name maps and plugin ids, with their offsets."""
    refs = [(f"{m[1]}:{m[2]}", m.start(), m.end()) for m in COORD.finditer(text)]
    refs += [(f"{m[1]}:{m[2]}", m.start(), m.end()) for m in GROUP_NAME.finditer(text)]
    return refs + [(f"{m[1]}:{m[1]}.gradle.plugin", m.start(), m.end()) for m in PLUGIN_ID.finditer(text)]


def build_file_names(text: str) -> set[str]:
    """`group:artifact` names a Gradle build file or version catalog declares."""
    return {name for name, _, _ in matches(text)}


def _tag(body: str, tag: str) -> str:
    found = re.search(rf"<{tag}>\s*([^<\s]+)\s*</{tag}>", body)
    return found.group(1) if found else ""


def pom_refs(text: str) -> list[Ref]:
    """The <dependency>/<plugin>/<extension> blocks of a pom.xml (plugins default to
    org.apache.maven.plugins); property-valued coordinates name nothing knowable."""
    refs: list[Ref] = []
    for block in POM_BLOCK.finditer(text):
        default = MAVEN_PLUGINS if block.group(1) != "dependency" else ""
        group, artifact = _tag(block.group(2), "groupId") or default, _tag(block.group(2), "artifactId")
        if group and artifact and "${" not in group + artifact:
            refs.append((f"{group}:{artifact}", block.start(), block.end()))
    return refs


def _line_of(text: str) -> tuple[list[str], list[int]]:
    """The lines of `text` and each one's start offset."""
    lines = text.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    return [line.rstrip("\r\n") for line in lines], starts


def line_decls(
    project: str, path: Path, text: str, refs: list[Ref], *, hand: bool = False
) -> list[tuple[str, Decl]]:
    """(name, Decl) per named ref; a line is deletable when it holds one whole statement.
    Unnamed refs (a bundle accessor) still count as sharing their line."""
    lines, starts = _line_of(text)
    line_at = [
        (name, bisect_right(starts, start), bisect_right(starts, end - 1)) for name, start, end in refs
    ]
    per_line = Counter(first for _, first, _ in line_at)
    decls = []
    for name, first, last in line_at:
        line = lines[first - 1]
        whole = first == last and per_line[first] == 1 and depth(line, "//") == 0
        cut = whole and not hand and not line.rstrip().endswith((",", "\\")) and not ASSIGNMENT.match(line)
        if name:
            decls.append((name, Decl(project, path, first, line, "delete" if cut else "hand")))
    return decls


def declarations(root: Path) -> dict[str, list[Decl]]:
    """artifact name -> every line of a ~/src project that declares it."""
    found: dict[str, list[Decl]] = {}

    def add(pairs: list[tuple[str, Decl]]) -> None:
        for name, decl in pairs:
            found.setdefault(name, []).append(decl)

    def read(path: Path) -> str:
        return path.read_text(errors="replace")

    gradle = project_files(GRADLE_FILES, root=root)
    settings = {p: read(p) for p in gradle if p.name in SETTINGS}
    catalogs = {}
    for path in project_files((CATALOGS,), root=root):
        project, cat = project_of(path, root=root), read_catalog(path)
        if cat is None:
            # Not valid TOML: still read for names, every line left to a human.
            text = read(path)
            add(line_decls(project, path, text, matches(text), hand=True))
        else:
            catalogs[path] = cat
            add(
                [
                    (name, Decl(project, path, line, text, edit, alias))
                    for name, line, text, edit, alias in cat.edits
                ]
            )
    for path in gradle:
        text = read(path)
        refs = matches(text) + references(text, visible(path, settings, catalogs, root))
        add(line_decls(project_of(path, root=root), path, text, refs))
    for path in project_files(("pom.xml",), root=root):
        text = read(path)
        add(line_decls(project_of(path, root=root), path, text, pom_refs(text), hand=True))
    return found
