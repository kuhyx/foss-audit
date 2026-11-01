"""Scan orchestration, CLI and the HTTP API."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from foss_audit import scan, server
from foss_audit.model import Item


def ok() -> list[Item]:
    return [Item(name="google-chrome", source="aur", verdict="nonfree")]


def boom() -> list[Item]:
    raise RuntimeError("expac missing")


def test_run_scan_isolates_failures() -> None:
    result = scan.run_scan({"aur": ok, "pacman": boom})
    assert [i["id"] for i in result["items"]] == ["aur:google-chrome"]
    assert result["items"][0]["alternative"]["fit"] == "drop-in"  # curated applied
    assert result["errors"] == [{"source": "pacman", "message": "RuntimeError: expac missing"}]
    assert "1 items" in scan.summary(result)
    assert "error pacman" in scan.summary(result)


def test_cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    result = {"items": [], "errors": [], "durationMs": 5}
    monkeypatch.setattr(scan, "run_scan", lambda progress=None: result)
    scan.main([])
    assert json.loads(capsys.readouterr().out) == result
    scan.main(["--summary"])
    assert capsys.readouterr().out.startswith("0 items in 5 ms")


def write_scan(path: Path, n: int) -> Path:
    path.write_text(json.dumps({"items": [], "errors": [], "n": n}))
    return path


def test_scan_file_is_served_and_reread_on_refresh(tmp_path: Path) -> None:
    saved = write_scan(tmp_path / "scan.json", 1)
    cache = server.ScanCache(scan_file=saved)
    assert cache.get(refresh=False)["n"] == 1
    write_scan(saved, 2)
    assert cache.get(refresh=False)["n"] == 1  # cached: no reread
    assert cache.get(refresh=True)["n"] == 2  # refresh re-reads the file, never scans


class IdleServer:
    def __init__(self, *_args: object) -> None:
        pass

    def serve_forever(self) -> None:
        pass


def test_server_main_loads_scan_file_at_startup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    saved = write_scan(tmp_path / "scan.json", 7)
    monkeypatch.setattr(server, "ThreadingHTTPServer", IdleServer)
    monkeypatch.setattr(server, "CACHE", server.ScanCache())
    monkeypatch.setattr(sys, "argv", ["server", "--scan-file", str(saved)])
    server.main()
    saved.unlink()  # already in memory: serving it must not touch the disk
    assert server.CACHE.get(refresh=False)["n"] == 7


@pytest.mark.parametrize("content", [None, "[1]", "{not json"])
def test_server_main_rejects_bad_scan_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str | None
) -> None:
    path = tmp_path / "scan.json"
    if content is not None:
        path.write_text(content)
    monkeypatch.setattr(server, "ThreadingHTTPServer", IdleServer)
    monkeypatch.setattr(sys, "argv", ["server", "--scan-file", str(path)])
    with pytest.raises(SystemExit) as exc:
        server.main()
    assert exc.value.code == 2
    assert "--scan-file" in capsys.readouterr().err
