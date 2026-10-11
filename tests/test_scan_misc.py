"""npm, cargo, flatpak, AppImage, /opt and ~/.local/bin scanners."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from conftest import make_repo

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
    linked = make_repo(home / "src/tool")
    (linked / "package.json").write_text("{}")
    (root / "bare").mkdir()
    (root / "bare/package.json").write_text(json.dumps({"name": "bare"}))
    (root / "bare/LICENSE").write_text("Apache License\nVersion 2.0\n")
    (root / "tool").symlink_to(linked)
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/npm")
    monkeypatch.setattr(subprocess, "run", fake_run(f"{root}\n"))
    by = {i.name: i for i in scan_misc.scan_npm_global()}
    assert by["prettier"].removeCommand == "npm uninstall -g prettier"
    assert by["odd"].verdict == "foss"
    assert by["@scope/pkg"].verdict == "foss"
    assert (by["tool"].verdict, by["tool"].own, by["tool"].reason) == ("foss", True, "npm link")
    assert (by["bare"].verdict, by["bare"].license) == ("foss", "Apache-2.0")


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


def test_local_bin(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    make_repo(home / "src/x")
    os.symlink(home / "gone", bin_dir / "dangling")
    site = home / "site"
    (site / "bandit-1.0.dist-info").mkdir(parents=True)
    (site / "bandit-1.0.dist-info/METADATA").write_text("Name: bandit\nLicense-Expression: Apache-2.0\n")
    (site / "nolic-1.0.dist-info").mkdir(parents=True)
    (site / "nolic-1.0.dist-info/METADATA").write_text("Name: nolic\n")
    (bin_dir / "bandit").write_text("#!/usr/bin/python\n")
    (bin_dir / "nolic").write_text("#!/usr/bin/python\n")
    owners = {str(bin_dir / n): site / f"{n}-1.0.dist-info/METADATA" for n in ("bandit", "nolic")}
    monkeypatch.setattr(scan_misc, "script_owners", lambda: owners)
    repo = make_repo(home / "src/dots")
    (repo / "tools").mkdir()
    (repo / "tools/copied.sh").write_text("#!/bin/sh\necho hi\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "tools/copied.sh"], check=True)
    (bin_dir / "copied.sh").write_text("#!/bin/sh\necho hi\n")
    by = {i.name: i for i in scan_misc.scan_local_bin()}
    assert set(by) == {"myscript", "butler", "x", "bandit", "nolic", "copied.sh"}
    assert (by["myscript"].verdict, by["myscript"].own, by["myscript"].loose) == ("nonfree", True, True)
    assert (by["x"].verdict, by["x"].own, by["x"].loose) == ("foss", True, False)
    assert by["x"].reason.startswith("-> ")
    assert (by["butler"].own, by["butler"].loose) == (False, True)
    assert by["butler"].reason == "binary in ~/.local/bin; no license (all rights reserved)"
    assert (by["bandit"].verdict, by["bandit"].reason) == ("foss", "entry point of bandit")
    assert by["nolic"].reason == "entry point of nolic; no license (all rights reserved)"
    assert (by["copied.sh"].verdict, by["copied.sh"].own) == ("foss", True)
    assert by["copied.sh"].reason == f"copy of {repo / 'tools/copied.sh'}"


def test_local_bin_binary_traced_to_its_source(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scan_misc, "script_owners", dict)
    bin_dir = home / ".local/bin"
    bin_dir.mkdir(parents=True)
    # Stray files above the install must not license it.
    (home / ".local/share").mkdir(parents=True)
    (home / ".local/share/COPYING").write_text("GNU AFFERO GENERAL PUBLIC LICENSE\n")
    (home / ".local/package.json").write_text('{"dependencies": {}}')
    built = home / ".local/share/app/bundle/bin/my_app"
    built.parent.mkdir(parents=True)
    built.write_bytes(ELF)
    (bin_dir / "my-app").symlink_to(built)
    orphan = home / ".local/share/other/run"
    orphan.parent.mkdir(parents=True)
    orphan.write_text("#!/bin/sh\n")
    (bin_dir / "other").symlink_to(orphan)
    repo = make_repo(home / "src/app")
    (repo / "bin").mkdir()
    (repo / "bin/my_app.dart").write_text("void main() {}\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "bin/my_app.dart"], check=True)
    by = {i.name: i for i in scan_misc.scan_local_bin()}
    assert (by["my-app"].verdict, by["my-app"].own) == ("foss", True)
    assert by["my-app"].reason == f"-> {built}, built from {repo / 'bin/my_app.dart'}"
    assert (by["other"].verdict, by["other"].own, by["other"].loose) == ("nonfree", False, False)


def pnpm_shim(bin_dir: Path, rel: str) -> None:
    """Write a pnpm-style shim (win/abs/plain exec variants) pointing at `rel`."""
    exec_lines = "\n".join(
        f'  exec {cmd} "{base}/{rel}" "$@"'
        for cmd, base in (("node.exe", "$basedir_win"), ("node ", "$basedir_abs"), ("node ", "$basedir"))
    )
    (bin_dir / rel.rsplit("/", 1)[-1].replace(".js", "")).write_text(
        f'#!/bin/sh\nbasedir=x\nif [ -n "$exe" ]; then\n{exec_lines}\nfi\n'
    )


def test_local_bin_pnpm_shim(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scan_misc, "script_owners", dict)
    bin_dir = home / ".local/bin"
    bin_dir.mkdir(parents=True)
    pkgs = home / ".local/share/pnpm/global/v11/abc/node_modules"
    licensed = pkgs / "@scope/tool"
    (licensed / "dist/bin").mkdir(parents=True)
    (licensed / "package.json").write_text('{"name": "@scope/tool", "license": "MIT"}')
    (licensed / "dist/bin/index.js").write_text("")
    bare = pkgs / "plain"
    bare.mkdir()
    (bare / "package.json").write_text('{"name": "plain"}')
    (bare / "cli.js").write_text("")
    pnpm_shim(bin_dir, "../share/pnpm/global/v11/abc/node_modules/@scope/tool/dist/bin/index.js")
    pnpm_shim(bin_dir, "../share/pnpm/global/v11/abc/node_modules/plain/cli.js")
    (bin_dir / "notshim").write_text('#!/bin/sh\nexec node "$HOME/node_modules/x.js"\n')
    by = {i.name: i for i in scan_misc.scan_local_bin()}
    tool = by["index"]
    assert (tool.verdict, tool.license, tool.own, tool.loose) == ("foss", "MIT", False, False)
    assert tool.reason == f"pnpm shim -> {licensed}"
    cli = by["cli"]
    assert (cli.verdict, cli.own, cli.loose) == ("nonfree", False, False)
    assert cli.reason == f"pnpm shim -> {bare}; no license (all rights reserved)"
    assert (by["notshim"].own, by["notshim"].loose) == (True, True)
