"""Progress of a running scan: scanner-side counters and the run-wide state."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable, Iterator, Sequence
from time import monotonic
from typing import Any

Sink = Callable[[str, int, "int | None"], None]
MIN_INTERVAL_S = 0.1

_sink: Sink | None = None
_counters: dict[str, Counter] = {}
_registry_lock = threading.Lock()


class Counter:
    """done/total of one source, thread-safe; totals accumulate over phases."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.done = 0
        self.total: int | None = None
        self._lock = threading.Lock()
        self._last_sent: float | None = None

    def add_total(self, count: int) -> None:
        with self._lock:
            self.total = (self.total or 0) + count
            self._send()

    def advance(self, count: int = 1) -> None:
        with self._lock:
            self.done += count
            at_end = self.total is not None and self.done >= self.total
            if at_end or self._last_sent is None or monotonic() - self._last_sent >= MIN_INTERVAL_S:
                self._send()

    def _send(self) -> None:
        self._last_sent = monotonic()
        if _sink is not None:
            _sink(self.source, self.done, self.total)


def set_sink(sink: Sink | None) -> None:
    global _sink  # noqa: PLW0603 - one sink per process
    _sink = sink


def counter(source: str) -> Counter:
    """This process's counter for `source`; a no-op until a sink is set."""
    with _registry_lock:
        return _counters.setdefault(source, Counter(source))


def begin_source(source: str) -> Counter:
    with _registry_lock:
        _counters[source] = Counter(source)
        return _counters[source]


def reset() -> None:
    with _registry_lock:
        _counters.clear()


def counted[T](source: str, items: Iterable[T]) -> Iterator[T]:
    """Yield `items`, adding their number to the total and advancing per item."""
    seq: Sequence[T] = items if isinstance(items, Sequence) else list(items)
    shared = counter(source)
    shared.add_total(len(seq))
    for item in seq:
        yield item
        shared.advance()


class ScanProgress:
    """Sources done/running and items found; a finished source ignores late updates."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._finished: set[str] = set()
        self._running: dict[str, tuple[int, int | None]] = {}
        self._total = 0
        self._items = 0

    def begin(self, sources_total: int) -> None:
        with self._lock:
            self._finished.clear()
            self._running.clear()
            self._total, self._items = sources_total, 0

    def started(self, source: str) -> None:
        with self._lock:
            if source not in self._finished:
                self._running.setdefault(source, (0, None))

    def advanced(self, source: str, done: int, total: int | None) -> None:
        with self._lock:
            if source in self._running:
                self._running[source] = (done, total)

    def finished(self, source: str, items: int) -> None:
        with self._lock:
            self._running.pop(source, None)
            self._finished.add(source)
            self._items += items

    def snapshot(self) -> dict[str, Any]:
        """The counter half of the /api/scan/progress body."""
        with self._lock:
            return {
                "sourcesDone": len(self._finished),
                "sourcesTotal": self._total,
                "itemsFound": self._items,
                "running": [
                    {"source": source, "done": done, "total": total}
                    for source, (done, total) in self._running.items()
                ],
            }
