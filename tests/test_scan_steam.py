"""Steam manifests: Subscriber Agreement, EULAs, root LICENSE files, bundled parts."""

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
