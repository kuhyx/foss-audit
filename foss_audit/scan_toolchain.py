"""Scan language toolchains and their global tools (source "toolchain").

Version managers (rustup, pyenv, nvm, fvm, a plain Go SDK) install a whole
toolchain per version; they are reported as ONE item per family with every
installed version in `version`. Globally installed third-party tools (.NET
tools, Dart `pub global` packages, user-level gems) get one item each.

A real LICENSE file that the toolchain ships wins over the constant for the
family; the constant is the fallback.
"""

from __future__ import annotations

import re
from pathlib import Path

from foss_audit.licenses import classify_text
from foss_audit.model import Item, Verdict
from foss_audit.own_license import identify
from foss_audit.scan_toolchain_tools import (
    SOURCE,
    first_text,
    natural_key,
    scan_dotnet_tools,
    scan_gems,
    scan_go_bins,
    scan_pub_global,
    subdirs,
)

HOME = Path.home()

# rustup names a toolchain "<version|channel>-<host triple>".
HOST_TRIPLE = re.compile(r"-(x86_64|aarch64|i686|armv7\w*|riscv64\w*)-.*$")


def classify_license_text(text: str) -> tuple[Verdict, str]:
    """Verdict of a whole LICENSE file: its wording or its recognised id may be the free one.

    The MIT and BSD texts never say "MIT" or "BSD", so the wording alone is not enough.
    """
    verdict, reason = classify_text(text)
    if verdict == "foss":
        return verdict, reason
    return classify_text(identify(text))


def family_item(name: str, spdx: str, versions: list[str], files: list[Path], where: str) -> Item:
    """One item for a toolchain family; a shipped license text beats the constant `spdx`."""
    text = first_text(files)
    verdict, reason = classify_license_text(text) if text else classify_text(spdx)
    return Item(
        name=name,
        source=SOURCE,
        version=", ".join(sorted(versions, key=natural_key)),
        verdict=verdict,
        license=spdx,
        reason="; ".join(r for r in (where, reason) if r),
    )


def family(name: str, spdx: str, dirs: list[Path], globs: tuple[str, ...], where: str) -> list[Item]:
    """The family item for version directories `dirs`; none when no version is installed.

    License files are looked up newest version first.
    """
    if not dirs:
        return []
    files = [f for d in reversed(dirs) for g in globs for f in sorted(d.glob(g))]
    return [family_item(name, spdx, [_label(d) for d in dirs], files, where)]


def _label(directory: Path) -> str:
    """Version label of a toolchain directory (rustup drops its host triple)."""
    return HOST_TRIPLE.sub("", directory.name)


def is_real_python(path: Path) -> bool:
    """A pyenv version that is an interpreter, not a virtualenv or a link to one."""
    if path.is_symlink() or (path / "pyvenv.cfg").exists():
        return False
    return any((path / "bin").glob("python*"))


def scan_rust() -> list[Item]:
    """Rust toolchains installed by rustup."""
    return family(
        "rust (rustup)",
        "MIT OR Apache-2.0",
        subdirs(HOME / ".rustup/toolchains"),
        ("share/doc/rust/LICENSE-MIT", "share/doc/rust/LICENSE-APACHE", "share/doc/rust/licenses/MIT.txt"),
        "~/.rustup/toolchains",
    )


def scan_pyenv() -> list[Item]:
    """CPython interpreters installed by pyenv (virtualenvs excluded)."""
    dirs = [p for p in subdirs(HOME / ".pyenv/versions") if is_real_python(p)]
    return family("python (pyenv)", "PSF-2.0", dirs, ("lib/python*/LICENSE.txt",), "~/.pyenv/versions")


def scan_nvm() -> list[Item]:
    """Node.js versions installed by nvm."""
    return family(
        "node (nvm)", "MIT", subdirs(HOME / ".nvm/versions/node"), ("LICENSE",), "~/.nvm/versions/node"
    )


def scan_fvm() -> list[Item]:
    """Flutter SDK versions installed by fvm."""
    return family(
        "flutter (fvm)",
        "BSD-3-Clause",
        subdirs(HOME / "sdk/fvm/versions"),
        ("LICENSE",),
        "~/sdk/fvm/versions",
    )


def scan_go() -> list[Item]:
    """The Go SDK in ~/sdk/go; a directory without bin/go is only a GOPATH."""
    root = HOME / "sdk/go"
    if not (root / "bin/go").is_file():
        return []
    marker = root / "VERSION"
    # First line is "go1.22.3"; the second is a build timestamp.
    version = marker.read_text().partition("\n")[0].removeprefix("go") if marker.is_file() else ""
    item = family_item("go", "BSD-3-Clause", [version] if version else [], [root / "LICENSE"], "~/sdk/go")
    item.version = version or None
    return [item]


def scan_toolchains() -> list[Item]:
    """Every toolchain family plus the global tools installed into them."""
    return [
        *scan_rust(),
        *scan_pyenv(),
        *scan_nvm(),
        *scan_fvm(),
        *scan_go(),
        *scan_dotnet_tools(HOME),
        *scan_pub_global(HOME),
        *scan_gems(HOME),
        *scan_go_bins(HOME),
    ]
