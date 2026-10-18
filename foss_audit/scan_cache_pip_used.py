"""Which ~/src projects name a Python distribution, and which ~/src checkout builds one.

Read from uv.lock, poetry.lock, requirements*.txt and pyproject.toml found by
`cache_common.project_files` (bounded globs, never a recursive walk). A file
that does not parse is skipped: it names nothing we could trust.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from foss_audit.cache_common import project_files, project_of
from foss_audit.scan_cache_pip_meta import REQ_NAME, norm

PROJECT_FILES = ("uv.lock", "poetry.lock", "requirements*.txt", "pyproject.toml")


def _req_names(lines: list[Any]) -> set[str]:
    """Names of PEP 508 requirement strings (non-strings, e.g. group includes, skipped)."""
    names = set()
    for line in lines:
        match = REQ_NAME.match(line) if isinstance(line, str) else None
        if match:
            names.add(norm(match.group(1)))
    return names


def _requirements_txt(text: str) -> set[str]:
    lines = [line.split("#", 1)[0].strip() for line in text.splitlines()]
    return _req_names([line for line in lines if line and not line.startswith("-")])


def _lock_names(data: dict[str, Any]) -> set[str]:
    return {norm(str(p["name"])) for p in data.get("package", []) if isinstance(p, dict) and "name" in p}


def _groups(table: Any) -> list[Any]:
    """Every requirement string of a {group: [req, ...]} table."""
    return (
        [req for reqs in table.values() if isinstance(reqs, list) for req in reqs]
        if isinstance(table, dict)
        else []
    )


def _pyproject_names(data: dict[str, Any]) -> set[str]:
    project = data.get("project", {})
    poetry = data.get("tool", {}).get("poetry", {})
    reqs = [
        *project.get("dependencies", []),
        *_groups(project.get("optional-dependencies")),
        *_groups(data.get("dependency-groups")),
        *data.get("build-system", {}).get("requires", []),
    ]
    poetry_keys = [*poetry.get("dependencies", {})]
    for group in poetry.get("group", {}).values():
        poetry_keys += [*group.get("dependencies", {})]
    return _req_names(reqs) | {norm(k) for k in poetry_keys if k != "python"}


def names_in(path: Path) -> set[str]:
    """Distribution names one project file depends on (or locks)."""
    try:
        text = path.read_text(errors="replace")
        if path.name.startswith("requirements"):
            return _requirements_txt(text)
        data = tomllib.loads(text)
    except OSError, ValueError:
        return set()
    return _pyproject_names(data) if path.name == "pyproject.toml" else _lock_names(data)


def used_by() -> dict[str, set[str]]:
    """Normalised distribution name -> the ~/src repos whose project files name it."""
    found: dict[str, set[str]] = {}
    for path in project_files(PROJECT_FILES):
        for name in names_in(path):
            found.setdefault(name, set()).add(project_of(path))
    return found


def checkouts() -> dict[str, list[Path]]:
    """Normalised project name -> the ~/src directories whose pyproject.toml builds it."""
    found: dict[str, list[Path]] = {}
    for path in project_files(["pyproject.toml"]):
        try:
            name = tomllib.loads(path.read_text(errors="replace")).get("project", {}).get("name")
        except OSError, ValueError:
            continue
        if isinstance(name, str) and name:
            found.setdefault(norm(name), []).append(path.parent)
    return found
