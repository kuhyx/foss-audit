"""The saved scan result: atomic writes and tolerant reads."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from foss_audit import scan_store


def write(path: Path, n: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"items": [], "n": n}))


def test_save_atomic_replaces_in_one_step_and_leaves_no_tmp(tmp_path: Path) -> None:
    store = tmp_path / "cache" / "scan.json"
    scan_store.save_atomic(store, {"items": [], "n": 1})  # creates the directory
    scan_store.save_atomic(store, {"items": [], "n": 2})
    assert json.loads(store.read_text())["n"] == 2
    assert [p.name for p in store.parent.iterdir()] == ["scan.json"]


def test_save_atomic_failure_keeps_the_old_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = tmp_path / "scan.json"
    write(store, 1)

    def broken(*_args: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken)
    with pytest.raises(OSError, match="disk full"):
        scan_store.save_atomic(store, {"items": [], "n": 2})
    assert json.loads(store.read_text())["n"] == 1
    assert [p.name for p in tmp_path.iterdir()] == ["scan.json"]


@pytest.mark.parametrize("content", [None, "{not json", "[1]", '{"no": "items"}'])
def test_load_saved_is_none_unless_a_scan_result(tmp_path: Path, content: str | None) -> None:
    store = tmp_path / "scan.json"
    if content is not None:
        store.write_text(content)
    assert scan_store.load_saved(store) is None


def test_load_saved_returns_the_result(tmp_path: Path) -> None:
    store = tmp_path / "scan.json"
    write(store, 5)
    assert scan_store.load_saved(store) == {"items": [], "n": 5}
