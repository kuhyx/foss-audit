"""Local-git fixtures for the upstream_license tests: file:// repos, an isolated cache file."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from foss_audit import upstream_license as ul

MIT = "MIT License\n\nPermission is hereby granted, free of charge, to any person...\n"
APACHE = "Apache License\nVersion 2.0, January 2004\n"
TODO = "TODO: Add your license here.\n"
GIT_ID = ("-c", "user.name=t", "-c", "user.email=t@example.org", "-c", "commit.gpgsign=false")


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *GIT_ID, *args], cwd=cwd, check=True, capture_output=True)


def make_repo(root: Path, files: dict[str, str], name: str = "repo") -> str:
    """A repo with one commit holding `files`; returns its file:// URL."""
    repo = root / name
    repo.mkdir()
    git(repo, "init", "--quiet", "--initial-branch=main")
    git(repo, "config", "uploadpack.allowFilter", "true")
    git(repo, "config", "uploadpack.allowAnySHA1InWant", "true")
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "--allow-empty", "-m", "init")
    return f"file://{repo}"


@pytest.fixture(autouse=True)
def cache_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "cache/upstream-license.json"
    monkeypatch.setattr(ul, "CACHE_FILE", path)
    monkeypatch.setattr(ul, "_now", lambda: 1_000_000.0)
    return path
