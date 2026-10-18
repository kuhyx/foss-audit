"""upstream_license: a repository the forge says is gone is a cached answer (no license), not a failure."""

# ruff: noqa: F811  (pytest fixtures are imported, then named as parameters)
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from foss_audit import upstream_git
from foss_audit import upstream_license as ul
from tests.upstream_helpers import MIT, cache_file, make_repo  # noqa: F401

URL = "https://github.com/substack/node-buffers"
GITHUB = (
    b"remote: Repository not found.\n"
    b"fatal: Authentication failed for 'https://github.com/substack/node-buffers/'\n"
)
GITLAB = (
    b"remote: HTTP Basic: Access denied. If a password was provided ...\n"
    b"fatal: Authentication failed for 'https://gitlab.com/o/r.git/'\n"
)
GITEA = b"remote: Not found.\nfatal: repository 'https://codeberg.org/o/r/' not found\n"
HTTP_404 = b"fatal: unable to access 'https://git.example.org/o/r/': The requested URL returned error: 404\n"
HTTP_401 = b"fatal: unable to access 'https://git.example.org/o/r/': The requested URL returned error: 401\n"
DNS = b"fatal: unable to access 'https://nohost.invalid/o/r/': Could not resolve host: nohost.invalid\n"
REFUSED = b"fatal: unable to access 'https://git.example.org/o/r/': Failed to connect to git.example.org\n"
HTTP_403 = b"fatal: unable to access 'https://github.com/o/r/': The requested URL returned error: 403\n"
HTTP_500 = b"fatal: unable to access 'https://git.example.org/o/r/': The requested URL returned error: 500\n"
NO_REF = b"fatal: couldn't find remote ref v9.9\n"


def fetch_fails_with(monkeypatch: pytest.MonkeyPatch, stderr: bytes) -> list[list[str]]:
    """Real git for the local steps; every `fetch` fails with `stderr` as the forge would answer."""
    real = subprocess.run
    fetches: list[list[str]] = []

    def fake(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if "fetch" in cmd:
            fetches.append(cmd)
            return subprocess.CompletedProcess(cmd, 128, b"", stderr)
        return real(cmd, **kwargs)  # type: ignore[call-overload,no-any-return]

    monkeypatch.setattr(subprocess, "run", fake)
    return fetches


@pytest.mark.parametrize(
    ("stderr", "shown"),
    [
        (GITHUB, "remote: Repository not found."),
        (GITLAB, "fatal: Authentication failed for 'https://gitlab.com/o/r.git/'"),
        (GITEA, "fatal: repository 'https://codeberg.org/o/r/' not found"),
        (HTTP_404, HTTP_404.decode().strip()),
        (HTTP_401, HTTP_401.decode().strip()),
    ],
)
def test_gone_repository_is_a_cached_no_license_answer(
    monkeypatch: pytest.MonkeyPatch, cache_file: Path, stderr: bytes, shown: str
) -> None:
    fetches = fetch_fails_with(monkeypatch, stderr)
    expected = ("", f"upstream {URL}: repository gone ({shown})")
    assert ul.upstream_license(URL) == expected
    assert json.loads(cache_file.read_text())[URL] == {
        "license": "",
        "checked": expected[1],
        "fetched_at": 1_000_000.0,
    }
    assert ul.upstream_license(URL) == expected  # the cache answers; git is not asked again
    assert len(fetches) == 1


@pytest.mark.parametrize("stderr", [DNS, REFUSED, HTTP_403, HTTP_500, NO_REF, b""])
def test_other_failures_stay_uncached(
    monkeypatch: pytest.MonkeyPatch, cache_file: Path, stderr: bytes
) -> None:
    fetch_fails_with(monkeypatch, stderr)
    found, checked = ul.upstream_license(URL)
    assert (found, checked.startswith(f"upstream {URL}: fetch failed: ")) == ("", True)
    assert "repository gone" not in checked
    assert not cache_file.exists()


def test_gone_error_is_an_upstream_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fetch_fails_with(monkeypatch, GITEA)
    with pytest.raises(upstream_git.UpstreamGoneError) as caught:
        upstream_git.read_root_files(URL)
    assert isinstance(caught.value, upstream_git.UpstreamError)


def test_gone_with_a_ref_does_not_retry_the_default_branch(
    monkeypatch: pytest.MonkeyPatch, cache_file: Path
) -> None:
    fetches = fetch_fails_with(monkeypatch, GITHUB)
    expected = ("", f"upstream {URL}: repository gone (remote: Repository not found.)")
    assert ul.upstream_license(URL, "v0.1.1") == expected
    assert len(fetches) == 1
    assert sorted(json.loads(cache_file.read_text())) == [f"{URL}@v0.1.1"]


def test_with_upstream_lists_a_gone_repo_as_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    fetch_fails_with(monkeypatch, GITHUB)
    found, where = ul.with_upstream("", "no license (all rights reserved); checked LICENSE file", URL)
    assert found == ""
    assert where.endswith(f"; upstream {URL}: repository gone (remote: Repository not found.)")
    assert "fetch failed" not in where


def test_user_global_git_config_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cache_file: Path
) -> None:
    """~/.gitconfig may hold per-host credential helpers (`gh auth git-credential`) that
    `credential.helper=` does not clear; git must not read it at all. An insteadOf
    rewrite there would break this fetch if it were read."""
    url = make_repo(tmp_path, {"LICENSE": MIT})
    home = tmp_path / "home"
    home.mkdir()
    (home / ".gitconfig").write_text(f'[url "file:///nonexistent/"]\n\tinsteadOf = {url}\n')
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.delenv("GIT_CONFIG_GLOBAL", raising=False)
    assert ul.upstream_license(url)[0] == "MIT"
