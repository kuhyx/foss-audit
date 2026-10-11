"""Curated verdict overrides and alternative attachment."""

from __future__ import annotations

import json
from pathlib import Path

from foss_audit.curated import CURATED_PATH, Curated, apply
from foss_audit.model import Item

ALT = {"names": ["Chromium"], "candidates": ["chromium", "firefox"], "fit": "drop-in", "effort": None}
ALT |= {"effortReason": "", "lockIn": ""}


def make_curated() -> Curated:
    return Curated(
        verdicts={
            "sudo": ["foss", "ISC"],
            "own-thing": ["nonfree", "should not apply"],
            "redist": ["nonfree", "Windows redistributables", "LicenseRef-MS"],
        },
        alternatives={
            "google-chrome": ALT,
            "Proton*": None,
            "*": ALT | {"names": ["FOSS games"], "onlySource": "steam"},
        },
    )


def test_verdict_override_and_own_is_protected() -> None:
    items = [
        Item(name="sudo", source="pacman", verdict="nonfree"),
        Item(name="own-thing", source="local-bin", verdict="foss", own=True),
    ]
    apply(items, make_curated())
    assert (items[0].verdict, items[0].reason, items[0].own) == ("foss", "ISC", False)
    assert items[1].verdict == "foss"


def test_alternative_attached_with_installed_candidates() -> None:
    items = [
        Item(name="google-chrome", source="aur", verdict="nonfree"),
        Item(name="Chromium", source="pacman", verdict="foss"),
    ]
    apply(items, make_curated())
    alt = items[0].alternative
    assert alt is not None
    assert alt.installed == ["chromium"]
    assert items[1].alternative is None  # free items never get one


def test_null_entry_blocks_broader_globs() -> None:
    proton = Item(name="Proton 9.0", source="steam", verdict="foss-partial")
    game = Item(name="Some Game", source="steam", verdict="nonfree")
    other = Item(name="mystery", source="aur", verdict="nonfree")
    apply([proton, game, other], make_curated())
    assert proton.alternative is None
    assert game.alternative is not None
    assert game.alternative.names == ["FOSS games"]
    assert other.alternative is None  # catch-all is steam-only


def test_load_reads_real_file(tmp_path: Path) -> None:
    real = Curated.load()
    assert real.verdict_for("google-chrome") is None
    assert real.alternative_for(Item(name="google-chrome", source="aur", verdict="nonfree"))
    custom = tmp_path / "c.json"
    custom.write_text(json.dumps({"verdicts": {"a*": ["foss", "x"]}, "alternatives": {}}))
    assert Curated.load(custom).verdict_for("abc") == ["foss", "x"]
    assert CURATED_PATH.name == "curated.json"


def test_item_json_has_id_first() -> None:
    data = Item(name="vim", source="pacman", verdict="foss").to_json()
    assert next(iter(data)) == "id"
    assert data["id"] == "pacman:vim"


def test_curated_license_is_appended_and_note_survives() -> None:
    items = [
        Item(name="redist", source="steam", verdict="nonfree", license="LicenseRef-SSA", note="EULA: x"),
        Item(name="sudo", source="pacman", verdict="nonfree", license="ISC"),
    ]
    apply(items, make_curated())
    assert items[0].license == "LicenseRef-SSA LicenseRef-MS"
    assert items[0].to_json()["reason"] == "Windows redistributables; EULA: x"
    assert "note" not in items[0].to_json()
    assert items[1].license == "ISC"
    assert Item(name="n", source="steam", verdict="nonfree", note="only").to_json()["reason"] == "only"
