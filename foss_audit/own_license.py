"""Find the license of code that lives in a local checkout.

kuhy's scripts, editable pip installs and `npm link`s carry no package
metadata, so the license comes from the checkout itself: a LICENSE/COPYING
file, else the pyproject.toml / package.json license field. Loose copies in
~/.local/bin are traced back to the kuhyx repo that tracks a file of the same
name. A local-only repo (no remote) directly under ~/src is kuhy's too.
Local only: no network, so a fresh LICENSE shows up on the next scan.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tomllib
from functools import cache
from pathlib import Path

HOME = Path.home()
# Where kuhy's checkouts live; ~/.claude is itself a kuhyx repo.
REPO_ROOTS = (HOME / "src",)
EXTRA_REPOS = (HOME / ".claude",)
OWN_MARKER = "github.com/kuhyx/"
REPO_SLUG = re.compile(r"github\.com[/:]kuhyx/([\w.-]+?)(?:\.git)?(?=[/#?\s]|$)", re.MULTILINE)
SOURCE_EXT = re.compile(r"\.(sh|bash|py|dart|go|rs|c|cc|cpp|js|ts)$")
LICENSE_FILE = re.compile(r"(?i)^(licen[cs]e|copying)([.-].*)?$")
# Distinctive phrase of each common license text. The phrase that appears
# EARLIEST wins: a file's own license comes first, the licenses of bundled parts
# it mentions later (Proton's BSD header, then "Wine ... under the LGPL"). An
# AGPL/LGPL header precedes the plain GPL wording its own text contains.
TEXT_IDS = (
    ("SIL Open Font License", "OFL-1.1"),
    ("GNU AFFERO GENERAL PUBLIC LICENSE", "AGPL-3.0"),
    ("GNU LESSER GENERAL PUBLIC LICENSE", "LGPL"),
    ("GNU GENERAL PUBLIC LICENSE", "GPL"),
    ("Apache License", "Apache-2.0"),
    ("Mozilla Public License", "MPL-2.0"),
    ("Permission is hereby granted, free of charge", "MIT"),
    ("Redistribution and use in source and binary forms", "BSD"),
    ("Permission to use, copy, modify, and/or distribute", "ISC"),
    ("This is free and unencumbered software", "Unlicense"),
)


def identify(text: str) -> str:
    """SPDX-ish id of a license text, or its first line when unrecognised."""
    lower = text.lower()
    hits = [(lower.find(phrase.lower()), i) for i, (phrase, _) in enumerate(TEXT_IDS)]
    found = [h for h in hits if h[0] >= 0]
    if found:
        return TEXT_IDS[min(found)[1]][1]
    first = text.strip().splitlines()
    return first[0][:80] if first else ""


def repo_root(path: Path) -> Path | None:
    """The nearest enclosing git checkout (a `.git` dir or worktree file)."""
    return next((p for p in [path, *path.parents] if (p / ".git").exists()), None)


def _git_config(root: Path) -> Path:
    dot_git = root / ".git"
    if dot_git.is_dir():
        return dot_git / "config"
    # Worktree/submodule: ".git" is a "gitdir: <path>" pointer file.
    gitdir = (root / dot_git.read_text().split(":", 1)[1].strip()).resolve()
    own = gitdir / "config"
    return own if own.is_file() else gitdir.parent.parent / "config"


def is_kuhy_repo(root: Path) -> bool:
    """True when the checkout is kuhy's: a remote under github.com/kuhyx/, or a
    local-only repo (no `[remote ` section at all) sitting directly under one of
    the REPO_ROOTS. A repo with anyone else's remote stays not-own."""
    config = _git_config(root)
    if not config.is_file():
        return False
    text = config.read_text(errors="replace")
    return "kuhyx/" in text or ("[remote " not in text and root.parent in REPO_ROOTS)


def _manifest_license(directory: Path) -> str:
    pyproject = directory / "pyproject.toml"
    if pyproject.is_file():
        lic = tomllib.loads(pyproject.read_text()).get("project", {}).get("license", "")
        if isinstance(lic, dict):
            lic = lic.get("text", "")
        if lic:
            return str(lic)
    package = directory / "package.json"
    if package.is_file():
        return str(json.loads(package.read_text()).get("license") or "")
    return ""


def declared_license(start: Path, stop: Path) -> str:
    """Walk from `start` up to `stop`; the nearest LICENSE file or manifest wins."""
    for directory in [start, *start.parents]:
        files = sorted(p for p in directory.glob("*") if LICENSE_FILE.match(p.name) and p.is_file())
        if files:
            return identify(files[0].read_text(errors="replace"))
        lic = _manifest_license(directory)
        if lic or directory in (stop, HOME):
            return lic
    return ""


def license_for_path(path: Path) -> tuple[str, bool]:
    """(license, own) for a file inside a checkout or package directory.

    Outside a checkout only a package dir (one with a manifest) counts: a stray
    ~/.local/share/COPYING must not license every app installed below it.
    """
    root = repo_root(path.parent)
    if root is not None:
        return declared_license(path.parent, root), is_kuhy_repo(root)
    package = next((p for p in [path.parent, *path.parents] if is_package(p)), None)
    return (declared_license(package, package) if package else ""), False


def is_package(directory: Path) -> bool:
    """A named package root; a bare dependency list (~/.local/package.json) is not one."""
    package = directory / "package.json"
    if package.is_file() and "name" in json.loads(package.read_text()):
        return True
    pyproject = directory / "pyproject.toml"
    return pyproject.is_file() and "name" in tomllib.loads(pyproject.read_text()).get("project", {})


@cache
def kuhy_repos() -> tuple[Path, ...]:
    """Every kuhyx checkout directly under the repo roots, plus ~/.claude."""
    found = [p for r in REPO_ROOTS if r.is_dir() for p in sorted(r.iterdir()) if (p / ".git").exists()]
    found += [p for p in EXTRA_REPOS if (p / ".git").exists()]
    return tuple(p for p in found if is_kuhy_repo(p))


def checkout_for_url(url: str) -> Path | None:
    """The local checkout of a github.com/kuhyx/<repo> URL, matched by its remote.

    AUR packages and VCS pip installs only record the GitHub URL, and the
    checkout dir name can differ from the repo (kuhyx/todo-app is ~/src/todo).
    """
    want = REPO_SLUG.search(url)
    if want is None:
        return None
    for repo in kuhy_repos():
        remotes = REPO_SLUG.findall(_git_config(repo).read_text(errors="replace"))
        if want.group(1).lower() in {r.lower() for r in remotes}:
            return repo
    return None


def script_key(name: str) -> str:
    """Install names drop the extension and swap _ for - (keepass_consolidate.sh
    is installed as keepass-consolidate; book_guard_desktop is compiled from
    book_guard_desktop.dart), so match on that normal form."""
    key = name.lower().replace("_", "-")
    return SOURCE_EXT.sub("", key)


@cache
def tracked_by_name() -> dict[str, tuple[Path, ...]]:
    """script_key -> tracked paths across kuhy's repos (one `git ls-files` each).

    A file's own name wins; its directory's name is the fallback, because a C
    program is often built from `<name>/main.c` (imageviewer <- C/imageViewer/main.c).
    """
    index: dict[str, list[Path]] = {}
    by_dir: dict[str, list[Path]] = {}
    for repo in kuhy_repos():
        out = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-z"], capture_output=True, text=True, check=False
        ).stdout
        for rel in filter(None, out.split("\0")):
            path = Path(rel)
            index.setdefault(script_key(path.name), []).append(repo / rel)
            if path.parent.name:
                by_dir.setdefault(script_key(path.parent.name), []).append(repo / rel)
    # Within a directory, name the entry point first: main.c over .clang-format.
    for paths in by_dir.values():
        paths.sort(key=lambda p: (p.stem.lower() != "main", not SOURCE_EXT.search(p.name)))
    return {k: tuple(v) for k, v in (by_dir | index).items()}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def origin_of(script: Path) -> Path | None:
    """The tracked repo file a loose script was copied (or a binary built) from.

    Identical content wins, else the first same-named tracked file.
    """
    candidates = tracked_by_name().get(script_key(script.name), ())
    want = _digest(script)
    return next((c for c in candidates if _digest(c) == want), candidates[0] if candidates else None)
