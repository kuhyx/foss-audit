"""Steam appinfo.vdf EULA reader."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest
from vdf_builder import V28, V29, Builder, eula_app

from foss_audit.steam_appinfo import Eula, eulas_for

URL = "https://store.steampowered.com//eula/7_eula_0"


@pytest.mark.parametrize("magic", [V28, V29])
def test_reads_only_wanted_apps(tmp_path: Path, magic: int) -> None:
    other = eula_app(9, ("Other EULA", "https://example.com/9"))
    odd = {"f": b"\x03" + b"\0" * 4, "u": b"\x07" + b"\0" * 8, "i": b"\x0a" + b"\0" * 8}
    apps = {9: other, 7: eula_app(7, ("Game EULA", URL)) | odd, 5: {"appinfo": {"appid": 5}}}
    path = tmp_path / "appinfo.vdf"
    path.write_bytes(Builder(magic).file(apps))
    assert eulas_for({7, 5}, path) == {7: [Eula("7_eula_0", "Game EULA", URL)], 5: []}


@pytest.mark.parametrize(
    "tree",
    [
        {"appinfo": "flat"},
        {"appinfo": {"common": "flat"}},
        {"appinfo": {"common": {"eulas": "flat"}}},
        {"appinfo": {"common": {"eulas": {"0": "flat", "1": {"name": "no url"}}}}},
    ],
)
def test_odd_shapes_list_no_eulas(tmp_path: Path, tree: dict[str, object]) -> None:
    path = tmp_path / "appinfo.vdf"
    path.write_bytes(Builder().file({7: tree}))
    assert eulas_for({7}, path) == {7: []}


def test_unreadable_cache_means_no_eulas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "appinfo.vdf"
    monkeypatch.setattr("foss_audit.steam_appinfo.APPINFO", path)
    assert eulas_for({7}) == {}  # missing
    path.write_bytes(struct.pack("<II", 0x07564427, 1))
    assert eulas_for({7}) == {}  # unsupported version
    good = Builder().file({7: eula_app(7, ("Game EULA", URL))})
    path.write_bytes(good[:40])
    assert eulas_for({7}) == {}  # truncated
    path.write_bytes(Builder().file({7: {"appinfo": {"weird": b"\x05"}}}))
    assert eulas_for({7}) == {}  # unknown KeyValues type
