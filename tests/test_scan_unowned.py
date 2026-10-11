"""Unowned /usr/bin files, system npm packages and ~/.config self-updating apps."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from conftest import make_repo

from foss_audit import scan_unowned

ELF = b"\x7fELF" + b"\0" * 12


def write(path: Path, data: bytes | str, mode: int = 0o755) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data)
    path.chmod(mode)
    return path


def track(repo: Path, rel: str, text: str) -> None:
    write(repo / rel, text)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", rel], check=True)


def fake_owned(paths: list[str]) -> set[str]:
    """Stand-in for pacman: files named owned* belong to a package."""
    return {p for p in paths if Path(p).name.startswith("owned")}


@pytest.fixture
def roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    usr, local = tmp_path / "usr/bin", tmp_path / "usr/local/bin"
    usr.mkdir(parents=True)
    local.mkdir(parents=True)
    monkeypatch.setattr(scan_unowned, "BIN_ROOTS", (usr, local))
    monkeypatch.setattr(scan_unowned, "owned_by_pacman", fake_owned)
    return usr, local


def test_unowned_bins(tmp_path: Path, roots: tuple[Path, Path]) -> None:
    usr, local = roots
    write(usr / "owned-tool", ELF)
    write(usr / "BuildPatchTool", ELF)
    write(usr / "libThing.so", ELF)
    write(usr / "libThing.so.1", ELF)
    write(usr / "Tool.debug", ELF)
    write(usr / "klvanc_parse", b"")  # 0-byte stub
    write(usr / "readme", "text", mode=0o644)
    (usr / "Linux").mkdir()
    (usr / "alias").symlink_to(usr / "BuildPatchTool")
    write(usr / "discord.orig", "#!/bin/sh\nexec Discord\n")
    write(usr / "pacman.orig", ELF)  # backup of a binary that still exists
    write(usr / "pacman", ELF)
    write(local / "ffmpeg.broken-libvpx11.bak", ELF)  # ffmpeg lives on in /usr/bin
    write(usr / "ffmpeg", ELF)
    write(local / "night-lockdown.sh", "#!/bin/sh\n")
    write(local / "guard", "#!/bin/sh\n")
    write(local / "viewer", ELF)
    write(local / "claude-like", ELF + b"per Anthropic's Commercial Terms of Service")
    repo = make_repo(tmp_path / "src/dots")
    track(repo, "top-level.sh", "#!/bin/sh\n")  # no parent directory name to index by
    track(repo, "bin/guard.sh", "#!/bin/sh\n")
    track(repo, "C/viewer/main.c", "int main(void) { return 0; }\n")
    track(repo, "C/viewer/.clang-format", "x\n")
    by = {i.name: i for i in scan_unowned.scan_unowned_bins()}
    assert set(by) == {"BuildPatchTool", "discord", "pacman", "ffmpeg", "night-lockdown.sh", "guard"} | {
        "viewer",
        "claude-like",
    }
    ue = by["BuildPatchTool"]
    assert (ue.source, ue.verdict, ue.own, ue.loose) == ("unowned", "nonfree", False, True)
    assert ue.to_json()["reason"] == (
        f"no license (all rights reserved); {usr / 'BuildPatchTool'} (no package owns it)"
    )
    assert ue.removeCommand == f"sudo rm {usr / 'BuildPatchTool'}"
    discord = by["discord"]
    assert (discord.own, discord.note) == (
        False,
        f"{usr / 'discord.orig'}: backup left after discord was removed",
    )
    assert (by["night-lockdown.sh"].own, by["night-lockdown.sh"].verdict) == (True, "nonfree")
    assert (by["guard"].verdict, by["guard"].own, by["guard"].source) == ("foss", True, "unowned")
    assert by["guard"].reason == f"copy of {repo / 'bin/guard.sh'}"
    assert by["viewer"].reason == f"built from {repo / 'C/viewer/main.c'}"
    claude = by["claude-like"]
    assert (claude.source, claude.license) == ("unowned", "LicenseRef-Anthropic-Commercial-Terms")


def test_missing_root_is_skipped(tmp_path: Path) -> None:
    assert scan_unowned.candidates((tmp_path / "nope",)) == []


def test_system_npm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "node_modules"
    monkeypatch.setattr(scan_unowned, "SYSTEM_NPM", root)
    assert scan_unowned.scan_system_npm() == []
    for name in ("prettier", "owned-npm"):
        write(root / name / "package.json", json.dumps({"name": name, "license": "MIT"}), mode=0o644)
    monkeypatch.setattr(scan_unowned, "owned_by_pacman", fake_owned)
    (item,) = scan_unowned.scan_system_npm()
    assert (item.name, item.source, item.verdict) == ("prettier", "npm-global", "foss")
    assert item.reason == f"{root} (system npm)"
    assert item.removeCommand == "sudo npm uninstall -g prettier"


def test_app_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / ".config"
    monkeypatch.setattr(scan_unowned, "CONFIG", config)
    assert scan_unowned.scan_app_home() == []
    for rel in ("discord/app-1.0.9", "discord/app-1.0.161", "discord/1.0.161", "slack/app-4.1.beta"):
        (config / rel).mkdir(parents=True)
    (config / "discord/app-2.0.0").write_text("a file, not an install")
    (config / "plain/sub").mkdir(parents=True)
    (config / "settings.json").write_text("{}")
    locked = config / "Thunar"
    locked.mkdir()
    locked.chmod(0o000)
    try:
        items = scan_unowned.scan_app_home()
    finally:
        locked.chmod(0o755)
    by = {i.name: i for i in items}
    assert set(by) == {"discord", "slack"}
    assert (by["discord"].version, by["discord"].source) == ("1.0.161", "app-home")
    assert by["discord"].note == f"{config / 'discord'}/app-1.0.161: self-updating install"
    assert by["discord"].removeCommand == f"rm -rf {config / 'discord'}"
    assert by["slack"].version == "4.1.beta"
