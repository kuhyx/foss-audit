"""A directory of unrelated git clones (~/.local/share/mcp-servers) is one item per clone."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import make_repo
from userapp_helpers import MIT, by_name, write

from foss_audit import scan_android, scan_userapp, scan_userapp_group


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(scan_userapp, "HOME", tmp_path)
    monkeypatch.setattr(scan_android, "HOME", tmp_path)
    monkeypatch.setattr(scan_userapp_group, "upstream_license", lambda url: ("", f"offline {url}"))
    (tmp_path / ".local/share").mkdir(parents=True)
    return tmp_path


def clone(path: Path, remote: str, license_text: str | None = MIT) -> Path:
    return make_repo(path, remote=remote, license_text=license_text)


def test_each_clone_is_its_own_item(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    servers = home / ".local/share/mcp-servers"
    clone(servers / "alpha", "https://github.com/a/alpha.git")
    write(servers / "alpha/bin/alpha")  # an ELF inside must not merge it into one item
    clone(servers / "beta", "https://github.com/b/beta.git", license_text=None)
    clone(servers / "gamma", "https://github.com/c/gamma.git", license_text=None)
    (servers / "plain").mkdir()  # not a clone: ignored
    seen: list[str] = []

    def fake(url: str) -> tuple[str, str]:
        seen.append(url)
        return ("Apache-2.0", f"upstream {url}") if "beta" in url else ("", "upstream: no license file")

    monkeypatch.setattr(scan_userapp_group, "upstream_license", fake)
    items = by_name(scan_userapp.scan_apps())
    assert sorted(items) == ["mcp-servers/alpha", "mcp-servers/beta", "mcp-servers/gamma"]
    alpha, beta, gamma = (items[f"mcp-servers/{n}"] for n in ("alpha", "beta", "gamma"))
    assert (alpha.id, alpha.verdict, alpha.license) == ("user-app:mcp-servers/alpha", "foss", "MIT")
    assert (
        alpha.removeCommand == f"rm -rf '{servers / 'alpha'}'"
        or alpha.removeCommand == f"rm -rf {servers / 'alpha'}"
    )
    assert (beta.verdict, beta.license) == ("foss", "Apache-2.0")
    assert "upstream https://github.com/b/beta" in beta.reason
    assert (gamma.verdict, gamma.license) == ("nonfree", "")
    assert "no license file shipped" in gamma.reason
    assert seen == ["https://github.com/b/beta", "https://github.com/c/gamma"]


def test_own_clones_and_single_clone_dirs_are_left_alone(home: Path) -> None:
    servers = home / ".local/share/mixed"
    clone(servers / "mine", "https://github.com/kuhyx/mine.git")
    clone(servers / "theirs", "https://github.com/t/theirs.git")
    assert [i.name for i in scan_userapp.scan_apps()] == ["mixed/theirs"]
    only = home / ".local/share/solo"
    clone(only / "one", "https://github.com/o/one.git")
    write(only / "one/prog")
    assert [i.name for i in scan_userapp.scan_apps()] == ["mixed/theirs", "solo"]


def test_clone_without_remote_or_manifest_is_unknown(home: Path) -> None:
    servers = home / ".local/share/g"
    clone(servers / "a", "https://github.com/x/a.git", license_text=None)
    make_repo(servers / "b", remote=None, license_text=None)
    (servers / "b/package.json").write_text('{"name": "b", "license": "ISC"}')
    items = by_name(scan_userapp.scan_apps())
    assert items["g/b"].license == "ISC"
    assert items["g/a"].verdict == "nonfree"
