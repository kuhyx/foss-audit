"""npm, cargo, flatpak, AppImage, /opt and ~/.local/bin scanners."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from foss_audit import scan_misc

ELF = b"\x7fELF" + b"\0" * 12


def fake_run(stdout: str) -> Any:
    def run(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 0, stdout, "")

    return run


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(scan_misc, "HOME", tmp_path)
    monkeypatch.setattr(scan_misc, "TOOL_ROOTS", (tmp_path / ".local/share/pipx",))
    return tmp_path


def test_tools_missing_means_empty(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: None)
    assert scan_misc.scan_npm_global() == []
    assert scan_misc.scan_flatpak() == []
    assert scan_misc.scan_cargo() == []
    assert scan_misc.scan_local_bin() == []


def test_npm_global(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    root = home / "node_modules"
    for name, data in {
        "prettier": {"name": "prettier", "version": "3", "license": "MIT", "homepage": "https://p"},
        "odd": {"license": {"type": "BSD"}},
    }.items():
        (root / name).mkdir(parents=True)
        (root / name / "package.json").write_text(json.dumps(data))
    (root / "@scope/pkg").mkdir(parents=True)
    (root / "@scope/pkg/package.json").write_text(json.dumps({"name": "@scope/pkg", "license": "ISC"}))
    linked = home / "src/tool"
    linked.mkdir(parents=True)
    (linked / "package.json").write_text("{}")
    (root / "tool").symlink_to(linked)
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/npm")
    monkeypatch.setattr(subprocess, "run", fake_run(f"{root}\n"))
    by = {i.name: i for i in scan_misc.scan_npm_global()}
    assert by["prettier"].removeCommand == "npm uninstall -g prettier"
    assert by["odd"].verdict == "foss"
    assert by["@scope/pkg"].verdict == "foss"
    assert by["tool"].verdict == "own"


def test_cargo_and_flatpak(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    (home / ".cargo").mkdir()
    crates = {"installs": {"counts 1.0.6 (registry+https://x)": {}}}
    (home / ".cargo/.crates2.json").write_text(json.dumps(crates))
    assert [(i.name, i.version) for i in scan_misc.scan_cargo()] == [("counts", "1.0.6")]
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/flatpak")
    monkeypatch.setattr(subprocess, "run", fake_run("net.app.One\t1.2\nnet.app.Two\t\n"))
    apps = scan_misc.scan_flatpak()
    assert [(a.name, a.version) for a in apps] == [("net.app.One", "1.2"), ("net.app.Two", None)]


def test_appimages_bounded_depth(home: Path) -> None:
    (home / "a/b").mkdir(parents=True)
    (home / "a/b/Joplin.AppImage").write_text("")
    (home / "Top.appimage").write_text("")
    (home / "a/b/c/d").mkdir(parents=True)
    (home / "a/b/c/d/Deep.AppImage").write_text("")  # deeper than 3 levels
    assert sorted(i.name for i in scan_misc.scan_appimages()) == ["Joplin", "Top"]


def test_opt_skips_pacman_owned(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for d in ("cuda", "miniconda3"):
        (tmp_path / d).mkdir()
    (tmp_path / "file").write_text("")
    monkeypatch.setattr(scan_misc, "OPT_ROOT", tmp_path)
    monkeypatch.setattr(scan_misc, "owned_by_pacman", lambda dirs: {d for d in dirs if d.endswith("cuda")})
    assert [i.name for i in scan_misc.scan_opt()] == ["miniconda3"]


def test_local_bin(home: Path) -> None:
    bin_dir = home / ".local/bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "myscript").write_text("#!/bin/sh\n")
    (bin_dir / "butler").write_bytes(ELF)
    tool = home / ".local/share/pipx/venvs/ruff/bin/ruff"
    tool.parent.mkdir(parents=True)
    tool.write_bytes(ELF)
    (bin_dir / "ruff").symlink_to(tool)
    wrapper = home / "src/x/run.sh"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text("#!/bin/sh\n")
    (bin_dir / "x").symlink_to(wrapper)
    os.symlink(home / "gone", bin_dir / "dangling")
    by = {i.name: i for i in scan_misc.scan_local_bin()}
    assert set(by) == {"myscript", "butler", "x"}
    assert by["myscript"].verdict == "own"
    assert by["x"].reason.startswith("script ->")
    assert (by["butler"].verdict, by["butler"].reason) == ("unknown", "binary in ~/.local/bin")
