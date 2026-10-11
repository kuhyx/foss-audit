"""Steam, Wine and Waydroid scanners."""

from __future__ import annotations

from pathlib import Path

import pytest

from foss_audit import scan_misc

ACF = '"AppState"\n{\n\t"appid"\t\t"2400160"\n\t"name"\t\t"Glyphica"\n\t"buildid"\t\t"42"\n}\n'


def test_steam_manifests(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "appmanifest_2400160.acf").write_text(ACF)
    (tmp_path / "appmanifest_1.acf").write_text("garbage")
    monkeypatch.setattr(scan_misc, "STEAM_APPS", tmp_path)
    by = {i.name: i for i in scan_misc.scan_steam()}
    game = by["Glyphica"]
    assert (game.version, game.verdict) == ("42", "nonfree")
    assert game.removeCommand == "steam steam://uninstall/2400160"
    assert "appmanifest_1" in by


def test_wine_two_levels_and_stock_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pf = tmp_path / "Program Files"
    (pf / "IBM/ILOG/CPLEX_Studio2211/deep/er").mkdir(parents=True)
    (pf / "IBM/readme.txt").write_text("")
    (pf / "Vendor").mkdir()  # no products: the vendor itself is the item
    (pf / "Common Files/x").mkdir(parents=True)
    monkeypatch.setattr(scan_misc, "WINE_PREFIX", tmp_path)
    items = scan_misc.scan_wine()
    assert [i.name for i in items] == ["CPLEX_Studio2211", "Vendor"]
    assert items[0].reason == "Program Files/IBM/ILOG/CPLEX_Studio2211"


def test_waydroid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image = tmp_path / "system.img"
    monkeypatch.setattr(scan_misc, "WAYDROID_IMAGE", image)
    assert scan_misc.scan_waydroid() == []
    image.write_text("")
    assert scan_misc.scan_waydroid()[0].name == "LineageOS (Waydroid)"
