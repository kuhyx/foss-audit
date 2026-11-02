"""/api/scan leaves out the two remove fields; POST /api/remove serves them per id."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from server_helpers import FakeScan, Serve, get, wait_until

from foss_audit import server, server_body

ITEMS = [
    {"id": "pacman:a", "name": "a", "removeCommand": "sudo pacman -Rns a", "removeVia": ""},
    {"id": "pip-cache:b", "name": "b", "removeCommand": None, "removeVia": "via torch"},
    {"id": "pacman:bare", "name": "bare"},
]
RESULT = {"generatedAt": "2026-01-01T00:00:00Z", "items": ITEMS, "errors": []}


def post(url: str, body: bytes, length: str | None = None) -> tuple[int, dict[str, object]]:
    request = urllib.request.Request(url, data=body, method="POST")
    if length is not None:
        request.add_unredirected_header("Content-Length", length)
    try:
        with urllib.request.urlopen(request) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


def post_ids(base: str, ids: object) -> tuple[int, dict[str, object]]:
    return post(f"{base}/api/remove", json.dumps({"ids": ids}).encode())


def started(store: Path, serve: Serve, result: dict[str, object] = RESULT) -> str:
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps(result))
    cache = server.ScanCache(store=store)
    cache.start()
    return serve(cache)


@pytest.fixture(autouse=True)
def release_the_scan(fake: FakeScan) -> Iterator[None]:
    """The startup rescan stays blocked during a test (the saved result is served), then ends."""
    yield
    fake.release.set()


@pytest.fixture
def base(store: Path, serve: Serve) -> str:
    return started(store, serve)


def test_scan_items_carry_no_remove_fields(base: str) -> None:
    status, body = get(f"{base}/api/scan")
    assert status == 200
    assert body["items"] == [
        {"id": "pacman:a", "name": "a"},
        {"id": "pip-cache:b", "name": "b"},
        {"id": "pacman:bare", "name": "bare"},
    ]


def test_the_served_result_in_memory_stays_full() -> None:
    encoded = server_body.EncodedScan(RESULT)
    assert encoded.result["items"] == ITEMS
    assert b"removeCommand" not in b"".join(encoded.parts(scanning=False, zipped=False))


def test_the_id_index_is_built_once() -> None:
    encoded = server_body.EncodedScan(RESULT)
    assert encoded.removes(["pacman:a"]) == encoded.removes(["pacman:a"])


def test_a_result_without_an_item_list_is_encoded_as_it_is() -> None:
    encoded = server_body.EncodedScan({"n": 1})
    assert json.loads(b"".join(encoded.parts(scanning=False, zipped=False))) == {"n": 1, "scanning": False}


def test_remove_returns_both_fields_per_id_and_omits_unknown_ids(base: str) -> None:
    status, body = post_ids(base, ["pip-cache:b", "pacman:a", "pacman:bare", "nope:x"])
    assert status == 200
    assert body == {
        "pacman:a": {"removeCommand": "sudo pacman -Rns a", "removeVia": ""},
        "pip-cache:b": {"removeCommand": None, "removeVia": "via torch"},
        "pacman:bare": {"removeCommand": None, "removeVia": ""},
    }


def test_remove_with_no_ids_is_an_empty_object(base: str) -> None:
    assert post_ids(base, []) == (200, {})


def test_remove_on_a_result_without_an_item_list_is_an_empty_object(store: Path, serve: Serve) -> None:
    assert post_ids(started(store, serve, {"items": 3}), ["pacman:a"]) == (200, {})


def test_remove_before_the_first_result_is_an_empty_object(store: Path, serve: Serve) -> None:
    cache = server.ScanCache(store=store)
    cache.start()
    assert post_ids(serve(cache), ["pacman:a"]) == (200, {})


def test_remove_works_in_scan_file_mode(tmp_path: Path, serve: Serve) -> None:
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(RESULT))
    cache = server.ScanCache(scan_file=path)
    cache.start()
    status, body = post_ids(serve(cache), ["pacman:a"])
    assert (status, body["pacman:a"]) == (200, {"removeCommand": "sudo pacman -Rns a", "removeVia": ""})


def test_remove_follows_a_swapped_in_result(fake: FakeScan, store: Path, serve: Serve) -> None:
    base = started(store, serve)
    assert post_ids(base, ["pacman:a"])[1] != {}
    fake.release.set()
    wait_until(lambda: get(f"{base}/api/scan")[1].get("n") == 1)
    assert post_ids(base, ["pacman:a"]) == (200, {})


@pytest.mark.parametrize(
    "body",
    [b"", b"{nope", b"[]", b'{"ids": "pacman:a"}', b'{"ids": [1]}', b"{}", b"\xff\xfe"],
)
def test_a_bad_body_is_a_400_json_error(base: str, body: bytes) -> None:
    status, reply = post(f"{base}/api/remove", body)
    assert status == 400
    assert isinstance(reply["error"], str)


def test_a_bad_content_length_is_a_400(base: str) -> None:
    assert post(f"{base}/api/remove", b"", length="x")[0] == 400
    assert post(f"{base}/api/remove", b"", length="-1")[0] == 400


def test_an_oversized_body_is_refused_unread(base: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "MAX_BODY", 10)
    status, reply = post(f"{base}/api/remove", json.dumps({"ids": ["pacman:a"]}).encode())
    assert status == 400
    assert "too large" in str(reply["error"])


def test_other_post_routes_are_404(base: str) -> None:
    assert post(f"{base}/api/scan", b"{}")[0] == 404
