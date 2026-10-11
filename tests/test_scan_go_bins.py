"""`go install`ed tools in a GOPATH bin: one toolchain item per module."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from conftest import MIT

from foss_audit import scan_toolchain_tools
from foss_audit.scan_toolchain_tools import go_module_dir, scan_go_bins

VERSION_M = """\
{bin}/age: go1.27.2
\tpath\tfilippo.io/age/cmd/age
\tmod\tfilippo.io/age\tv1.3.2\th1:x=
\tdep\tfilippo.io/edwards25519\tv1.2.0\th1:y=
{bin}/age-keygen: go1.27.2
\tmod\tfilippo.io/age\tv1.3.2\th1:x=
{bin}/Tool: go1.27.2
\tmod\tgithub.com/BurntSushi/Tool\tv0.1.0\th1:z=
{bin}/devel: go1.27.2
\tpath\texample.com/devel
"""


def fake_go(out: str, calls: list[list[str]]) -> Any:
    def run(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, out, "")

    return run


def test_no_go_or_no_bin_dir_means_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "go/bin").mkdir(parents=True)
    monkeypatch.setattr(shutil, "which", lambda _: None)
    assert scan_go_bins(tmp_path) == []
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/go")
    (tmp_path / "go/bin").rmdir()
    assert scan_go_bins(tmp_path) == []


def test_sdk_bin_is_not_a_gopath(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "sdk/go/bin").mkdir(parents=True)
    (tmp_path / "sdk/go/bin/go").write_text("")
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/go")
    assert scan_go_bins(tmp_path) == []


def test_one_item_per_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gopath = tmp_path / "sdk/go"
    bindir = gopath / "bin"
    bindir.mkdir(parents=True)
    licensed = go_module_dir(gopath, "filippo.io/age", "v1.3.2")
    licensed.mkdir(parents=True)
    (licensed / "LICENSE").write_text(MIT)
    calls: list[list[str]] = []
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/go")
    monkeypatch.setattr(subprocess, "run", fake_go(VERSION_M.format(bin=bindir), calls))
    items = {i.name: i for i in scan_go_bins(tmp_path)}
    assert calls == [["/usr/bin/go", "version", "-m", str(bindir)]]
    age = items["filippo.io/age"]
    assert (age.version, age.verdict, age.license) == ("v1.3.2", "foss", "MIT")
    assert age.removeCommand == f"rm {bindir / 'age'} {bindir / 'age-keygen'}"
    assert age.reason.startswith("~/sdk/go/bin")
    tool = items["github.com/BurntSushi/Tool"]
    assert tool.verdict == "nonfree"
    assert set(items) == {"filippo.io/age", "github.com/BurntSushi/Tool"}


def test_module_dir_escapes_upper_case(tmp_path: Path) -> None:
    got = go_module_dir(tmp_path, "github.com/BurntSushi/toml", "v1.0.0")
    assert got == tmp_path / "pkg/mod/github.com/!burnt!sushi/toml@v1.0.0"


def test_gopaths_cover_sdk_and_default() -> None:
    assert scan_toolchain_tools.GOPATHS == ("sdk/go", "go")
