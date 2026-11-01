"""Run the scanners concurrently, one worker process each (threads stay GIL-bound).

Workers are spawned, not forked: the server calling in is multi-threaded.
Counter updates travel back on a queue to a drain thread in the parent.
"""

from __future__ import annotations

import multiprocessing
import threading
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing.queues import SimpleQueue
from typing import Any

from foss_audit import progress
from foss_audit.model import Item, ScanError

Scanner = Callable[[], list[Item]]
MAX_WORKERS = 12
# Longest first, so the slow ones start at once and the short ones fill the gaps.
SLOW_FIRST = ("npm-cache", "maven-cache", "pip-cache", "pub-cache", "cargo-cache")

_queue: SimpleQueue[Any] | None = None


def _emit(source: str, done: int, total: int | None) -> None:
    assert _queue is not None
    _queue.put(("tick", source, done, total))


def _init_worker(queue: SimpleQueue[Any]) -> None:
    global _queue  # noqa: PLW0603 - the worker's one channel to the parent
    _queue = queue
    progress.set_sink(_emit)


def _run_one(source: str, scanner: Scanner) -> list[Item]:
    assert _queue is not None
    progress.begin_source(source)
    _queue.put(("start", source))
    return scanner()


def _drain(queue: SimpleQueue[Any], state: progress.ScanProgress) -> None:
    """Apply worker messages to `state` until the None sentinel."""
    while (message := queue.get()) is not None:
        if message[0] == "start":
            state.started(message[1])
        else:
            state.advanced(*message[1:])


def submit_order(scanners: dict[str, Scanner]) -> list[str]:
    """Sources with the slow ones first (otherwise in the given order)."""
    return sorted(scanners, key=lambda source: source not in SLOW_FIRST)


def run_sources(
    scanners: dict[str, Scanner], state: progress.ScanProgress
) -> tuple[list[Item], list[ScanError]]:
    """Every scanner's items (in `scanners` order) and one error per failed scanner."""
    context = multiprocessing.get_context("spawn")
    queue = context.SimpleQueue()
    drain = threading.Thread(target=_drain, args=(queue, state), daemon=True)
    drain.start()
    results: dict[str, list[Item]] = {}
    failures: dict[str, ScanError] = {}
    try:
        with ProcessPoolExecutor(
            max_workers=min(MAX_WORKERS, len(scanners)),
            mp_context=context,
            initializer=_init_worker,
            initargs=(queue,),
        ) as pool:
            futures = {
                pool.submit(_run_one, source, scanners[source]): source for source in submit_order(scanners)
            }
            for future in as_completed(futures):
                source = futures[future]
                try:
                    results[source] = future.result()
                except Exception as exc:  # noqa: BLE001 - one scanner failing must not end the scan
                    failures[source] = ScanError(source=source, message=f"{type(exc).__name__}: {exc}")
                state.finished(source, len(results.get(source, [])))
    finally:
        queue.put(None)
        drain.join()
    items = [item for source in scanners for item in results.get(source, [])]
    return items, [failures[source] for source in scanners if source in failures]
