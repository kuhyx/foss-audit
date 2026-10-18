"""ELF apps unpacked under ~/.local/share: one item per top directory."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from conftest import make_repo
from userapp_helpers import ELF, MIT, by_name, write

from foss_audit import scan, scan_android, scan_userapp


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(scan_userapp, "HOME", tmp_path)
    monkeypatch.setattr(scan_android, "HOME", tmp_path)
    (tmp_path / ".local/share").mkdir(parents=True)
    return tmp_path


def test_nothing_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scan_userapp, "HOME", tmp_path)
    monkeypatch.setattr(scan_android, "HOME", tmp_path)
    assert scan_userapp.scan_user_apps() == []
    (tmp_path / ".local/share").mkdir(parents=True)
    assert scan_userapp.scan_user_apps() == []


def test_one_item_per_top_dir(home: Path) -> None:
    share = home / ".local/share"
    write(share / "GitKrakenCLI/gk")
    write(share / "GitKrakenCLI/gk.cfg", "text", 0o644)
    write(share / "Tachidesk/bin/kcef/cef_server")
    write(share / "Tachidesk/bin/kcef/other")
    write(share / "Blender Launcher/blenderlauncher")
    items = by_name(scan_userapp.scan_apps())
    assert sorted(items) == ["Blender Launcher", "GitKrakenCLI", "Tachidesk"]
    gk = items["GitKrakenCLI"]
    assert (gk.source, gk.verdict, gk.license) == ("user-app", "nonfree", "")
    assert gk.reason == "~/.local/share/GitKrakenCLI/gk; no license file shipped"
    assert gk.removeCommand == f"rm -rf {share}/GitKrakenCLI"
    assert "Tachidesk/bin/kcef/cef_server" in items["Tachidesk"].reason
    assert items["Blender Launcher"].removeCommand == f"rm -rf '{share}/Blender Launcher'"


def test_what_is_not_a_program(home: Path) -> None:
    share = home / ".local/share"
    write(share / "Libs/libfoo.so")
    write(share / "Libs/libfoo.so.1.2")
    write(share / "Data/blob", ELF, 0o644)
    write(share / "Scripts/run.sh", "#!/bin/sh\n")
    write(share / "Deep/a/b/c/tool")
    write(share / "Pruned/node_modules/pkg/tool")
    write(share / "Pruned/.git/hooks/tool")
    write(share / "Locked/tool", ELF, 0o111)
    write(share / "real/tool")
    (share / "Linked").mkdir()
    (share / "Linked/tool").symlink_to(share / "real/tool")
    (share / "Alias").symlink_to(share / "real")
    write(share / "loose-file", ELF)
    assert [i.name for i in scan_userapp.scan_apps()] == ["real"]


def test_depth_bound_is_three_levels(home: Path) -> None:
    share = home / ".local/share"
    write(share / "Three/a/b/tool")
    write(share / "Four/a/b/c/tool")
    assert [i.name for i in scan_userapp.scan_apps()] == ["Three"]


def test_license_file_decides(home: Path) -> None:
    share = home / ".local/share"
    write(share / "Free/tool")
    write(share / "Free/LICENSE", MIT)
    write(share / "Proprietary/tool")
    write(share / "Proprietary/license.txt", "Proprietary EULA. All rights reserved.\n")
    write(share / "Notes/tool")
    write(share / "Notes/LICENSES.chromium.html", "<html>Permission is hereby granted, free of charge</html>")
    items = by_name(scan_userapp.scan_apps())
    assert (items["Free"].verdict, items["Free"].license) == ("foss", "MIT")
    assert "LICENSE: MIT" in items["Free"].reason
    assert items["Proprietary"].verdict == "nonfree"
    assert items["Proprietary"].reason.endswith("All rights reserved.")
    assert items["Proprietary"].reason.count("Proprietary EULA") == 1
    # Only LICENSE/COPYING-style names count, not bundled-notices html.
    assert items["Notes"].license == ""


def test_skips_other_scanners_and_specials(home: Path) -> None:
    share = home / ".local/share"
    for name in ("Steam", "flatpak", "pipx", "uv", "lutris", "gh", "godot", "PrismLauncher", "mangatl"):
        write(share / name / "tool")
    assert scan_userapp.scan_apps() == []


def test_skips_local_bin_targets(home: Path) -> None:
    share = home / ".local/share"
    write(share / "claude/versions/2.1.0")
    write(share / "other/tool")
    (home / ".local/bin").mkdir(parents=True)
    (home / ".local/bin/claude").symlink_to(share / "claude/versions/2.1.0")
    write(home / ".local/bin/plain", "#!/bin/sh\n")
    assert [i.name for i in scan_userapp.scan_apps()] == ["other"]


def test_skips_kuhys_own_code(home: Path) -> None:
    share = home / ".local/share"
    make_repo(share / "OwnCheckout")
    write(share / "OwnCheckout/tool")
    make_repo(share / "Vendored", remote="https://github.com/someone/else.git")
    write(share / "Vendored/tool")
    # A binary built from a file kuhy's repo tracks.
    repo = home / "src/mytools"
    write(repo / "mytool.c", "int main(void){return 0;}\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "mytool.c"], check=True)
    (repo / ".git/config").write_text('[remote "origin"]\n\turl = https://github.com/kuhyx/mytools.git\n')
    write(share / "Built/mytool")
    assert [i.name for i in scan_userapp.scan_apps()] == ["Vendored"]


def test_registered_as_a_scanner() -> None:
    assert scan.SCANNERS["user-app"] is scan_userapp.scan_user_apps
