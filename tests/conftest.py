"""Keep own_license away from the real ~/src (every test gets an empty fake home),
and upstream_license away from the network and the real cache."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from server_helpers import FakeScan, Serve

from foss_audit import memo, own_license, progress, server, upstream_git, upstream_license

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
    # pre-commit exports GIT_DIR/GIT_INDEX_FILE; left in place, the tests' git
    # calls hit the real repo (in a worktree this once set core.bare=true).
    for var in [v for v in os.environ if v.startswith("GIT_")]:
        monkeypatch.delenv(var)
    monkeypatch.setattr(own_license, "HOME", tmp_path)
    monkeypatch.setattr(own_license, "REPO_ROOTS", (tmp_path / "src",))
    monkeypatch.setattr(own_license, "EXTRA_REPOS", (tmp_path / ".claude",))
    own_license.kuhy_repos.cache_clear()
    own_license.tracked_by_name.cache_clear()
    yield tmp_path
    own_license.kuhy_repos.cache_clear()
    own_license.tracked_by_name.cache_clear()


@pytest.fixture(autouse=True)
def upstream_offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reads the real upstream-license cache or reaches a real git remote:
    git may only fetch file:// repos, so a stray network lookup fails at once."""
    monkeypatch.setattr(upstream_license, "CACHE_FILE", tmp_path / "upstream-cache/upstream-license.json")
    monkeypatch.setitem(upstream_git.ENV, "GIT_ALLOW_PROTOCOL", "file")


@pytest.fixture(autouse=True)
def no_real_projects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove commands are planned from ~/src projects: every cache scanner looks
    under the test's own (empty unless the test fills it) src dir instead."""
    from foss_audit import scan_cache_cargo, scan_cache_npm, scan_cache_pip, scan_cache_pub

    for module in (scan_cache_cargo, scan_cache_npm, scan_cache_pip, scan_cache_pub):
        monkeypatch.setattr(module, "SRC", tmp_path / "src")


@pytest.fixture(autouse=True)
def memo_off_the_machine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reads or writes the real ~/.cache/foss-audit/memo (workers inherit the env)."""
    monkeypatch.setenv(memo.ENV_DIR, str(tmp_path / "memo-dir"))


def _no_live_scan(progress: object = None) -> dict[str, object]:
    raise AssertionError("a test reached the real run_scan: stub server.run_scan")


@pytest.fixture(autouse=True)
def server_off_the_machine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The API never scans this machine or writes the real ~/.cache in a test."""
    monkeypatch.setattr(server, "DEFAULT_STORE", tmp_path / "default-store/scan.json")
    monkeypatch.setattr(server, "run_scan", _no_live_scan)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeScan:
    scan = FakeScan()
    monkeypatch.setattr(server, "run_scan", scan)
    return scan


@pytest.fixture
def store(tmp_path: Path) -> Path:
    return tmp_path / "cache" / "scan.json"


@pytest.fixture
def serve(monkeypatch: pytest.MonkeyPatch) -> Iterator[Serve]:
    servers: list[ThreadingHTTPServer] = []

    def start(cache: server.ScanCache) -> str:
        monkeypatch.setattr(server, "CACHE", cache)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers.append(httpd)
        return f"http://127.0.0.1:{httpd.server_address[1]}"

    yield start
    for httpd in servers:
        httpd.shutdown()


@pytest.fixture
def ticks() -> Iterator[dict[str, tuple[int, int | None]]]:
    """The last (done, total) each source's counter reported."""
    last: dict[str, tuple[int, int | None]] = {}
    progress.reset()
    progress.set_sink(lambda source, done, total: last.__setitem__(source, (done, total)))
    yield last
    progress.set_sink(None)
    progress.reset()
