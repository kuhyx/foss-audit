"""Reading one cached crate (a .crate archive, an extracted dir or a git checkout) into a Manifest.

The cache is untrusted: everything is read-only and size-capped, nothing runs.
"""

from __future__ import annotations

import tarfile
import tomllib
import zlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from foss_audit.own_license import LICENSE_FILE

# Manifests and license texts are small; anything bigger is not read whole.
MAX_READ = 512 * 1024
READ_ERRORS = (OSError, EOFError, tarfile.TarError, zlib.error, UnicodeDecodeError, tomllib.TOMLDecodeError)


@dataclass
class Manifest:
    """What one crate copy says about itself, plus the license texts it holds."""

    where: str
    stem: str
    package: dict[str, Any] = field(default_factory=dict)
    deps: dict[str, Any] = field(default_factory=dict)
    texts: dict[str, str] = field(default_factory=dict)
    error: str = ""
    # (db dir, rev dir) of a git checkout under ~/.cargo/git/checkouts, else None.
    git: tuple[str, str] | None = None


def _decode(data: bytes) -> str:
    return data[:MAX_READ].decode("utf-8", errors="replace")


def table(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse(m: Manifest, text: str) -> None:
    data = tomllib.loads(text)
    m.package = table(data.get("package"))
    m.deps = table(data.get("dependencies"))


def _needs_files(m: Manifest) -> bool:
    return not isinstance(m.package.get("license"), str)


def _wanted(m: Manifest) -> Callable[[str], bool]:
    """Relative paths whose text the license fallback reads."""
    named = m.package.get("license-file")
    return lambda rel: rel == named or ("/" not in rel and bool(LICENSE_FILE.match(rel)))


def _members(path: Path) -> Iterator[tuple[str, tarfile.TarFile, tarfile.TarInfo]]:
    """(path below the crate's top dir, archive, member) for each regular file."""
    with tarfile.open(path, "r|gz") as tf:
        for member in tf:
            top, _, rel = member.name.partition("/")
            if member.isfile() and top == path.name.removesuffix(".crate"):
                yield rel, tf, member


def _read(tf: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    handle = tf.extractfile(member)
    return _decode(handle.read(MAX_READ)) if handle else ""


def read_crate(path: Path) -> Manifest:
    """Cargo.toml (stream stops there), then license texts only when needed."""
    m = Manifest(".crate", path.name.removesuffix(".crate"))
    try:
        for rel, tf, member in _members(path):
            if rel == "Cargo.toml":
                _parse(m, _read(tf, member))
                break
        if _needs_files(m):
            # A second pass: COPYING/LICENSE may sit before Cargo.toml in the tar.
            wanted = _wanted(m)
            m.texts = {rel: _read(tf, member) for rel, tf, member in _members(path) if wanted(rel)}
    except READ_ERRORS as exc:
        m.error = f"unreadable {path.name}: {type(exc).__name__}: {exc}"
    return m


def read_dir(path: Path, where: str) -> Manifest:
    """An extracted crate or git checkout (read-only, no path escapes)."""
    m = Manifest(where, path.name)
    try:
        _parse(m, _decode((path / "Cargo.toml").read_bytes()))
        if _needs_files(m):
            wanted = _wanted(m)
            names = [p.name for p in path.iterdir()] + [str(m.package.get("license-file", ""))]
            for rel in filter(wanted, names):
                file = (path / rel).resolve()
                if file.is_file() and file.is_relative_to(path.resolve()):
                    m.texts[rel] = _decode(file.read_bytes())
    except READ_ERRORS as exc:
        m.error = f"unreadable {path}/Cargo.toml: {type(exc).__name__}: {exc}"
    return m


def read_git_checkout(toml: Path) -> Manifest | None:
    """A git checkout's Cargo.toml (None for a workspace-only root, which has no [package])."""
    m = read_dir(toml.parent, f"git checkout {toml.parent.parent.name}/{toml.parent.name}")
    if not (m.package or m.error):
        return None
    m.git = (toml.parent.parent.name, toml.parent.name)
    return m
