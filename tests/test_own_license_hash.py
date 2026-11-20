"""Copies installed under another name are traced to the kuhy repo by content hash."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from conftest import make_repo

from foss_audit import own_license, scan_unowned

SHIM = (
    "#!/bin/bash\n# nmap shim: a wrapper deployed as /usr/local/bin/nmap\n" + 'exec /usr/bin/nmap "$@"\n' * 4
)


def track(repo: Path, rel: str, text: str) -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    subprocess.run(["git", "-C", str(repo), "add", rel], check=True)
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = make_repo(tmp_path / "src/digital-wellbeing")
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def test_copy_under_a_different_name_is_traced(tmp_path: Path, repo: Path) -> None:
    tracked = track(repo, "pacman/nmap_shim.sh", SHIM)
    copy = tmp_path / "usr/local/bin/nmap"
    copy.parent.mkdir(parents=True)
    copy.write_text(SHIM)
    assert own_license.origin_of(copy) == tracked


def test_unowned_nmap_is_foss_with_the_repo_license(
    tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracked = track(repo, "pacman/nmap_shim.sh", SHIM)
    copy = tmp_path / "usr/local/bin/nmap"
    copy.parent.mkdir(parents=True)
    copy.write_text(SHIM)
    copy.chmod(0o755)
    monkeypatch.setattr(scan_unowned, "owned_by_pacman", lambda _paths: set())
    item = scan_unowned.classify(copy, (copy.parent,))
    assert item is not None
    assert (item.id, item.verdict, item.license, item.own) == ("unowned:nmap", "foss", "MIT", True)
    assert item.reason == f"copy of {tracked}"


def test_edited_copy_is_not_traced(tmp_path: Path, repo: Path) -> None:
    track(repo, "pacman/nmap_shim.sh", SHIM)
    copy = tmp_path / "bin/nmap"
    copy.parent.mkdir()
    copy.write_text(SHIM + "# local edit\n")
    assert own_license.origin_of(copy) is None


def test_tiny_and_oversized_files_are_never_hashed(
    tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    track(repo, "a/stub.sh", "#!/bin/sh\n")
    big = track(repo, "a/big.bin", SHIM)
    monkeypatch.setattr(own_license, "MAX_HASHED_BYTES", len(SHIM) - 1)
    tiny_copy = tmp_path / "bin/tool"
    tiny_copy.parent.mkdir()
    tiny_copy.write_text("#!/bin/sh\n")
    big_copy = tmp_path / "bin/other"
    big_copy.write_text(big.read_text())
    assert own_license.origin_of(tiny_copy) is None
    assert own_license.origin_of(big_copy) is None


def test_tracked_symlinks_and_deleted_files_are_skipped(tmp_path: Path, repo: Path) -> None:
    real = track(repo, "a/real.sh", SHIM)
    (repo / "a/link.sh").symlink_to(real)
    gone = track(repo, "a/gone.sh", SHIM + "# gone\n")
    subprocess.run(["git", "-C", str(repo), "add", "a/link.sh"], check=True)
    gone.unlink()
    copy = tmp_path / "bin/tool"
    copy.parent.mkdir()
    copy.write_text(SHIM)
    assert own_license.origin_of(copy) == real
    assert own_license.origin_of(tmp_path / "bin/missing") is None
