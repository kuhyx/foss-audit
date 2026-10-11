"""pacman/AUR scanner, with subprocess faked out."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from foss_audit import scan_pacman
from foss_audit.scan_pacman import owned_by_pacman, parse_expac


def fake_run(outputs: dict[str, tuple[int, str, str]]) -> Any:
    """subprocess.run stand-in keyed by the command's first two words."""

    def run(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        code, out, err = outputs[" ".join(cmd[:2])]
        return subprocess.CompletedProcess(cmd, code, out, err)

    return run


def test_parse_expac_sets_source_flags_and_own() -> None:
    lines = [
        "vim\t9.1-1\tVim\thttps://vim.org\t",
        "yay\t12-1\tGPL-3.0-or-later\thttps://github.com/Jguer/yay\t",
        "todo-flutter\t1-1\tcustom\thttps://github.com/kuhyx/todo\t",
        "zlib\t1.3-1\tZlib\thttps://zlib.net\tvim|yay",
        "lonely",
    ]
    items = parse_expac(lines, explicit={"vim", "yay"}, foreign={"yay", "todo-flutter"}, orphans={"zlib"})
    by = {i.name: i for i in items}
    assert by["yay"].source == "aur"
    assert by["vim"].explicit
    assert not by["zlib"].explicit
    assert by["zlib"].orphan
    assert by["zlib"].requiredBy == ["vim", "yay"]
    assert by["todo-flutter"].verdict == "own"
    assert by["vim"].removeCommand == "sudo pacman -Rns vim"
    assert by["lonely"].version is None
    assert by["lonely"].url is None


def test_scan_runs_all_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        fake_run(
            {
                "expac -Q": (0, "vim\t9\tVim\t\t\nzlib\t1\tZlib\t\tvim\n", ""),
                "pacman -Qqe": (0, "vim\n", ""),
                "pacman -Qqm": (0, "", ""),
                "pacman -Qdtq": (1, "", ""),  # exit 1 = no orphans, not an error
            },
        ),
    )
    items = scan_pacman.scan()
    assert [i.name for i in items] == ["vim", "zlib"]


def test_scan_raises_on_real_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", fake_run({"expac -Q": (2, "", "database locked")}))
    with pytest.raises(RuntimeError, match="database locked"):
        scan_pacman.scan()


def test_owned_by_pacman(monkeypatch: pytest.MonkeyPatch) -> None:
    assert owned_by_pacman([]) == set()
    monkeypatch.setattr(
        subprocess,
        "run",
        fake_run({"pacman -Qqo": (1, "cuda\n", "error: No package owns /opt/x\n")}),
    )
    assert owned_by_pacman(["/opt/cuda", "/opt/x"]) == {"/opt/cuda"}
