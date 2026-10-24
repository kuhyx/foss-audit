"""Every ~/.local/bin item gets a remove command matched to what installed it."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import make_repo

from foss_audit import scan_misc
from foss_audit.remove_cmd import module_name, shell_path

ELF = b"\x7fELF" + b"\0" * 12
CLAUDE_TERMS = b"// a Beta product per Anthropic's Commercial Terms of Service."


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(scan_misc, "HOME", tmp_path)
    monkeypatch.setattr(scan_misc, "TOOL_ROOTS", (tmp_path / ".local/share/pipx",))
    return tmp_path


def write(path: Path, data: bytes | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data)
    return path


def pnpm_shim(path: Path, rel: str) -> None:
    write(path, f'#!/bin/sh\nbasedir=x\n  exec node  "$basedir/{rel}" "$@"\n')


def test_shell_path_keeps_tilde_outside_the_quotes(tmp_path: Path) -> None:
    assert shell_path(tmp_path / ".local/bin/my tool", tmp_path) == "~/'.local/bin/my tool'"
    assert shell_path(tmp_path / ".local/bin/x", tmp_path) == "~/.local/bin/x"
    assert shell_path(Path("/opt/YouTube Music"), tmp_path) == "'/opt/YouTube Music'"
    assert module_name(Path("/n/node_modules/@scope/pkg")) == "@scope/pkg"
    assert module_name(Path("/n/node_modules/pkg")) == "pkg"


def test_every_local_bin_entry_has_its_owners_remove_command(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = home / ".local/bin"
    # pip --user entry point: the distribution's uninstall, not the script's name.
    meta = write(home / "site/bandit-1.0.dist-info/METADATA", "Name: bandit\nLicense-Expression: MIT\n")
    write(bin_dir / "bandit-baseline", "#!/usr/bin/python\n")
    monkeypatch.setattr(scan_misc, "script_owners", lambda: {str(bin_dir / "bandit-baseline"): meta})
    # Loose files and a directory: rm the exact path, quoted.
    write(bin_dir / "butler", ELF)
    write(bin_dir / "my script", "#!/bin/sh\n")
    (bin_dir / "adir").mkdir()
    # Symlink into kuhy's checkout: only the link goes.
    wrapper = write(make_repo(home / "src/x") / "run.sh", "#!/bin/sh\n")
    (bin_dir / "x").symlink_to(wrapper)
    # claude native install: the link plus the versions dir it downloads into.
    native = write(home / ".local/share/claude/versions/2.1.0", ELF + CLAUDE_TERMS)
    (bin_dir / "claude").symlink_to(native)
    # A cited-terms binary that is not a versioned install: only the link.
    other = write(home / "vendor/tool/tool", ELF + CLAUDE_TERMS)
    (bin_dir / "tool").symlink_to(other)
    # Symlink into another node's global node_modules: that npm's uninstall plus the link.
    pkg = home / ".nvm/versions/node/v22.18.0/lib/node_modules/@iyadhk/clauditor"
    write(pkg / "package.json", '{"name": "@iyadhk/clauditor", "license": "MIT"}')
    (bin_dir / "clauditor").symlink_to(write(pkg / "dist/cli.js", ""))
    # Symlink into a project-local node_modules: not a global install, only the link.
    local = write(home / "proj/node_modules/lint/package.json", '{"name": "lint", "license": "MIT"}')
    (bin_dir / "lint").symlink_to(write(local.parent / "cli.js", ""))
    # pnpm shim: pnpm's global remove of the package it execs.
    store = home / ".local/share/pnpm/global/v11/abc/node_modules"
    write(store / "@scope/tool/package.json", '{"name": "@scope/tool", "license": "MIT"}')
    write(store / "@scope/tool/dist/index.js", "")
    pnpm_shim(bin_dir / "scoped", "../share/pnpm/global/v11/abc/node_modules/@scope/tool/dist/index.js")
    items = scan_misc.scan_local_bin()
    assert [i.name for i in items if i.removeCommand is None] == []
    by = {i.name: (i.removeCommand, i.removeVia) for i in items}
    assert by["bandit-baseline"] == ("pip uninstall --user bandit", "entry point of pip-user package bandit")
    assert by["butler"] == ("rm ~/.local/bin/butler", "")
    assert by["my script"] == ("rm ~/'.local/bin/my script'", "")
    assert by["adir"] == ("rm -r ~/.local/bin/adir", "")
    assert by["x"] == ("rm ~/.local/bin/x", "symlink only; ~/src/x/run.sh stays")
    assert by["claude"] == (
        "rm ~/.local/bin/claude && rm -rf ~/.local/share/claude/versions",
        "native install: the link and every downloaded version",
    )
    assert by["tool"] == ("rm ~/.local/bin/tool", "symlink only; ~/vendor/tool/tool stays")
    assert by["clauditor"] == (
        "npm uninstall -g --prefix ~/.nvm/versions/node/v22.18.0 @iyadhk/clauditor"
        " && rm ~/.local/bin/clauditor",
        "npm global package @iyadhk/clauditor",
    )
    assert by["lint"] == ("rm ~/.local/bin/lint", "symlink only; ~/proj/node_modules/lint/cli.js stays")
    assert by["scoped"] == ("pnpm remove -g @scope/tool", "pnpm global package @scope/tool")


def test_npm_link_removes_by_scoped_name(home: Path) -> None:
    root = home / "node_modules"
    linked = make_repo(home / "src/tool")
    write(linked / "package.json", "{}")
    (root / "@me").mkdir(parents=True)
    (root / "@me/tool").symlink_to(linked)
    [item] = scan_misc.npm_items(scan_misc.npm_manifests(root))
    assert (item.reason, item.removeCommand) == ("npm link", "npm uninstall -g @me/tool")
