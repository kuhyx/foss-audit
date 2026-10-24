"""Wine and Waydroid scanners (Steam: test_scan_steam.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from foss_audit import scan_games


def test_wine_two_levels_and_stock_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pf = tmp_path / "Program Files"
    (pf / "IBM/ILOG/CPLEX_Studio2211/deep/er").mkdir(parents=True)
    (pf / "IBM/readme.txt").write_text("")
    (pf / "Vendor").mkdir()  # no products: the vendor itself is the item
    (pf / "Common Files/x").mkdir(parents=True)
    monkeypatch.setattr(scan_games, "WINE_PREFIX", tmp_path)
    items = scan_games.scan_wine()
    assert [i.name for i in items] == ["CPLEX_Studio2211", "Vendor"]
    assert items[0].reason == "Program Files/IBM/ILOG/CPLEX_Studio2211"


def test_waydroid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image = tmp_path / "system.img"
    monkeypatch.setattr(scan_games, "WAYDROID_IMAGE", image)
    assert scan_games.scan_waydroid() == []
    image.write_text("")
    assert scan_games.scan_waydroid()[0].name == "LineageOS (Waydroid)"
