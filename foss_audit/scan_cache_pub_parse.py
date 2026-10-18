"""Line-based readers for pubspec.yaml and pubspec.lock (stdlib only, no PyYAML).

Only the handful of top-level keys the pub-cache scanner needs: `name`,
`version`, `repository`/`homepage` and the keys of the `dependencies:` block.
A dependency whose nested block (or inline map) names an `sdk:` is part of the
Flutter/Dart SDK, not a package in the cache, so it is left out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TOP_KEY = re.compile(r"^([A-Za-z_][\w-]*):\s*(.*)$")
CHILD_KEY = re.compile(r"^  ([A-Za-z_]\w*):\s*(.*)$")


@dataclass
class Pubspec:
    """The fields of a pubspec.yaml the scanner uses."""

    name: str = ""
    version: str = ""
    url: str = ""
    deps: tuple[str, ...] = ()


def scalar(raw: str) -> str:
    """A YAML scalar without its trailing `# comment` and surrounding quotes."""
    value = re.sub(r"\s+#.*$", "", raw).strip()
    return value.strip("\"'")


def _blocks(text: str) -> dict[str, list[str]]:
    """Top-level key -> [inline value, nested lines...]."""
    blocks: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        top = TOP_KEY.match(line)
        if top:
            current = blocks.setdefault(top.group(1), [top.group(2)])
        elif current is not None and line.startswith(" "):
            current.append(line)
    return blocks


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _runtime_deps(lines: list[str]) -> tuple[str, ...]:
    """Keys of a `dependencies:` block, minus SDK packages (`sdk: flutter`).

    The key indent is the block's first line's (2 spaces usually, 4 in some).
    """
    nested = [line for line in lines[1:] if line.strip() and not line.lstrip().startswith("#")]
    deps: dict[str, bool] = {}
    name = ""
    for line in nested:
        if _indent(line) == _indent(nested[0]):
            key, _, value = line.strip().partition(":")
            name = scalar(key)
            deps[name] = "sdk:" in value
        elif "sdk:" in line:
            deps[name] = True
    return tuple(n for n, sdk in deps.items() if not sdk)


def parse_pubspec(text: str) -> Pubspec:
    """Name, version, repository-or-homepage and runtime deps of a pubspec.yaml."""
    blocks = _blocks(text)

    def top(key: str) -> str:
        return scalar(blocks.get(key, [""])[0])

    return Pubspec(
        name=top("name"),
        version=top("version"),
        url=top("repository") or top("homepage"),
        deps=_runtime_deps(blocks.get("dependencies", [""])),
    )


def lock_packages(text: str) -> list[str]:
    """Package names of a pubspec.lock: the 2-space keys under `packages:`."""
    lines = _blocks(text).get("packages", [""])[1:]
    return [m.group(1) for m in map(CHILD_KEY.match, lines) if m]
