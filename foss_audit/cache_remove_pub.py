"""Remove commands for pub-cache items (see cache_remove for the rules).

Projects are the ~/src pubspec.yaml files (build output and plugin symlink
trees are not). `flutter pub remove` when the pubspec depends on the Flutter
SDK, else `dart pub remove`, always in the declaring package's directory (a
workspace member's own). pubspec.lock records no edges, so the graph is the
cached pubspecs' dependencies; a package the lock lists that no cached chain
reaches comes from an SDK package (flutter, flutter_test...), whose pubspec is
not in the cache, so those are blamed (fallback). Path dependencies are local.
The cache step deletes hosted/<server>/<name>-<ver> (+ its hosted-hashes
entry) and whole git checkouts, naming the other packages a checkout holds.
"""

from __future__ import annotations

import re
import shlex
from functools import partial
from pathlib import Path

from foss_audit.cache_common import CachedArtifact
from foss_audit.cache_remove import Manifest, Planner, apply, cache_graph, nearest, projects, repo_of, rm
from foss_audit.model import Item
from foss_audit.scan_cache_pub_parse import declared_deps, lock_packages, parse_pubspec

FLUTTER_SDK = re.compile(r"sdk:\s*flutter\b")
LOCK_FLUTTER = re.compile(r"^  flutter:", re.MULTILINE)


def _read(path: Path) -> str:
    # Only files project_files / nearest just found; like the pub scanner, unguarded.
    return path.read_text(errors="replace")


def _tool(flutter: bool) -> str:
    return "flutter" if flutter else "dart"


def render(tool: str, _kind: str, names: list[str]) -> str:
    """`dart|flutter pub remove <names>` (it finds them in any dependency section)."""
    return f"{tool} pub remove {' '.join(map(shlex.quote, names))}"


def manifests(root: Path) -> list[Manifest]:
    """Every ~/src pubspec.yaml; its local packages are its path deps and its workspace's members."""
    found: list[tuple[Manifest, set[str]]] = []
    locks: dict[Path, frozenset[str]] = {}
    members: dict[Path, set[str]] = {}
    for path in projects(["pubspec.yaml"], root, lock="pubspec.lock"):
        text = _read(path)
        m = Manifest(path.parent, partial(render, _tool(bool(FLUTTER_SDK.search(text)))))
        deps = declared_deps(text)
        for name, _source in deps:
            m.declare(name, "")
        m.fallback = tuple(name for name, source in deps if source == "sdk")
        lock = nearest(path.parent, ["pubspec.lock"], repo_of(path, root))
        if lock:
            lock_text = _read(lock)
            m.locked = locks.setdefault(lock, frozenset(lock_packages(lock_text)))
            m.relock = (lock.parent, f"{_tool(bool(LOCK_FLUTTER.search(lock_text)))} pub get")
        members.setdefault(lock or path, set()).add(parse_pubspec(text).name)
        found.append((m, {name for name, source in deps if source == "path"}))
    for m, paths in found:
        m.local = frozenset(
            paths | members[m.relock[0] / "pubspec.lock" if m.relock else m.dir / "pubspec.yaml"]
        )
    return [m for m, _ in found]


class CacheDirs:
    """Exact pub-cache paths per package: hosted versions, their hashes, git checkouts."""

    def __init__(self, cache: Path, git: dict[Path, list[str]]) -> None:
        self.paths: dict[str, list[Path]] = {}
        for server in sorted((cache / "hosted").glob("*/")):
            for folder in sorted(server.iterdir()):
                name = folder.name.partition("-")[0]
                if folder.is_dir() and not folder.name.startswith("."):
                    sha = cache / "hosted-hashes" / server.name / f"{folder.name}.sha256"
                    self.paths.setdefault(name, []).extend([folder, *([sha] if sha.is_file() else [])])
        self.git = git
        for checkout, names in git.items():
            for name in names:
                self.paths.setdefault(name, []).append(checkout)

    def step(self, name: str) -> tuple[str, str]:
        """`rm -rf` of every cached copy of `name`, and what else a git checkout holds."""
        paths = self.paths.get(name, [])
        notes = [
            f"the git checkout {checkout.name} also holds {', '.join(others)}"
            for checkout in paths
            if (others := sorted(set(self.git.get(checkout, [])) - {name}))
        ]
        return rm(paths), "; ".join(notes)


def fill(
    items: list[Item], arts: list[CachedArtifact], cache: Path, root: Path, git: dict[Path, list[str]]
) -> None:
    """Set removeCommand and removeVia on every pub-cache item."""
    apply(items, Planner(manifests(root), cache_graph(arts)), CacheDirs(cache, git).step)
