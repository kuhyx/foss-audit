"""The non-blocking API: saved result served at once, rescans in the background."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
from server_helpers import FakeScan, Serve, get, saved, wait_until

from foss_audit import server


def test_first_run_answers_202_while_the_scan_runs(fake: FakeScan, store: Path, serve: Serve) -> None:
    cache = server.ScanCache(store=store)
    cache.start()
    base = serve(cache)
    assert fake.started.wait(10)
    began = time.monotonic()
    assert get(f"{base}/api/scan") == (202, {"scanning": True})
    assert time.monotonic() - began < 0.1
    fake.release.set()
    wait_until(lambda: get(f"{base}/api/scan")[0] == 200)
    status, body = get(f"{base}/api/scan")
    assert (status, body["n"], body["scanning"]) == (200, 1, False)
    assert json.loads(store.read_text())["n"] == 1  # persisted for the next start
    assert [p.name for p in store.parent.iterdir()] == ["scan.json"]  # no tmp file left


def test_saved_result_is_served_at_once_during_the_startup_rescan(
    fake: FakeScan, store: Path, serve: Serve
) -> None:
    saved(store, 7)
    cache = server.ScanCache(store=store)
    cache.start()
    base = serve(cache)
    assert fake.started.wait(10)
    began = time.monotonic()
    status, body = get(f"{base}/api/scan")
    assert time.monotonic() - began < 0.1
    assert (status, body["n"], body["scanning"]) == (200, 7, True)
    fake.release.set()
    wait_until(lambda: get(f"{base}/api/scan")[1]["n"] == 1)
    assert get(f"{base}/api/scan")[1]["scanning"] is False


def test_corrupt_saved_result_means_no_result(fake: FakeScan, store: Path, serve: Serve) -> None:
    store.parent.mkdir(parents=True)
    store.write_text("{not json")
    cache = server.ScanCache(store=store)
    cache.start()
    assert get(f"{serve(cache)}/api/scan") == (202, {"scanning": True})
    fake.release.set()


def test_refresh_starts_one_rescan_only(fake: FakeScan, store: Path, serve: Serve) -> None:
    saved(store, 7)
    cache = server.ScanCache(store=store)
    cache.start()
    base = serve(cache)
    assert fake.started.wait(10)
    assert get(f"{base}/api/scan?refresh=1")[1]["scanning"] is True  # already running
    assert get(f"{base}/api/scan?refresh=full")[1]["scanning"] is True
    fake.release.set()
    wait_until(lambda: get(f"{base}/api/scan")[1]["scanning"] is False)
    assert fake.calls == 1
    assert get(f"{base}/api/scan?refresh=full")[1]["scanning"] is True
    wait_until(lambda: fake.calls == 2)
    assert fake.fulls == [False, True]  # the startup rescan is incremental, refresh=full is not


def test_refresh_one_rescans_incrementally(fake: FakeScan, store: Path, serve: Serve) -> None:
    saved(store, 7)
    cache = server.ScanCache(store=store)
    cache.start()
    base = serve(cache)
    fake.release.set()
    wait_until(lambda: get(f"{base}/api/scan")[1]["scanning"] is False)
    get(f"{base}/api/scan?refresh=1")
    wait_until(lambda: fake.calls == 2)
    assert fake.fulls == [False, False]


def test_a_crashed_rescan_keeps_the_old_result_and_reports_the_error(
    fake: FakeScan, store: Path, serve: Serve
) -> None:
    saved(store, 7)
    fake.failure = RuntimeError("expac exploded")
    cache = server.ScanCache(store=store)
    cache.start()
    base = serve(cache)
    assert fake.started.wait(10)
    fake.release.set()
    wait_until(lambda: get(f"{base}/api/scan/progress")[1]["scanning"] is False)
    assert get(f"{base}/api/scan/progress")[1]["error"] == "RuntimeError: expac exploded"
    assert get(f"{base}/api/scan")[1]["n"] == 7
    assert json.loads(store.read_text())["n"] == 7
    fake.failure = None
    get(f"{base}/api/scan?refresh=1")
    assert get(f"{base}/api/scan/progress")[1]["error"] is None  # cleared by the new rescan
    wait_until(lambda: get(f"{base}/api/scan")[1]["n"] == 2)


def test_progress_reports_counts_while_scanning(fake: FakeScan, store: Path, serve: Serve) -> None:
    saved(store, 7)
    cache = server.ScanCache(store=store)
    cache.start()
    base = serve(cache)
    assert fake.started.wait(10)
    wait_until(lambda: get(f"{base}/api/scan/progress")[1]["running"] != [])
    busy = get(f"{base}/api/scan/progress")[1]
    assert busy["scanning"] is True
    assert busy["generatedAt"] == "2026-01-01T00:00:00Z"  # still the served result's
    assert (busy["sourcesDone"], busy["sourcesTotal"]) == (0, 2)
    assert busy["running"] == [{"source": "a", "done": 3, "total": 9}]
    assert busy["error"] is None
    fake.release.set()
    wait_until(lambda: get(f"{base}/api/scan/progress")[1]["generatedAt"] == "2026-02-01T00:00:00Z")


def test_progress_before_any_result_has_a_null_generated_at(serve: Serve) -> None:
    status, body = get(f"{serve(server.ScanCache())}/api/scan/progress")
    assert status == 200
    assert body == {
        "scanning": False,
        "generatedAt": None,
        "sourcesDone": 0,
        "sourcesTotal": 0,
        "itemsFound": 0,
        "running": [],
        "error": None,
    }


def test_scan_file_mode_never_scans_and_never_writes(
    fake: FakeScan, store: Path, tmp_path: Path, serve: Serve
) -> None:
    file = tmp_path / "fixture.json"
    saved(file, 3, "2026-03-03T00:00:00Z")
    cache = server.ScanCache(scan_file=file, store=store)
    cache.start()
    base = serve(cache)
    assert get(f"{base}/api/scan")[1]["n"] == 3
    assert get(f"{base}/api/scan")[1]["scanning"] is False
    saved(file, 4, "2026-03-04T00:00:00Z")
    status, body = get(f"{base}/api/scan?refresh=1")
    assert (status, body["n"], body["scanning"]) == (200, 4, False)
    assert get(f"{base}/api/scan?refresh=full")[1]["n"] == 4
    progress_body = get(f"{base}/api/scan/progress")[1]
    assert (progress_body["scanning"], progress_body["generatedAt"]) == (False, "2026-03-04T00:00:00Z")
    assert fake.calls == 0
    assert not store.parent.exists()


def test_a_store_that_cannot_be_written_does_not_lose_the_result(
    fake: FakeScan, tmp_path: Path, serve: Serve, capsys: pytest.CaptureFixture[str]
) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where the cache dir should be")
    cache = server.ScanCache(store=blocker / "scan.json")
    cache.start()
    base = serve(cache)
    assert fake.started.wait(10)
    fake.release.set()
    wait_until(lambda: get(f"{base}/api/scan")[0] == 200)
    assert "could not save" in capsys.readouterr().err


def test_without_a_store_results_stay_in_memory(fake: FakeScan, serve: Serve) -> None:
    cache = server.ScanCache()
    cache.start()
    base = serve(cache)
    fake.release.set()
    wait_until(lambda: get(f"{base}/api/scan")[0] == 200)
    assert get(f"{base}/api/scan")[1]["n"] == 1


class IdleServer:
    addr: tuple[str, int] | None = None

    def __init__(self, addr: tuple[str, int], *_args: object) -> None:
        IdleServer.addr = addr

    def serve_forever(self) -> None:
        pass


def test_main_loads_the_store_and_starts_a_rescan(
    fake: FakeScan, store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved(store, 7)
    monkeypatch.setattr(server, "DEFAULT_STORE", store)
    monkeypatch.setattr(server, "ThreadingHTTPServer", IdleServer)
    monkeypatch.setattr(sys, "argv", ["server", "--port", "6000"])
    server.main()
    assert fake.started.wait(10)
    body = server.CACHE.get(refresh=False)
    assert body is not None
    assert (body["n"], body["scanning"]) == (7, True)
    assert IdleServer.addr == ("127.0.0.1", 6000)
    fake.release.set()


def test_health_and_unknown_routes(serve: Serve) -> None:
    base = serve(server.ScanCache())
    assert get(f"{base}/api/health") == (200, {"ok": True})
    assert get(f"{base}/nope") == (404, {"error": "no route /nope"})
