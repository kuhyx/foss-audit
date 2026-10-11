"""Scan .desktop launchers for programs no other scanner accounts for.

A launcher's Exec target is resolved and then dropped when another scanner
already owns it: pacman-owned files, /usr/bin and /usr/local/bin (unowned scan),
~/.local/bin, /opt, ~/.local/share, AppImages the appimage scan finds, Steam,
Flatpak, Wine and Waydroid launchers, and kuhy's own checkouts. What is left is
a program somebody installed by hand (a build in ~/sdk, an installer's private
directory). A launcher whose target is gone is a dead entry: it is reported
with `dangling` set so the UI can offer to delete the .desktop file.
"""

from __future__ import annotations

import configparser
import os
import re
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path

from foss_audit.licenses import classify_text
from foss_audit.model import NO_LICENSE, Item
from foss_audit.own_license import (
    LICENSE_FILE,
    identify,
    is_kuhy_repo,
    license_for_path,
    origin_of,
    repo_root,
)
from foss_audit.scan_misc import unknown
from foss_audit.scan_pacman import owned_by_pacman

HOME = Path.home()
# Highest precedence first (XDG: the user's copy of a launcher wins).
SYSTEM_DIRS = (
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path("/var/lib/flatpak/exports/share/applications"),
)
# Targets in these directories are covered by the scanners named in the module doc.
SYSTEM_COVERED = (Path("/usr/bin"), Path("/usr/local/bin"), Path("/opt"))
HOME_COVERED = (".local/bin", ".local/share")
# AppImages the appimage scanner finds: up to three levels below $HOME.
APPIMAGE_DEPTH = 3
# Wrappers and launchers that belong to another source (steam, flatpak, wine, waydroid scanners).
OTHER_SOURCE = re.compile(r"^(steam|flatpak|waydroid|wine.*)$")
WRAPPERS = frozenset({"env", "exec"})
SHELLS = frozenset({"sh", "bash", "dash", "zsh"})
# Interpreters whose first non-option argument is the program being launched.
INTERPRETERS = re.compile(r"^(python[\d.]*|node|ruby|perl|lua)$")
ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# Discord registers a "Game <id>" stub per game it has seen; the target says more.
GENERIC_NAME = re.compile(r"Game \d+")


@dataclass(frozen=True)
class Launcher:
    """One parsed [Desktop Entry]."""

    path: Path
    name: str
    exec_line: str


def desktop_dirs() -> tuple[Path, ...]:
    """Application directories, user ones first."""
    return (
        HOME / ".local/share/applications",
        *SYSTEM_DIRS[:2],
        HOME / ".local/share/flatpak/exports/share/applications",
        SYSTEM_DIRS[2],
    )


def parse_desktop(path: Path) -> Launcher | None:
    """The launcher in a .desktop file; None when it is not a visible application with an Exec."""
    parser = configparser.ConfigParser(interpolation=None, strict=False, delimiters=("=",))
    parser.optionxform = str  # type: ignore[assignment,method-assign]  # keys are case-sensitive
    try:
        parser.read_string(path.read_text(errors="replace"))
    except configparser.Error:
        return None
    entry = parser["Desktop Entry"] if parser.has_section("Desktop Entry") else {}
    if entry.get("Type") != "Application" or entry.get("Hidden", "").lower() == "true" or "Exec" not in entry:
        return None
    return Launcher(path, entry.get("Name", path.stem), entry["Exec"])


def launchers() -> list[Launcher]:
    """Every launcher; a file name seen in an earlier directory shadows later ones."""
    seen: set[str] = set()
    found: list[Launcher] = []
    for directory in desktop_dirs():
        for path in sorted(directory.glob("*.desktop")) if directory.is_dir() else []:
            launcher = parse_desktop(path) if path.name not in seen else None
            seen.add(path.name)
            if launcher is not None:
                found.append(launcher)
    return found


def split_words(text: str) -> list[str]:
    """Shell-style words; unbalanced quotes degrade to whitespace splitting."""
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def expand_home(word: str) -> str:
    """Substitute $HOME, ${HOME} and a leading ~ (the only variables launchers rely on)."""
    home = str(HOME)
    word = word.replace("${HOME}", home).replace("$HOME", home)
    return home + word[1:] if word.startswith("~/") else word


def exec_command(exec_line: str) -> str | None:
    """The program an Exec line runs, past env/exec/VAR=x and `sh -c '...'` wrappers.

    None when nothing is left, or when the command still holds an unexpanded
    variable (it cannot be located, so it is not called dangling either).
    """
    words = split_words(exec_line)
    wrapped = False
    while words:
        word = words.pop(0)
        if Path(word).name in WRAPPERS or ENV_ASSIGN.match(word) or (wrapped and word.startswith("-")):
            wrapped = True
            continue
        if Path(word).name in SHELLS and words[:1] == ["-c"] and len(words) > 1:
            return exec_command(words[1])
        if INTERPRETERS.match(Path(word).name):
            word = script_of(word, words)
        word = expand_home(word)
        return None if "$" in word else word
    return None


def script_of(interpreter: str, args: list[str]) -> str:
    """The script an interpreter runs (`python3 /opt/x/main.py`); the interpreter for -m/-c/bare."""
    for arg in args:
        if arg in ("-m", "-c"):
            break
        if not arg.startswith("-"):
            return arg
    return interpreter


def locate(command: str) -> Path | None:
    """The file a command names: an existing path, or the first match on PATH."""
    if "/" in command:
        return Path(command) if os.path.exists(command) else None
    found = shutil.which(command)
    return Path(found) if found else None


def other_source(exec_line: str, command: str) -> bool:
    """A Steam/Flatpak/Wine/Waydroid launcher or a URL handler: another scanner's business."""
    return bool(OTHER_SOURCE.match(Path(command).name)) or "://" in command or "steam://" in exec_line


def covered_elsewhere(target: Path) -> bool:
    """Whether a parallel scanner already lists this existing file."""
    if any(target.is_relative_to(root) for root in SYSTEM_COVERED):
        return True
    if any(target.is_relative_to(HOME / sub) for sub in HOME_COVERED):
        return True
    is_appimage = target.suffix.lower() == ".appimage" and target.is_relative_to(HOME)
    return is_appimage and len(target.relative_to(HOME).parts) <= APPIMAGE_DEPTH


def is_kuhys(target: Path) -> bool:
    """Inside one of kuhy's checkouts, or a copy of a file tracked in one."""
    real = target.resolve()
    root = repo_root(real.parent)
    return is_kuhy_repo(root) if root is not None else origin_of(real) is not None


def sibling_license(target: Path) -> str:
    """Identify a LICENSE/COPYING file in the target's own directory."""
    files = sorted(p for p in target.parent.iterdir() if LICENSE_FILE.match(p.name) and p.is_file())
    return identify(files[0].read_text(errors="replace")) if files else ""


def display_name(launcher: Launcher, command: str) -> str:
    """Name= of the launcher, or the target's file name for Discord's "Game <id>" stubs."""
    return Path(command).name if GENERIC_NAME.fullmatch(launcher.name) else launcher.name


def quote(path: Path) -> str:
    """Single-quote a path for a copy-pasteable shell command."""
    return "'" + str(path).replace("'", "'\\''") + "'"


def target_item(name: str, launcher: Launcher, target: Path) -> Item:
    """Item for an existing, uncovered target; a license file beside it decides, else unknown."""
    how = f"{launcher.path.name} -> {target}"
    lic = license_for_path(target)[0] or sibling_license(target)
    if not lic:
        return unknown(name, "desktop", reason=f"{how}; {NO_LICENSE}")
    verdict, reason = classify_text(lic)
    return Item(
        name=name,
        source="desktop",
        verdict=verdict,
        license=lic,
        reason=f"{how}; {reason}" if reason else how,
    )


def dangling_item(name: str, launcher: Launcher, command: str) -> Item:
    """Item for a launcher whose target is gone; removing the .desktop file fixes it."""
    return unknown(
        name,
        "desktop",
        note=f"launcher without target: {command}",
        dangling=True,
        removeCommand=f"rm {quote(launcher.path)}",
    )


def scan_desktop() -> list[Item]:
    """Items for launchers whose target nothing else scans, plus dead launchers."""
    dead: list[tuple[str, Launcher, str]] = []
    survivors: list[tuple[str, Launcher, Path]] = []
    used: set[str] = set()
    for launcher in launchers():
        command = exec_command(launcher.exec_line)
        if command is None or other_source(launcher.exec_line, command):
            continue
        target = locate(command)
        if target is not None and (covered_elsewhere(target) or is_kuhys(target)):
            continue
        name = display_name(launcher, command)
        if name in used:
            name = f"{name} ({launcher.path.stem})"
        used.add(name)
        if target is None:
            dead.append((name, launcher, command))
        else:
            survivors.append((name, launcher, target))
    # One pacman call for all of it: a package's own launcher for an optional,
    # uninstalled program is the package's business (rm would only be undone).
    owned = owned_by_pacman([str(t) for _, _, t in survivors] + [str(ln.path) for _, ln, _ in dead])
    items = [dangling_item(*d) for d in dead if str(d[1].path) not in owned]
    return items + [target_item(*s) for s in survivors if str(s[2]) not in owned]
