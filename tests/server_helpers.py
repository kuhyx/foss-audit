"""Shared by the HTTP API tests: a blockable run_scan, an HTTP getter, polling."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from foss_audit import progress, server


class FakeScan:
    """A run_scan stand-in that blocks until released, so tests see the scanning state."""

    def __init__(self) -> None:
        self.calls = 0
        self.fulls: list[bool] = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.failure: Exception | None = None

    def __call__(self, progress: progress.ScanProgress, full: bool = False) -> dict[str, object]:
        self.calls += 1
        self.fulls.append(full)
        self.started.set()
        progress.begin(2)
        progress.started("a")
        progress.advanced("a", 3, 9)
        assert self.release.wait(20)
        if self.failure is not None:
            raise self.failure
        return {"generatedAt": f"2026-02-0{self.calls}T00:00:00Z", "items": [], "errors": [], "n": self.calls}


Serve = Callable[[server.ScanCache], str]


def get(url: str) -> tuple[int, dict[str, object]]:
    try:
        with urllib.request.urlopen(url) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


def saved(path: Path, n: int, generated: str = "2026-01-01T00:00:00Z") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"generatedAt": generated, "items": [], "errors": [], "n": n}))


def wait_until(check: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 10
    while not check():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)
