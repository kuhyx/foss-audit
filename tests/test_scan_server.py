"""Scan orchestration, CLI and the HTTP API."""

from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer

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
    monkeypatch.setattr(scan, "run_scan", lambda: result)
    scan.main([])
    assert json.loads(capsys.readouterr().out) == result
    scan.main(["--summary"])
    assert capsys.readouterr().out.startswith("0 items in 5 ms")


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    calls: list[int] = []

    def fake_scan() -> dict[str, object]:
        calls.append(1)
        return {"items": [], "errors": [], "n": len(calls)}

    monkeypatch.setattr(server, "run_scan", fake_scan)
    monkeypatch.setattr(server, "CACHE", server.ScanCache())
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def get(url: str) -> tuple[int, dict[str, object]]:
    try:
        with urllib.request.urlopen(url) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


def test_api_routes_and_cache(api: str) -> None:
    assert get(f"{api}/api/health") == (200, {"ok": True})
    assert get(f"{api}/api/scan")[1]["n"] == 1
    assert get(f"{api}/api/scan")[1]["n"] == 1  # cached
    assert get(f"{api}/api/scan?refresh=1")[1]["n"] == 2
    assert get(f"{api}/nope") == (404, {"error": "no route /nope"})


def test_server_main_binds_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    class FakeServer:
        def __init__(self, addr: tuple[str, int], _handler: object) -> None:
            seen["addr"] = addr

        def serve_forever(self) -> None:
            seen["served"] = True

    monkeypatch.setattr(server, "ThreadingHTTPServer", FakeServer)
    monkeypatch.setattr(sys, "argv", ["server", "--port", "6000"])
    server.main()
    assert seen == {"addr": ("127.0.0.1", 6000), "served": True}
