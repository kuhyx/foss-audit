"""Gradle version catalogs: which artifact each alias names, and where builds reference it.

A catalog is `gradle/<name>.versions.toml`. `libs` is Gradle's implicit one
(`gradle/libs.versions.toml` next to the settings file); others are named in
the settings file (`create("sylibs") { from(files("gradle/sy.versions.toml")) }`,
which an included build like gradle/build-logic also uses to re-import its
parent's). A build file sees the catalogs of its nearest enclosing settings file.

Aliases normalise `-`, `_` and `.` to one separator: `okhttp_logging` is
`libs.okhttp.logging` in a build file and "okhttp-logging" in a bundle.
Removing an alias means its entry line, every line that references it, and
its name inside each `[bundles]` array (the bundle itself stays: it pulls in
its other members).
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Edit = Literal["delete", "hand", "unbundle"]
# (artifact name or "" for a reference that is not one, start offset, end offset)
Ref = tuple[str, int, int]
SETTINGS = ("settings.gradle", "settings.gradle.kts")
CREATE = re.compile(r"""create\(\s*["'](\w+)["']\s*\)\s*\{\s*from\(\s*files\(\s*["']([^"']+)["']""")
SECTION = re.compile(r"^\s*\[\s*([\w.\-]+)\s*\]")
KEY = re.compile(r"""^\s*["']?([\w.\-]+)["']?\s*=""")
MEMBER_LINE = re.compile(r"""^\s*["']([\w.\-]+)["']\s*,?\s*(#.*)?$""")
STRING = re.compile(r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'""")
# libs.a.b.c, maximal: a prefix alias never matches a longer reference.
CHAIN = re.compile(r"(?<![\w.])([A-Za-z_]\w*)((?:\.[A-Za-z_]\w*)+)")
# Provider calls that may end an accessor: libs.plugins.x.get().pluginId
CALLS = frozenset({"get", "asProvider"})


def normal(alias: str) -> str:
    """An alias with every separator made `.`, as its accessor spells it."""
    return re.sub(r"[-_.]", ".", alias)


def depth(line: str, comment: str) -> int:
    """Brackets the line opens minus those it closes, strings and comment ignored."""
    code = STRING.sub('""', line).split(comment, 1)[0]
    return sum(code.count(c) for c in "([{") - sum(code.count(c) for c in ")]}")


@dataclass
class Catalog:
    """One parsed catalog: alias -> artifact, and the edits that remove each artifact."""

    libraries: dict[str, str] = field(default_factory=dict)
    plugins: dict[str, str] = field(default_factory=dict)
    # (artifact name, line, line text, edit, bundle member alias)
    edits: list[tuple[str, int, str, Edit, str]] = field(default_factory=list)


def _module(value: Any) -> str:
    """ "g:a" of a [libraries] value: "g:a:v", {module = "g:a"} or {group, name}."""
    if isinstance(value, str):
        return ":".join(value.split(":")[:2]) if ":" in value else ""
    if not isinstance(value, dict):
        return ""
    if "module" in value:
        return str(value["module"])
    return f"{value['group']}:{value['name']}" if {"group", "name"} <= value.keys() else ""


def _plugin(value: Any) -> str:
    """The marker artifact of a [plugins] value: "id:version" or {id = ...}."""
    if isinstance(value, str):
        plugin_id = value.split(":")[0]
    else:
        plugin_id = str(value.get("id", "")) if isinstance(value, dict) else ""
    return f"{plugin_id}:{plugin_id}.gradle.plugin" if plugin_id else ""


def _spans(lines: list[str]) -> dict[tuple[str, str], tuple[int, int]]:
    """(section, key) -> (first line, last line) of every top-level entry, 1-based.
    A `[libraries.alias]` sub-table counts as one entry spanning its body."""
    spans: dict[tuple[str, str], tuple[int, int]] = {}
    section, last, open_entry, level = "", "", None, 0
    for number, line in enumerate(lines, 1):
        header = SECTION.match(line) if level == 0 else None
        if header:
            table, _, sub = header.group(1).partition(".")
            section, open_entry = (table, (table, sub)) if sub else (table, None)
            if sub:
                spans[(table, sub)] = (number, number)
            continue
        if open_entry is not None:
            spans[open_entry] = (spans[open_entry][0], number)
            continue
        key = KEY.match(line) if level == 0 else None
        if key:
            spans[(section, key.group(1))] = (number, number)
            last = key.group(1)
        elif level:
            spans[(section, last)] = (spans[(section, last)][0], number)
        level += depth(line, "#")
    return spans


def read_catalog(path: Path) -> Catalog | None:
    """The catalog at `path`, or None when it is not valid TOML."""
    text = path.read_text(errors="replace")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None
    lines = text.splitlines()
    spans = _spans(lines)
    cat = Catalog()
    for section, read, into in (("libraries", _module, cat.libraries), ("plugins", _plugin, cat.plugins)):
        for key, value in data.get(section, {}).items():
            name = read(value)
            if not name:
                continue
            into[normal(key)] = name
            # A dotted or oddly quoted key has no line of its own: left to a human.
            first, last = spans.get((section, key), (1, 0))
            edit: Edit = "delete" if first == last else "hand"
            cat.edits.append((name, first, lines[first - 1], edit, ""))
    for key, members in data.get("bundles", {}).items():
        first, last = spans.get(("bundles", key), (1, 0))
        for member in members if isinstance(members, list) else []:
            alias = str(member)
            name = cat.libraries.get(normal(alias), "")
            if name and first == last:
                cat.edits.append((name, first, lines[first - 1], "unbundle", alias))
            elif name:
                quoted = re.compile(rf"""["']{re.escape(alias)}["']""")
                number = next((n for n in range(first, last + 1) if quoted.search(lines[n - 1])), first)
                alone = MEMBER_LINE.match(lines[number - 1])
                cat.edits.append((name, number, lines[number - 1], "delete" if alone else "hand", ""))
    return cat


def build_root(path: Path, settings: set[Path], root: Path) -> Path:
    """The directory of the settings file `path` belongs to, else its ~/src repo."""
    top = root / path.relative_to(root).parts[0]
    return next(p for p in path.parents if p == top or any(p / s in settings for s in SETTINGS))


def visible(
    path: Path, settings: dict[Path, str], catalogs: dict[Path, Catalog], root: Path
) -> dict[str, Catalog]:
    """Accessor name -> catalog, for a build file at `path`."""
    base = build_root(path, set(settings), root)
    named = {"libs": base / "gradle/libs.versions.toml"}
    for name in SETTINGS:
        text = settings.get(base / name, "")
        named |= {acc: Path(os.path.normpath(base / rel)) for acc, rel in CREATE.findall(text)}
    return {acc: catalogs[p] for acc, p in named.items() if p in catalogs}


def references(text: str, cats: dict[str, Catalog]) -> list[Ref]:
    """Every catalog accessor in a build file; "" names a bundle or unknown alias."""
    refs: list[Ref] = []
    for match in CHAIN.finditer(text):
        cat = cats.get(match.group(1))
        parts = match.group(2)[1:].split(".")
        while parts[-1] in CALLS and len(parts) > 1:
            parts.pop()
        if cat is None or parts[0] == "versions":
            continue
        if parts[0] == "plugins":
            name = cat.plugins.get(".".join(parts[1:]), "")
        else:
            name = "" if parts[0] == "bundles" else cat.libraries.get(".".join(parts), "")
        refs.append((name, match.start(), match.end()))
    return refs
