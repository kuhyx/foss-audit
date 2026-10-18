"""upstream_license: failures stay visible and uncached, cache TTL, the scanners' with_upstream fallback."""

# ruff: noqa: F811  (pytest fixtures are imported, then named as parameters)
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from foss_audit import upstream_license as ul
from tests.upstream_helpers import APACHE, MIT, cache_file, git, make_repo  # noqa: F401

# --- failures are visible and never cached ------------------------------------------------


def test_missing_repo_is_a_visible_uncached_failure(tmp_path: Path, cache_file: Path) -> None:
    url = f"file://{tmp_path}/nope"
    found, checked = ul.upstream_license(url)
    assert found == ""
    assert checked.startswith(f"upstream {url}: fetch failed: ")
    assert not cache_file.exists()


def test_unusable_url(cache_file: Path) -> None:
    assert ul.upstream_license("ext::sh -c evil") == (
        "",
        "upstream 'ext::sh -c evil': not a fetchable git URL",
    )
    assert not cache_file.exists()


def test_timeout_and_missing_git_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*_a: object, **_k: object) -> None:
        raise subprocess.TimeoutExpired("git", 20)

    def no_git(*_a: object, **_k: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", timeout)
    assert ul.upstream_license("https://example.org/o/r") == (
        "",
        "upstream https://example.org/o/r: fetch failed: timed out after 20 s",
    )
    monkeypatch.setattr(subprocess, "run", no_git)
    assert "fetch failed: cannot run git" in ul.upstream_license("https://example.org/o/r")[1]


def test_git_failure_without_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    done = subprocess.CompletedProcess([], 3, b"", b"")
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: done)
    assert ul.upstream_license("https://example.org/o/r")[1].endswith("fetch failed: git init exited 3")


def test_git_is_called_without_shell_prompts_or_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[subprocess.CompletedProcess[bytes]] = []
    real = subprocess.run

    def spy(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        env = kwargs["env"]
        assert isinstance(env, dict)
        assert (kwargs["timeout"], kwargs.get("shell"), env["GIT_TERMINAL_PROMPT"]) == (20, None, "0")
        assert "credential.helper=" in cmd
        done = real(cmd, **kwargs)  # type: ignore[call-overload]
        seen.append(done)
        return done  # type: ignore[no-any-return]

    monkeypatch.setattr(subprocess, "run", spy)
    ul.upstream_license("file:///nonexistent/repo")
    assert seen


# --- cache ---------------------------------------------------------------------------------


def test_cache_hit_skips_git_and_expiry_refetches(
    tmp_path: Path, cache_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = make_repo(tmp_path, {"LICENSE": MIT})
    assert ul.upstream_license(url)[0] == "MIT"
    (tmp_path / "repo/LICENSE").write_text(APACHE)
    git(tmp_path / "repo", "commit", "--quiet", "-am", "relicense")
    clock = {"now": 1_000_000.0 + ul.TTL_S - 1}
    monkeypatch.setattr(ul, "_now", lambda: clock["now"])
    assert ul.upstream_license(url + ".git")[0] == "MIT"  # fresh: served from the cache, git not asked
    clock["now"] = 1_000_000.0 + ul.TTL_S
    assert ul.upstream_license(url)[0] == "Apache-2.0"
    assert json.loads(cache_file.read_text())[url]["fetched_at"] == clock["now"]


def test_bad_cache_entries_are_ignored(tmp_path: Path, cache_file: Path) -> None:
    url = make_repo(tmp_path, {"LICENSE": MIT})
    cache_file.parent.mkdir(parents=True)
    for junk in (
        "not json",
        "[1]",
        json.dumps({url: "x"}),
        json.dumps({url: {"license": "GPL"}}),
        json.dumps({url: {"license": "GPL", "checked": "c", "fetched_at": 2_000_000.0}}),
    ):
        cache_file.write_text(junk)
        assert ul.upstream_license(url)[0] == "MIT"


def test_unwritable_cache_dir_does_not_hide_the_answer(
    tmp_path: Path, cache_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = make_repo(tmp_path, {"LICENSE": MIT})
    (tmp_path / "cache").write_text("a file where the directory should be")
    assert ul.upstream_license(url)[0] == "MIT"
    assert not cache_file.exists()


# --- with_upstream (the fallback the scanners call) -----------------------------------------


def test_with_upstream_keeps_licensed_and_urlless(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ul, "upstream_license", lambda url: pytest.fail("must not be asked"))
    assert ul.with_upstream("MIT", "LICENSE file", "https://x/y") == ("MIT", "LICENSE file")
    assert ul.with_upstream("", "own check", "") == ("", "own check")


def test_with_upstream_adopts_license_or_appends_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = {
        "https://x/lic": ("MIT", "upstream https://x/lic HEAD: LICENSE file"),
        "https://x/none": ("", "upstream https://x/none HEAD: no license file"),
    }
    monkeypatch.setattr(ul, "upstream_license", answers.__getitem__)
    assert ul.with_upstream("", "own check", "https://x/lic") == (
        "MIT",
        "upstream https://x/lic HEAD: LICENSE file",
    )
    assert ul.with_upstream("", "own check", "https://x/none") == (
        "",
        "own check; upstream https://x/none HEAD: no license file",
    )


def test_real_clock_is_epoch_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()
    assert ul._now() > 1_700_000_000
