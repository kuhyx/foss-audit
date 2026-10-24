"""Every non-cache source sets `removeCommand`; fixture homes only, never a live scan."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from userapp_helpers import write

from foss_audit import (
    scan_android,
    scan_desktop,
    scan_games,
    scan_misc,
    scan_python,
    scan_toolchain,
    scan_userapp,
)
from foss_audit.model import Item


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for module in (
        scan_misc,
        scan_games,
        scan_python,
        scan_toolchain,
        scan_userapp,
        scan_android,
        scan_desktop,
    ):
        monkeypatch.setattr(module, "HOME", tmp_path)
    return tmp_path


def commands(items: list[Item]) -> dict[str, tuple[str | None, str]]:
    assert [i.name for i in items if i.removeCommand is None] == []
    return {i.name: (i.removeCommand, i.removeVia) for i in items}


def foreign_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend root owns every path (the real /opt), so commands need sudo."""
    monkeypatch.setattr(os, "getuid", lambda: -1)


def test_conda_package_removed_from_its_env(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bare, full = home / "opt/miniconda3", home / "mc"
    monkeypatch.setattr(scan_python, "CONDA_ROOTS", (bare, full))
    write(bare / "conda-meta/ca-certificates.json", json.dumps({"name": "ca-certificates"}))
    write(bare / "envs/my env/conda-meta/numpy.json", json.dumps({"name": "numpy", "license": "BSD"}))
    write(full / "bin/conda", "#!/bin/sh\n")
    write(full / "conda-meta/python.json", json.dumps({"name": "python", "license": "Python-2.0"}))
    by = commands(scan_python.scan_conda())
    # No conda binary in the root (bin/ was removed): micromamba works on any prefix.
    assert by["ca-certificates [base]"] == ("micromamba remove -p ~/opt/miniconda3 ca-certificates", "")
    assert by["numpy [my env]"] == ("micromamba remove -p ~/'opt/miniconda3/envs/my env' numpy", "")
    assert by["python [base]"] == ("~/mc/bin/conda remove -n base python", "")
    foreign_owner(monkeypatch)
    assert (
        commands(scan_python.scan_conda())["python [base]"][0] == "sudo ~/mc/bin/conda remove -n base python"
    )


def test_appimage_opt_wine_waydroid(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write(home / ".joplin/Joplin.AppImage", "")
    assert commands(scan_misc.scan_appimages()) == {"Joplin": ("rm ~/.joplin/Joplin.AppImage", "")}
    opt = home / "opt"
    (opt / "YouTube Music").mkdir(parents=True)
    monkeypatch.setattr(scan_misc, "OPT_ROOT", opt)
    monkeypatch.setattr(scan_misc, "owned_by_pacman", lambda _: set())
    assert commands(scan_misc.scan_opt()) == {"YouTube Music": ("rm -rf ~/'opt/YouTube Music'", "")}
    prefix = home / ".wine/drive_c"
    monkeypatch.setattr(scan_games, "WINE_PREFIX", prefix)
    (prefix / "Program Files/Vendor/Suite/Product").mkdir(parents=True)
    assert commands(scan_games.scan_wine()) == {
        "Product": (
            "rm -rf ~/'.wine/drive_c/Program Files/Vendor/Suite/Product'",
            "files only; Wine's uninstall registry entry stays",
        )
    }
    image = write(home / "var/lib/waydroid/images/system.img", "")
    monkeypatch.setattr(scan_games, "WAYDROID_IMAGE", image)
    stop = "sudo systemctl stop waydroid-container && sudo rm -rf ~/var/lib/waydroid"
    via = "image, overlay and Android user data; the waydroid package stays"
    assert commands(scan_games.scan_waydroid()) == {"LineageOS (Waydroid)": (stop, via)}
    (home / ".local/share/waydroid").mkdir(parents=True)
    assert scan_games.scan_waydroid()[0].removeCommand == f"{stop} ~/.local/share/waydroid"
    foreign_owner(monkeypatch)
    assert scan_misc.scan_opt()[0].removeCommand == "sudo rm -rf ~/'opt/YouTube Music'"


def test_toolchain_families(home: Path) -> None:
    write(home / ".rustup/toolchains/1.77.2-x86_64-unknown-linux-gnu/bin/rustc", "")
    write(home / ".rustup/toolchains/stable-x86_64-unknown-linux-gnu/bin/rustc", "")
    write(home / ".pyenv/versions/3.12.8/bin/python", "")
    write(home / ".pyenv/versions/3.9.1/bin/python", "")
    (home / ".nvm/versions/node/v20.1.0").mkdir(parents=True)
    (home / ".nvm/versions/node/v22.2.0").mkdir(parents=True)
    (home / "sdk/fvm/versions/3.24.0").mkdir(parents=True)
    write(home / "sdk/go/bin/go", "")
    by = commands(scan_toolchain.scan_toolchains())
    assert by == {
        "rust (rustup)": (
            "rustup toolchain uninstall 1.77.2-x86_64-unknown-linux-gnu stable-x86_64-unknown-linux-gnu",
            "",
        ),
        "python (pyenv)": ("pyenv uninstall -f 3.9.1 3.12.8", ""),
        "node (nvm)": ("rm -rf ~/.nvm/versions/node/v20.1.0 ~/.nvm/versions/node/v22.2.0", ""),
        "flutter (fvm)": ("rm -rf ~/sdk/fvm/versions/3.24.0", ""),
        "go": ("rm -rf ~/sdk/go", ""),
    }


def test_user_app_specials(home: Path) -> None:
    share = home / ".local/share"
    write(share / "godot/export_templates/4.7.2.stable/linux_release.x86_64")
    runner = home / "services/actions-runner/aseprite-mcp"
    write(runner / "bin/Runner.Listener")
    write(share / "mangatl/llama.cpp/build/bin/llama-server")
    write(home / "sdk/Android/Sdk/platform-tools/adb")
    by = commands(scan_userapp.scan_user_apps())
    assert by["godot export templates"] == (f"rm -rf {share / 'godot/export_templates'}", "")
    deregister = "deregister it on GitHub too: config.sh remove --token <token>"
    assert by["github actions-runner"] == (f"rm -rf {runner.parent}", deregister)
    assert by["llama.cpp (llama-server)"] == (f"rm -rf {share / 'mangatl/llama.cpp'}", "")
    assert by["android-sdk"] == (f"rm -rf {home / 'sdk/Android/Sdk'}", "")
    write(runner / ".service", "actions.runner.kuhyx-aseprite-mcp.service\n")
    write(home / "sdk/Android/Sdk/licenses/android-sdk-license", "hash\n")
    by = commands(scan_userapp.scan_user_apps())
    assert by["github actions-runner"] == (
        f"(cd {runner} && sudo ./svc.sh uninstall) && rm -rf {runner.parent}",
        deregister,
    )
    assert by["android-sdk"] == (f"rm -rf {home / 'sdk/Android/Sdk'}", "")


def test_desktop_target_and_launcher(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scan_desktop, "SYSTEM_DIRS", (home / "none",) * 3)
    monkeypatch.setattr(scan_desktop, "SYSTEM_COVERED", ())
    monkeypatch.setattr(scan_desktop, "owned_by_pacman", lambda _: set())
    target = write(home / "sdk/fx/firefox-bin", "#!/bin/sh\n")
    launcher = write(home / ".local/share/applications/fx.desktop", "")
    launcher.write_text(f"[Desktop Entry]\nType=Application\nName=Fx\nExec={target} %u\n")
    write(target.parent / "LICENSE", "MIT License\n\nPermission is hereby granted, free of charge\n", 0o644)
    via = "the program and its launcher; files beside it stay"
    assert commands(scan_desktop.scan_desktop()) == {"Fx": (f"rm '{target}' '{launcher}'", via)}
    (target.parent / "LICENSE").unlink()
    assert commands(scan_desktop.scan_desktop())["Fx"][0] == f"rm '{target}' '{launcher}'"
