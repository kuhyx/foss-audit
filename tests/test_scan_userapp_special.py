"""The special-cased installs (gh Copilot, Android SDK, Prism, Proton, Godot, runner, llama.cpp)."""

from __future__ import annotations

from pathlib import Path

import pytest
from userapp_helpers import GPL2, MIT, by_name, write

from foss_audit import scan_userapp
from foss_audit.curated import Curated, apply


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(scan_userapp, "HOME", tmp_path)
    (tmp_path / ".local/share").mkdir(parents=True)
    return tmp_path


def test_gh_copilot(home: Path) -> None:
    base = home / ".local/share/gh"
    assert scan_userapp.scan_gh_copilot() == []
    write(base / "copilot/copilot")
    (item,) = scan_userapp.scan_gh_copilot()
    assert (item.name, item.verdict, item.version) == ("gh-copilot", "nonfree", None)
    write(base / "extensions/gh-copilot/manifest.yml", "owner: github\ntag: v1.1.0\n", 0o600)
    assert scan_userapp.scan_gh_copilot()[0].version == "1.1.0"
    write(base / "extensions/gh-copilot/manifest.yml", "owner: github\n", 0o600)
    assert scan_userapp.scan_gh_copilot()[0].version is None


def test_android_sdk(home: Path) -> None:
    sdk = home / "sdk/Android/Sdk"
    assert scan_userapp.scan_android_sdk() == []
    sdk.mkdir(parents=True)
    (item,) = scan_userapp.scan_android_sdk()
    assert (item.verdict, item.license, item.reason) == (
        "nonfree",
        "",
        "~/sdk/Android/Sdk; no SDK license accepted",
    )
    write(sdk / "licenses/android-sdk-license", "abc\n", 0o644)
    write(sdk / "licenses/google-gdk-license", "def\n", 0o644)
    (item,) = scan_userapp.scan_android_sdk()
    assert (item.verdict, item.license) == ("nonfree", "LicenseRef-Android-SDK-License")
    assert "Android SDK License accepted (android-sdk-license, google-gdk-license)" in item.reason


def test_prism_java_runtimes(home: Path) -> None:
    java = home / ".local/share/PrismLauncher/java"
    assert scan_userapp.scan_prism_java() == []
    write(java / "temurin/release", 'JAVA_VERSION="21.0.7"\nIMPLEMENTOR="Eclipse Adoptium"\n', 0o644)
    write(java / "mojang/release", 'JAVA_VERSION="17.0.15"\n', 0o644)
    write(java / "mojang/legal/java.base/LICENSE", GPL2, 0o644)
    write(java / "stray-file", "x", 0o644)
    (item,) = scan_userapp.scan_prism_java()
    assert (item.name, item.verdict, item.license) == (
        "PrismLauncher java runtimes",
        "foss",
        "GPL-2.0 WITH Classpath-exception-2.0",
    )
    assert item.version == "17.0.15, 21.0.7"
    assert item.reason == "OpenJDK builds: mojang 17.0.15, temurin 21.0.7"
    assert item.removeCommand == f"rm -rf {java}"
    # A runtime with neither a free vendor nor a GPL text, and no release file.
    (java / "odd").mkdir()
    (item,) = scan_userapp.scan_prism_java()
    assert (item.verdict, item.license, item.version) == ("nonfree", "", "17.0.15, 21.0.7, ?")
    assert "odd ?" in item.reason
    assert item.reason.endswith("not recognisably OpenJDK")


def test_proton_tools(home: Path) -> None:
    tools = home / ".local/share/Steam/compatibilitytools.d"
    assert scan_userapp.scan_proton_tools() == []
    write(tools / "GE-Proton11-7/LICENSE", "Redistribution and use in source and binary forms\n", 0o644)
    write(tools / "GE-Proton11-7/LICENSE.OFL", "SIL Open Font License\n", 0o644)
    write(tools / "NoLicense/proton", "x")
    write(tools / "stray.txt", "x", 0o644)
    items = by_name(scan_userapp.scan_proton_tools())
    assert sorted(items) == ["GE-Proton11-7", "NoLicense"]
    assert (items["GE-Proton11-7"].verdict, items["GE-Proton11-7"].license) == ("foss", "BSD")
    assert items["NoLicense"].verdict == "nonfree"


def test_godot_export_templates(home: Path) -> None:
    root = home / ".local/share/godot/export_templates"
    assert scan_userapp.scan_godot_templates() == []
    write(root / "4.6.stable/version.txt", "4.6.stable\n", 0o644)
    write(root / "4.7.2.stable/version.txt", "4.7.2.stable\n", 0o644)
    (item,) = scan_userapp.scan_godot_templates()
    assert (item.name, item.verdict, item.version) == (
        "godot export templates",
        "nonfree",
        "4.6.stable, 4.7.2.stable",
    )
    write(root / "4.7.2.stable/LICENSE.txt", MIT, 0o644)
    assert scan_userapp.scan_godot_templates()[0].license == "MIT"


def test_actions_runner(home: Path) -> None:
    root = home / "services/actions-runner"
    assert scan_userapp.scan_actions_runner() == []
    (root / "empty").mkdir(parents=True)
    assert scan_userapp.scan_actions_runner() == []
    write(root / "repo-a/bin.2.337.0/Runner.Listener")
    (root / "repo-a/bin").symlink_to(root / "repo-a/bin.2.337.0")
    (item,) = scan_userapp.scan_actions_runner()
    assert (item.name, item.verdict, item.version) == ("github actions-runner", "nonfree", "2.337.0")
    write(root / "repo-a/bin.2.337.0/LICENSE", MIT, 0o644)
    assert scan_userapp.scan_actions_runner()[0].license == "MIT"
    # A plain `bin` directory carries no version in its name.
    write(root / "repo-b/bin/Runner.Listener")
    assert scan_userapp.scan_actions_runner()[0].version is None


def test_llama_cpp(home: Path) -> None:
    root = home / ".local/share/mangatl/llama.cpp"
    assert scan_userapp.scan_llama_cpp() == []
    write(root / "build/bin/llama-cli")
    assert scan_userapp.scan_llama_cpp() == []
    write(root / "build/bin/llama-server")
    write(root / "LICENSE", MIT, 0o644)
    (item,) = scan_userapp.scan_llama_cpp()
    assert (item.name, item.verdict, item.license) == ("llama.cpp (llama-server)", "foss", "MIT")
    # mangatl itself is not an item, whoever owns it.
    write(home / ".local/share/mangatl/venv/bin/python")
    assert [i.name for i in scan_userapp.scan_user_apps()] == ["llama.cpp (llama-server)"]


def test_curated_verdicts_for_unlicensed_installs(home: Path) -> None:
    share = home / ".local/share"
    write(share / "GitKrakenCLI/gk")
    write(share / "Blender Launcher/blenderlauncher")
    write(share / "Tachidesk/bin/kcef/cef_server")
    write(share / "gh/copilot/copilot")
    write(home / "sdk/Android/Sdk/licenses/android-sdk-license", "abc\n", 0o644)
    write(share / "godot/export_templates/4.7.2.stable/version.txt", "4.7.2.stable\n", 0o644)
    write(home / "services/actions-runner/a/bin/Runner.Listener")
    write(
        share / "Steam/compatibilitytools.d/GE-Proton11-7/LICENSE",
        "Redistribution and use in source and binary forms\n",
        0o644,
    )
    items = by_name(apply(scan_userapp.scan_user_apps(), Curated.load()))
    verdicts = {name: item.verdict for name, item in items.items()}
    assert verdicts == {
        "GitKrakenCLI": "nonfree",
        "Blender Launcher": "foss",
        "Tachidesk": "foss",
        "gh-copilot": "nonfree",
        "android-sdk": "nonfree",
        "GE-Proton11-7": "foss",
        "godot export templates": "foss",
        "github actions-runner": "foss",
    }
    assert items["android-sdk"].reason.startswith("Android SDK License")
    assert items["godot export templates"].license == "MIT"
    assert items["github actions-runner"].license == "MIT"
    assert "GPL-3.0" in items["Blender Launcher"].license
    for name in ("GitKrakenCLI", "gh-copilot", "android-sdk"):
        assert items[name].alternative is not None
