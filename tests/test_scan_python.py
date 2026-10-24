"""pip --user, pipx, uv tools and conda scanners against a fake $HOME."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import make_repo

from foss_audit import scan_python


def dist(site: Path, name: str, headers: str, direct_url: dict[str, str] | None = None) -> None:
    info = site / f"{name.replace('-', '_')}-1.0.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(f"Name: {name}\nVersion: 1.0\n{headers}\n")
    if direct_url is not None:
        (info / "direct_url.json").write_text(json.dumps(direct_url))


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(scan_python, "HOME", tmp_path)
    monkeypatch.setattr(scan_python, "PIPX_VENVS", tmp_path / "pipx")
    monkeypatch.setattr(scan_python, "UV_TOOLS", tmp_path / "uv")
    monkeypatch.setattr(scan_python, "CONDA_ROOTS", (tmp_path / "conda", tmp_path / "missing"))
    return tmp_path


def test_pip_user_license_sources_and_own(home: Path) -> None:
    site = home / ".local/lib/python3.14/site-packages"
    dist(site, "expr", "License-Expression: MIT\nHome-page: https://e.x")
    dist(
        site, "trove", "Classifier: License :: OSI Approved :: BSD License\nProject-URL: Source, https://t.x"
    )
    dist(site, "freetext", "License: Proprietary\n second line")
    dist(site, "bare", "")
    dist(site, "mine", "", {"url": "https://github.com/kuhyx/utils"})
    local = make_repo(home / "src/x")
    dist(site, "local", "", {"url": f"file://{local}"})
    dist(site, "vendored", "Home-page: https://github.com/someone/v", {"url": f"file://{local}"})
    utils = make_repo(home / "src/utils", remote="git@github.com:kuhyx/utils.git")
    (utils / "sub").mkdir()
    dist(site, "sub", "", {"url": "https://github.com/kuhyx/utils", "subdirectory": "sub"})
    dist(site, "remote", "License: MIT", {"url": "https://github.com/other/x"})
    by = {i.name: i for i in scan_python.scan_pip_user()}
    assert (by["expr"].verdict, by["expr"].url) == ("foss", "https://e.x")
    assert (by["trove"].license, by["trove"].url) == ("BSD License", "https://t.x")
    assert by["freetext"].verdict == "nonfree"
    assert (by["bare"].verdict, by["bare"].own) == ("nonfree", False)
    assert by["mine"].own and by["local"].own and by["sub"].own
    assert (by["local"].verdict, by["local"].license) == ("foss", "MIT")
    assert (by["sub"].verdict, by["sub"].license) == ("foss", "MIT")
    assert not by["vendored"].own
    assert by["remote"].verdict == "foss"
    assert by["expr"].removeCommand == "pip uninstall --break-system-packages expr"


def test_tool_venvs_pick_the_matching_distribution(home: Path) -> None:
    pipx_site = home / "pipx/pre-commit/lib/python3.14/site-packages"
    dist(pipx_site, "cfgv", "License: MIT")
    dist(pipx_site, "pre-commit", "License: MIT")
    (home / "pipx/broken").mkdir()  # venv without metadata is skipped
    dist(home / "pipx/renamed/lib/python3.14/site-packages", "other", "")  # no dist matches the venv
    (home / "pipx/stray-file").write_text("")
    dist(home / "uv/ruff/lib/python3.14/site-packages", "ruff", "License-Expression: MIT")
    pipx = scan_python.scan_pipx()
    assert [(i.name, i.source) for i in pipx] == [("pre-commit", "pipx")]
    assert scan_python.scan_uv_tools()[0].removeCommand == "uv tool uninstall ruff"


def test_conda_base_and_envs(home: Path) -> None:
    base = home / "conda/conda-meta"
    env = home / "conda/envs/copo/conda-meta"
    base.mkdir(parents=True)
    env.mkdir(parents=True)
    (base / "python.json").write_text(
        json.dumps({"name": "python", "version": "3.14", "license": "Python-2.0"})
    )
    (env / "meta.json").write_text(json.dumps({"license": None}))
    items = scan_python.scan_conda()
    assert [(i.name, i.verdict) for i in items] == [("python [base]", "foss"), ("meta [copo]", "nonfree")]


def test_script_owners_from_record(home: Path) -> None:
    site = home / ".local/lib/python3.14/site-packages"
    dist(site, "bandit", "License: Apache")
    record = site / "bandit-1.0.dist-info/RECORD"
    record.write_text("bandit/__init__.py,sha256=x,1\n../../../bin/bandit,sha256=y,2\n")
    owners = scan_python.script_owners()
    assert owners == {str(home / ".local/bin/bandit"): record.parent / "METADATA"}
