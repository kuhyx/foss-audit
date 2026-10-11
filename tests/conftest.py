"""Keep own_license away from the real ~/src: every test gets an empty fake home."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from foss_audit import own_license

MIT = "MIT License\n\nPermission is hereby granted, free of charge, to any person...\n"


def make_repo(
    path: Path, remote: str | None = "https://github.com/kuhyx/x.git", license_text: str | None = MIT
) -> Path:
    """A fake checkout: .git/config with an origin remote (none when `remote` is
    None, a local-only repo), plus a LICENSE."""
    (path / ".git").mkdir(parents=True)
    config = "[core]\n\tbare = false\n" if remote is None else f'[remote "origin"]\n\turl = {remote}\n'
    (path / ".git/config").write_text(config)
    if license_text is not None:
        (path / "LICENSE").write_text(license_text)
    return path


@pytest.fixture(autouse=True)
def fake_repo_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setattr(own_license, "HOME", tmp_path)
    monkeypatch.setattr(own_license, "REPO_ROOTS", (tmp_path / "src",))
    monkeypatch.setattr(own_license, "EXTRA_REPOS", (tmp_path / ".claude",))
    own_license.kuhy_repos.cache_clear()
    own_license.tracked_by_name.cache_clear()
    yield tmp_path
    own_license.kuhy_repos.cache_clear()
    own_license.tracked_by_name.cache_clear()
