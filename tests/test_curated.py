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


def test_real_file_has_pip_cache_cuda_alternatives() -> None:
    real = Curated.load()
    alt = real.alternative_for(Item(name="cuda-bindings", source="pip-cache", verdict="nonfree"))
    assert alt is not None
    assert "python-pytorch" in alt["candidates"]
    # onlySource keeps the pip-cache research off any other source.
    assert real.alternative_for(Item(name="cuda-bindings", source="pip-user", verdict="nonfree")) is None


CUDA_WHEELS = (
    "cuda-bindings", "cuda-toolkit", "nvidia-cublas", "nvidia-cublas-cu12", "nvidia-cuda-cccl",
    "nvidia-cuda-cupti", "nvidia-cuda-cupti-cu12", "nvidia-cuda-nvrtc", "nvidia-cuda-nvrtc-cu12",
    "nvidia-cuda-runtime", "nvidia-cuda-runtime-cu12", "nvidia-cudnn-cu12", "nvidia-cudnn-cu13",
    "nvidia-cufft", "nvidia-cufft-cu12", "nvidia-cufile", "nvidia-cufile-cu12", "nvidia-curand",
    "nvidia-curand-cu12", "nvidia-cusolver", "nvidia-cusolver-cu12", "nvidia-cusparse",
    "nvidia-cusparse-cu12", "nvidia-cusparselt-cu12", "nvidia-cusparselt-cu13", "nvidia-nccl-cu12",
    "nvidia-nccl-cu13", "nvidia-nvjitlink", "nvidia-nvjitlink-cu12", "nvidia-nvshmem-cu12",
    "nvidia-nvshmem-cu13", "nvidia-nvtx",
)  # fmt: skip


def test_real_file_curates_every_cuda_wheel() -> None:
    real = Curated.load()
    assert len(CUDA_WHEELS) == 32
    for name in CUDA_WHEELS:
        alt = real.alternative_for(Item(name=name, source="pip-cache", verdict="nonfree"))
        assert alt is not None, name
        assert "python-pytorch" in alt["candidates"], name
        assert real.alternative_for(Item(name=name, source="pip-user", verdict="nonfree")) is None, name


def test_real_file_curates_proton_cachyos_native_as_ranked_partial() -> None:
    version = "cachyos-11.0-20261015-native"
    item = Item(name="proton-cachyos-native", source="steam", verdict="nonfree", version=version)
    apply([item], Curated.load())
    assert item.verdict == "foss-partial"
    assert "lsteamclient" in item.reason and "PROTONFIXES_DISABLE" in item.reason
    assert "LicenseRef-Steamworks-SDK" in item.license
    assert item.url == "https://github.com/CachyOS/proton-cachyos"
    assert item.alternative is not None
    assert (item.unranked, bool(item.fitRank), bool(item.effortRank)) == (False, True, True)


def test_real_file_steam_tools_carry_the_native_proton_proofs() -> None:
    real = Curated.load()
    proton = real.verdict_for("Proton Experimental")
    assert proton is not None and "lsteamclient/LICENSE" in proton[1]
    for name in ("Proton Experimental", "Steam Linux Runtime 4.0", "Steamworks Common Redistributables"):
        alt = real.alternative_for(Item(name=name, source="steam", verdict="nonfree"))
        assert alt is not None and "proton-cachyos-native" in alt["candidates"], name
    # The proof covers Steam Linux Runtime 4.0 only; scout and soldier serve native Linux games.
    scout = real.alternative_for(
        Item(name="Steam Linux Runtime 1.0 (scout)", source="steam", verdict="nonfree")
    )
    assert scout is not None and "proton-cachyos-native" not in scout["candidates"]
    assert scout["effort"] == "L"
    scout_verdict = real.verdict_for("Steam Linux Runtime 1.0 (scout)")
    assert scout_verdict is not None and "4183110" not in scout_verdict[1]
    steamcmd = real.alternative_for(Item(name="steamcmd", source="aur", verdict="nonfree"))
    assert steamcmd is not None and "not needed" in steamcmd["effortReason"]
    steam = real.verdict_for("steam")
    assert steam is not None and "VAC" in steam[1]
