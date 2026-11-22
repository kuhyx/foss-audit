"""Steam manifests (Subscriber Agreement, EULAs, root LICENSE files, bundled parts) and compat tools."""

from __future__ import annotations

from pathlib import Path

import pytest
from vdf_builder import Builder, eula_app

from foss_audit import scan_steam, steam_appinfo

MIT = "Permission is hereby granted, free of charge, to any person...\n"
BSD = "Copyright Valve. All rights reserved.\nRedistribution and use in source and binary forms\n"


def acf(appid: str, name: str, installdir: str | None) -> str:
    install = f'\t"installdir"\t\t"{installdir}"\n' if installdir else ""
    return f'"AppState"\n{{\n\t"appid"\t\t"{appid}"\n\t"name"\t\t"{name}"\n\t"buildid"\t\t"42"\n{install}}}\n'


@pytest.fixture
def steam(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(scan_steam, "STEAM_APPS", tmp_path)
    monkeypatch.setattr(steam_appinfo, "APPINFO", tmp_path / "appinfo.vdf")
    monkeypatch.setattr(scan_steam, "COMPAT_TOOLS", tmp_path / "compatibilitytools.d")
    return tmp_path


def test_licenses_eula_and_bundled_parts(steam: Path) -> None:
    (steam / "appmanifest_7.acf").write_text(acf("7", "Game", "Game"))
    (steam / "appmanifest_8.acf").write_text(acf("8", "Proton", "Proton"))
    (steam / "appmanifest_9.acf").write_text(acf("9", "Gone", "Gone"))
    (steam / "appmanifest_1.acf").write_text("garbage")
    url = "https://store.steampowered.com//eula/7_eula_0"
    (steam / "appinfo.vdf").write_bytes(Builder().file({7: eula_app(7, ("Game EULA", url))}))
    game = steam / "common/Game"
    (game / "licenses/sub").mkdir(parents=True)
    (game / "licenses/allegro.txt").write_text(BSD)
    (game / "licenses/fonts.txt").write_text("Fonts under the SIL Open Font License")
    (game / "licenses/icons.txt").write_text("Icons licensed under CC BY 4.0.")
    (game / "licenses/blob.txt").write_text("Proprietary. All rights reserved.")
    (game / "data").mkdir()
    proton = steam / "common/Proton"
    proton.mkdir(parents=True)
    (proton / "LICENSE").write_text(BSD + "Wine: Mozilla Public License\n")
    (proton / "LICENSE.OFL").write_text("SIL Open Font License\n" + MIT)
    (proton / "LICENSE.custom").write_text("Do what you like\n")
    (proton / "licenses").mkdir()
    (proton / "files").mkdir()
    by = {i.name: i for i in scan_steam.scan_steam()}
    assert set(by) == {"Game", "Proton", "Gone", "appmanifest_1"}
    g = by["Game"]
    assert (g.version, g.verdict, g.removeCommand) == ("42", "nonfree", "steam steam://uninstall/7")
    assert g.license == "LicenseRef-Steam-Subscriber-Agreement LicenseRef-EULA-7"
    assert g.note == (
        "EULA: Game EULA <https://store.steampowered.com/eula/7_eula_0>; bundled components: "
        "BSD: allegro; OFL-1.1: fonts; not free: blob; other free: icons"
    )
    assert by["Proton"].license == "LicenseRef-Steam-Subscriber-Agreement BSD OFL-1.1"
    assert by["Proton"].note == ""
    assert (by["Gone"].license, by["Gone"].note) == ("LicenseRef-Steam-Subscriber-Agreement", "")
    assert by["appmanifest_1"].license == "LicenseRef-Steam-Subscriber-Agreement"


def test_no_manifests_skips_the_cache(steam: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_: set[int]) -> None:
        raise AssertionError("cache read without apps")

    monkeypatch.setattr(scan_steam, "eulas_for", boom)
    assert scan_steam.scan_steam() == []


def test_compat_tools_are_steam_items(steam: Path) -> None:
    tools = steam / "compatibilitytools.d"
    (tools / "GE-Proton11-7/licenses").mkdir(parents=True)
    (tools / "GE-Proton11-7/LICENSE").write_text(BSD)
    (tools / "GE-Proton11-7/LICENSE.OFL").write_text("SIL Open Font License\n")
    (tools / "GE-Proton11-7/licenses/fonts.txt").write_text("Fonts under the SIL Open Font License")
    (tools / "GE-Proton11-7/version").write_text("1762000000 GE-Proton11-7\n")
    (tools / "proton-cachyos-native").mkdir()
    (tools / "proton-cachyos-native/version").write_text("cachyos-11.0-20261015-native\n")
    (tools / "bare").mkdir()
    (tools / "stray.txt").write_text("x")
    by = {i.id: i for i in scan_steam.scan_steam()}
    assert sorted(by) == ["steam:GE-Proton11-7", "steam:bare", "steam:proton-cachyos-native"]
    ge = by["steam:GE-Proton11-7"]
    assert (ge.verdict, ge.license, ge.version) == ("foss", "BSD OFL-1.1", "GE-Proton11-7")
    assert ge.reason == "Steam compatibility tool; LICENSE files: BSD, OFL-1.1"
    assert ge.note == "bundled components: OFL-1.1: fonts"
    assert ge.removeCommand == f"rm -rf {tools / 'GE-Proton11-7'}"
    cachy = by["steam:proton-cachyos-native"]
    assert (cachy.verdict, cachy.license, cachy.version) == ("nonfree", "", "cachyos-11.0-20261015-native")
    assert cachy.reason == "Steam compatibility tool; no license file shipped (proprietary unless curated)"
    assert (by["steam:bare"].version, by["steam:bare"].url) == (None, None)
