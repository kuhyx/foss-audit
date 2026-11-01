"""Module-level scanners for the process-pool tests (workers import them by name)."""

from __future__ import annotations

import os
import time
from pathlib import Path

from foss_audit import progress
from foss_audit.model import Item


def item(name: str, source: str = "aur") -> Item:
    return Item(name=name, source=source, verdict="foss")  # type: ignore[arg-type]


def one_item() -> list[Item]:
    return [item("fast")]


def slow_item() -> list[Item]:
    time.sleep(0.6)
    return [item("slow")]


def failing() -> list[Item]:
    raise RuntimeError("expac missing")


def crashing() -> list[Item]:
    os._exit(3)


def ticker(gate: str) -> list[Item]:
    """Report 2 of 4, wait for the gate file to appear, then finish."""
    counter = progress.counter("ticker")
    counter.add_total(4)
    time.sleep(0.3)
    counter.advance(2)
    deadline = time.monotonic() + 30
    while not Path(gate).exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    counter.advance(2)
    return [item("tick-a"), item("tick-b")]


STORES = 40


def store_many(cache_file: str, tag: str) -> None:
    """Child process: write STORES distinct upstream-license entries into `cache_file`."""
    from foss_audit import upstream_license

    upstream_license.CACHE_FILE = Path(cache_file)
    for n in range(STORES):
        upstream_license._store(f"{tag}{n}", "MIT", "checked")
