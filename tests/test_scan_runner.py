"""Scanners run in worker processes; progress flows back and order stays fixed."""

from __future__ import annotations

import threading
import time
from collections import deque
from functools import partial
from pathlib import Path

import pytest
import runner_helpers as helpers

from foss_audit import progress, scan_runner
from foss_audit.model import ScanError


class FakeQueue:
    def __init__(self, messages: list[object] | None = None) -> None:
        self.messages: deque[object] = deque(messages or [])

    def put(self, message: object) -> None:
        self.messages.append(message)

    def get(self) -> object:
        return self.messages.popleft()


def test_results_keep_the_scanners_order_and_failures_become_errors() -> None:
    state = progress.ScanProgress()
    state.begin(3)
    items, errors = scan_runner.run_sources(
        {"slow": helpers.slow_item, "boom": helpers.failing, "fast": helpers.one_item}, state
    )
    assert [i.name for i in items] == ["slow", "fast"]
    assert errors == [ScanError(source="boom", message="RuntimeError: expac missing")]
    assert state.snapshot() == {"sourcesDone": 3, "sourcesTotal": 3, "itemsFound": 2, "running": []}


@pytest.mark.parametrize("full", [False, True])
def test_a_full_scan_starts_its_workers_with_the_memo_bypassed(full: bool) -> None:
    items, _ = scan_runner.run_sources({"x": helpers.bypass_flag}, progress.ScanProgress(), full=full)
    assert [i.name for i in items] == [str(full)]


def test_a_worker_that_dies_is_an_error_entry() -> None:
    items, errors = scan_runner.run_sources({"dead": helpers.crashing}, progress.ScanProgress())
    assert items == []
    assert [e.source for e in errors] == ["dead"]
    assert errors[0].message.startswith("BrokenProcessPool")


def test_inner_counts_reach_the_parent_while_the_scanner_runs(tmp_path: Path) -> None:
    gate = tmp_path / "gate"
    state = progress.ScanProgress()
    state.begin(1)
    done: list[object] = []
    thread = threading.Thread(
        target=lambda: done.append(
            scan_runner.run_sources({"ticker": partial(helpers.ticker, str(gate))}, state)
        )
    )
    thread.start()
    deadline = time.monotonic() + 30
    expected = [{"source": "ticker", "done": 2, "total": 4}]
    while state.snapshot()["running"] != expected and time.monotonic() < deadline:
        time.sleep(0.05)
    seen = state.snapshot()["running"]
    gate.touch()
    thread.join(30)
    assert seen == expected
    assert state.snapshot()["sourcesDone"] == 1
    assert [i.name for i in done[0][0]] == ["tick-a", "tick-b"]  # type: ignore[index]


def test_slow_sources_are_submitted_first() -> None:
    names = ["pacman", "pip-cache", "flatpak", "npm-cache"]
    assert scan_runner.submit_order(dict.fromkeys(names)) == ["pip-cache", "npm-cache", "pacman", "flatpak"]  # type: ignore[arg-type]


def test_worker_side_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    queue = FakeQueue()
    monkeypatch.setattr(scan_runner, "_queue", queue)
    monkeypatch.setattr(progress, "_sink", None)
    scan_runner._init_worker(queue, False)  # type: ignore[arg-type]
    items = scan_runner._run_one("ticker", partial(helpers.ticker, str(Path(__file__))))
    assert [i.name for i in items] == ["tick-a", "tick-b"]
    assert list(queue.messages)[0] == ("start", "ticker")
    assert ("tick", "ticker", 0, 4) in queue.messages
    assert ("tick", "ticker", 4, 4) in queue.messages


def test_drain_applies_messages_until_the_sentinel() -> None:
    state = progress.ScanProgress()
    queue = FakeQueue([("start", "a"), ("tick", "a", 1, 5), None, ("start", "b")])
    scan_runner._drain(queue, state)  # type: ignore[arg-type]
    assert state.snapshot()["running"] == [{"source": "a", "done": 1, "total": 5}]
