"""Launchers a service-PATH scan misreads: ~/.local/bin targets and dead Chrome web apps."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_scan_desktop import apps, desktop, fake_owned, program

from foss_audit import scan_desktop


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(scan_desktop, "HOME", tmp_path)
    monkeypatch.setattr(scan_desktop, "SYSTEM_DIRS", (tmp_path / "s1", tmp_path / "s2", tmp_path / "s3"))
    monkeypatch.setattr(scan_desktop, "SYSTEM_COVERED", (tmp_path / "usr/bin",))
    monkeypatch.setattr(scan_desktop, "owned_by_pacman", fake_owned)
    return tmp_path


def test_local_bin_target_resolves_without_it_on_path(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The systemd service runs with PATH=/usr/local/bin:/usr/bin, no ~/.local/bin.
    monkeypatch.setenv("PATH", "/nonexistent")
    target = program(home / ".local/bin/sickdays")
    desktop(apps(home) / "sickdays.desktop", "sickdays gui", "Sick days")
    assert scan_desktop.locate("sickdays") == target
    assert scan_desktop.scan_desktop() == []  # covered by the local-bin/pip-user items


def test_missing_command_is_still_dangling(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/nonexistent")
    assert scan_desktop.locate("sickdays") is None


def test_dead_chrome_web_app_is_a_stale_launcher_not_nonfree(home: Path) -> None:
    path = desktop(
        apps(home) / "chrome-lbikmagadijbjdijgbiafoipflnaekep-Default.desktop",
        "/usr/local/bin/helium-wrapper --profile-directory=Default --app-id=lbikmagadijbjdijgbiafoipflnaekep",
        "todoImplementer",
    )
    (item,) = scan_desktop.scan_desktop()
    assert (item.id, item.verdict, item.dangling) == ("desktop:todoImplementer", "foss", True)
    assert item.removeCommand == f"rm '{path}'"
    assert "web-app launcher" in item.note
    assert "/usr/local/bin/helium-wrapper" in item.note
    assert item.license == ""


def test_dead_plain_launcher_stays_unknown(home: Path) -> None:
    desktop(apps(home) / "x.desktop", "/gone/prog", "Prog")
    (item,) = scan_desktop.scan_desktop()
    assert (item.verdict, item.dangling) == ("nonfree", True)
