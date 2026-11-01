"""/api/scan sends bytes encoded once per result, gzipped when the client accepts it."""

from __future__ import annotations

import gzip
import json
import time
import urllib.request
from pathlib import Path

import pytest
from server_helpers import FakeScan, Serve, saved, wait_until

from foss_audit import server, server_body

BIG = {
    "generatedAt": "2026-01-01T00:00:00Z",
    "items": [{"id": f"pacman:p{i}", "name": f"p{i}", "reason": "x" * 600} for i in range(4000)],
    "errors": [],
}


def fetch(url: str, accept: str | None) -> tuple[dict[str, str], bytes]:
    request = urllib.request.Request(url, headers={} if accept is None else {"Accept-Encoding": accept})
    with urllib.request.urlopen(request) as resp:
        return dict(resp.headers), resp.read()


def unzipped(url: str) -> dict[str, object]:
    return json.loads(gzip.decompress(fetch(url, "gzip")[1]))  # type: ignore[no-any-return]


def serve_big(store: Path, serve: Serve) -> str:
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps(BIG))
    cache = server.ScanCache(store=store)
    cache.start()
    return serve(cache)


def test_the_result_is_json_encoded_once_however_often_it_is_fetched(
    fake: FakeScan, store: Path, serve: Serve, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = serve_big(store, serve)
    fetch(f"{base}/api/scan", None)  # the first fetch (or the prewarm) encodes
    calls: list[int] = []
    real = json.dumps

    def spy(obj: object, **kw: object) -> str:
        calls.append(1)
        return real(obj, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(server_body.json, "dumps", spy)
    for accept in (None, "gzip", None, "gzip", "identity"):
        fetch(f"{base}/api/scan", accept)
    assert calls == []
    fake.release.set()


def test_gzip_body_equals_the_plain_body_and_carries_the_scanning_flag(
    fake: FakeScan, store: Path, serve: Serve
) -> None:
    base = serve_big(store, serve)
    assert fake.started.wait(10)
    plain_headers, plain = fetch(f"{base}/api/scan", None)
    zipped_headers, zipped = fetch(f"{base}/api/scan", "br, gzip;q=0.8")
    assert "Content-Encoding" not in plain_headers
    assert zipped_headers["Content-Encoding"] == "gzip"
    assert "Accept-Encoding" in zipped_headers["Vary"]
    assert len(zipped) < len(plain) / 10
    assert json.loads(gzip.decompress(zipped)) == json.loads(plain)
    assert json.loads(plain)["scanning"] is True
    fake.release.set()


@pytest.mark.parametrize("accept", ["gzip;q=0", "identity", "br", "*;q=0"])
def test_gzip_is_not_sent_unless_accepted(fake: FakeScan, store: Path, serve: Serve, accept: str) -> None:
    base = serve_big(store, serve)
    headers, body = fetch(f"{base}/api/scan", accept)
    assert "Content-Encoding" not in headers
    assert json.loads(body)["items"][0]["id"] == "pacman:p0"
    fake.release.set()


def test_a_finished_rescan_replaces_the_cached_bytes(fake: FakeScan, store: Path, serve: Serve) -> None:
    saved(store, 7)
    cache = server.ScanCache(store=store)
    cache.start()
    base = serve(cache)
    assert unzipped(f"{base}/api/scan")["n"] == 7
    fake.release.set()
    wait_until(lambda: unzipped(f"{base}/api/scan")["n"] == 1)
    assert unzipped(f"{base}/api/scan")["scanning"] is False


def test_a_cached_fetch_of_a_big_result_is_fast(fake: FakeScan, store: Path, serve: Serve) -> None:
    base = serve_big(store, serve)
    fetch(f"{base}/api/scan", "gzip")  # the first one may wait for the encoder
    best = float("inf")
    for _ in range(5):
        began = time.perf_counter()
        fetch(f"{base}/api/scan", "gzip")
        best = min(best, time.perf_counter() - began)
    assert best < 0.02
    fake.release.set()


def test_an_empty_result_still_gets_the_scanning_flag() -> None:
    encoded = server_body.EncodedScan({})
    assert json.loads(b"".join(encoded.parts(scanning=True, zipped=False))) == {"scanning": True}
    assert json.loads(gzip.decompress(b"".join(encoded.parts(scanning=False, zipped=True)))) == {
        "scanning": False
    }


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, False),
        ("gzip", True),
        ("deflate, GZIP", True),
        ("br;q=1.0, gzip;q=0.5", True),
        ("gzip;q=0", False),
        ("*", True),
        ("*;q=0", False),
        ("identity", False),
        ("gzip;q=oops", False),
    ],
)
def test_accepts_gzip(header: str | None, expected: bool) -> None:
    assert server_body.accepts_gzip(header) is expected
