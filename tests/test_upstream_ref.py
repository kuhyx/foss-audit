"""upstream_license at a given git ref (tag or commit), falling back to HEAD (local file:// repos only)."""

# ruff: noqa: F811  (pytest fixtures are imported, then named as parameters)
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from foss_audit import upstream_git
from foss_audit import upstream_license as ul
from tests.upstream_helpers import APACHE, MIT, cache_file, git, make_repo  # noqa: F401


def tagged_repo(tmp_path: Path) -> tuple[str, str]:
    """MIT at tag v1, then Apache on the default branch; returns (url, v1's commit sha)."""
    url = make_repo(tmp_path, {"LICENSE": MIT})
    repo = tmp_path / "repo"
    git(repo, "tag", "v1")
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    (repo / "LICENSE").write_text(APACHE)
    git(repo, "commit", "--quiet", "-am", "relicense")
    return url, sha


def test_tag_is_read_not_the_default_branch(tmp_path: Path, cache_file: Path) -> None:
    url, _ = tagged_repo(tmp_path)
    assert ul.upstream_license(url, "v1") == ("MIT", f"upstream {url} v1: LICENSE file")
    assert ul.upstream_license(url) == ("Apache-2.0", f"upstream {url} HEAD: LICENSE file")
    assert sorted(json.loads(cache_file.read_text())) == [url, f"{url}@v1"]


def test_commit_sha_is_read(tmp_path: Path) -> None:
    url, sha = tagged_repo(tmp_path)
    assert ul.upstream_license(url, sha) == ("MIT", f"upstream {url} {sha}: LICENSE file")


def test_ref_hit_is_cached_under_its_own_key(tmp_path: Path, cache_file: Path) -> None:
    url, _ = tagged_repo(tmp_path)
    ul.upstream_license(url, "v1")
    git(tmp_path / "repo", "tag", "-d", "v1")
    assert ul.upstream_license(url, "v1") == ("MIT", f"upstream {url} v1: LICENSE file")


def test_missing_ref_falls_back_to_head_labelled(tmp_path: Path, cache_file: Path) -> None:
    url, _ = tagged_repo(tmp_path)
    assert ul.upstream_license(url, "v9") == (
        "Apache-2.0",
        f"upstream {url} HEAD: LICENSE file (default branch, not v9)",
    )
    assert sorted(json.loads(cache_file.read_text())) == [url, f"{url}@v9"]  # the fallback answer is cached


def test_fallback_answer_is_cached_under_the_ref_key(
    tmp_path: Path, cache_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url, _ = tagged_repo(tmp_path)
    first = ul.upstream_license(url, "v9")
    calls: list[tuple[str, str]] = []

    def no_git(key: str, ref: str = "") -> upstream_git.RootFiles:
        calls.append((key, ref))
        raise AssertionError("git was called")

    monkeypatch.setattr(ul, "read_root_files", no_git)
    assert ul.upstream_license(url, "v9") == first
    assert calls == []
    assert json.loads(cache_file.read_text())[f"{url}@v9"]["checked"] == first[1]


def test_total_failure_stays_uncached_and_is_retried(
    tmp_path: Path, cache_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def down(key: str, ref: str = "") -> upstream_git.RootFiles:
        calls.append(ref)
        raise upstream_git.UpstreamError("network down")

    monkeypatch.setattr(ul, "read_root_files", down)
    url = f"file://{tmp_path}/nope"
    assert ul.upstream_license(url, "v9")[0] == ""
    assert ul.upstream_license(url, "v9")[0] == ""
    assert calls == ["v9", "", "v9", ""]
    assert not cache_file.exists()


@pytest.mark.parametrize("ref", ["--upload-pack=touch pwned", "a:b", "+v1", "v1^", "a b", "x..y", "v1~1"])
def test_unsafe_ref_is_never_passed_to_git(tmp_path: Path, ref: str) -> None:
    url, _ = tagged_repo(tmp_path)
    found, checked = ul.upstream_license(url, ref)
    assert (found, checked) == (
        "Apache-2.0",
        f"upstream {url} HEAD: LICENSE file (default branch, not {ref})",
    )
    assert not (tmp_path / "pwned").exists()


def test_read_root_files_rejects_unsafe_ref() -> None:
    with pytest.raises(upstream_git.UpstreamError, match="not a usable git ref"):
        upstream_git.read_root_files("file:///nowhere", "-x")


def test_only_the_root_files_that_matter_are_fetched(tmp_path: Path) -> None:
    # A partial fetch fetches each blob it reads on demand, one round trip each: a big
    # repository root made reading its LICENSE take 5-20 s. Prove no other blob is
    # asked for by deleting one from the remote: reading it would fail the lookup.
    url = make_repo(tmp_path, {"LICENSE": MIT, "README.md": "# hi\n", "build.gradle": "x\n"})
    repo = tmp_path / "repo"
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD:build.gradle"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    (repo / ".git/objects" / sha[:2] / sha[2:]).unlink()
    files = upstream_git.read_root_files(url)
    assert (files.licenses, files.readme_name, files.readme) == ({"LICENSE": MIT}, "README.md", "# hi\n")
