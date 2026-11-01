"""The per-source counters scanners report into, and the run-wide progress state."""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest

from foss_audit import progress


class Clock:
    """A settable monotonic clock for the throttling tests."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def sink() -> Iterator[list[tuple[str, int, int | None]]]:
    seen: list[tuple[str, int, int | None]] = []
    progress.set_sink(lambda source, done, total: seen.append((source, done, total)))
    yield seen
    progress.set_sink(None)
    progress.reset()


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(progress, "monotonic", fake)
    return fake


def test_counter_without_a_sink_is_a_no_op() -> None:
    progress.set_sink(None)
    counter = progress.begin_source("npm-cache")
    counter.add_total(3)
    counter.advance()
    assert (counter.done, counter.total) == (1, 3)


def test_counter_reports_total_and_throttles_advances(
    sink: list[tuple[str, int, int | None]], clock: Clock
) -> None:
    counter = progress.begin_source("maven-cache")
    counter.add_total(10)
    assert sink == [("maven-cache", 0, 10)]
    counter.advance()  # within the interval of the total: swallowed
    counter.advance()
    assert len(sink) == 1
    clock.now += 1
    counter.advance()
    assert sink[-1] == ("maven-cache", 3, 10)


def test_counter_always_reports_the_last_step(sink: list[tuple[str, int, int | None]], clock: Clock) -> None:
    counter = progress.begin_source("pub-cache")
    counter.add_total(2)
    counter.advance()
    counter.advance()  # same instant, but done == total
    assert sink[-1] == ("pub-cache", 2, 2)
    assert clock() == 100.0


def test_totals_accumulate_across_phases(sink: list[tuple[str, int, int | None]]) -> None:
    counter = progress.begin_source("npm-cache")
    counter.add_total(2)
    counter.add_total(3)
    assert sink[-1] == ("npm-cache", 0, 5)


def test_counter_is_shared_per_source_and_begin_source_resets_it() -> None:
    first = progress.begin_source("pip-cache")
    first.add_total(4)
    assert progress.counter("pip-cache") is first
    assert progress.begin_source("pip-cache") is not first
    assert progress.counter("pip-cache").total is None


def test_counter_is_thread_safe() -> None:
    counter = progress.begin_source("npm-cache")
    counter.add_total(4000)
    threads = [threading.Thread(target=lambda: [counter.advance() for _ in range(500)]) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert counter.done == 4000


def test_counted_advances_per_item(sink: list[tuple[str, int, int | None]]) -> None:
    progress.begin_source("cargo-cache")
    assert list(progress.counted("cargo-cache", ["a", "b", "c"])) == ["a", "b", "c"]
    assert progress.counter("cargo-cache").done == 3
    assert progress.counter("cargo-cache").total == 3
    assert sink[0] == ("cargo-cache", 0, 3)


def test_scan_progress_tracks_sources() -> None:
    state = progress.ScanProgress()
    assert state.snapshot() == {"sourcesDone": 0, "sourcesTotal": 0, "itemsFound": 0, "running": []}
    state.begin(3)
    state.started("a")
    state.started("b")
    state.advanced("a", 2, None)
    state.advanced("b", 5, 9)
    assert state.snapshot()["running"] == [
        {"source": "a", "done": 2, "total": None},
        {"source": "b", "done": 5, "total": 9},
    ]
    state.finished("a", 40)
    state.finished("b", 2)
    assert state.snapshot() == {"sourcesDone": 2, "sourcesTotal": 3, "itemsFound": 42, "running": []}


def test_scan_progress_ignores_late_messages() -> None:
    state = progress.ScanProgress()
    state.begin(1)
    state.started("a")
    state.finished("a", 1)
    state.advanced("a", 9, 9)  # a tick that overtook the result
    state.started("a")  # a start that arrived after the result
    state.advanced("never-started", 1, 1)
    assert state.snapshot()["running"] == []


def test_scan_progress_begin_resets_the_previous_run() -> None:
    state = progress.ScanProgress()
    state.begin(2)
    state.started("a")
    state.finished("a", 7)
    state.begin(5)
    assert state.snapshot() == {"sourcesDone": 0, "sourcesTotal": 5, "itemsFound": 0, "running": []}
    state.started("a")  # allowed again in the new run
    assert state.snapshot()["running"] == [{"source": "a", "done": 0, "total": None}]
