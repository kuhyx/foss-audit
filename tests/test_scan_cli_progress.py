"""`python -m foss_audit.scan --progress`: status lines on stderr."""

from __future__ import annotations

import io
import threading

import pytest

from foss_audit import progress, scan


def snapshot(running: list[dict[str, object]]) -> dict[str, object]:
    return {"sourcesDone": 14, "sourcesTotal": 26, "itemsFound": 9120, "running": running}


def test_progress_line_names_running_sources() -> None:
    assert scan.progress_line(snapshot([])) == "[14/26] 9120 items"
    running = [
        {"source": "npm-cache", "done": 3400, "total": 12000},
        {"source": "pip-cache", "done": 5, "total": None},
    ]
    assert scan.progress_line(snapshot(running)) == (
        "[14/26] 9120 items; npm-cache 3400/12000, pip-cache 5/?"
    )


def test_report_progress_prints_changes_only_then_a_final_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scan, "PROGRESS_INTERVAL_S", 0.01)
    state = progress.ScanProgress()
    state.begin(2)
    out = io.StringIO()
    stop = threading.Event()
    thread = threading.Thread(target=scan.report_progress, args=(state, stop, out))
    thread.start()
    state.started("a")
    state.advanced("a", 1, 2)
    while "a 1/2" not in out.getvalue():
        stop.wait(0.01)
    stop.wait(0.05)  # several polls with nothing new
    state.finished("a", 3)
    stop.set()
    thread.join()
    lines = out.getvalue().splitlines()
    assert lines.count("[0/2] 0 items; a 1/2") == 1
    assert lines[-1] == "[1/2] 3 items"


def test_main_with_progress_writes_to_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_scan(progress: progress.ScanProgress) -> dict[str, object]:
        progress.begin(1)
        return {"items": [], "errors": [], "durationMs": 1}

    monkeypatch.setattr(scan, "run_scan", fake_scan)
    scan.main(["--summary", "--progress"])
    captured = capsys.readouterr()
    assert captured.out.startswith("0 items in 1 ms")
    assert captured.err.strip() == "[0/1] 0 items"
