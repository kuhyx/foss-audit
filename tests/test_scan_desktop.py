""".desktop launcher scanner: Exec resolution, coverage by other scanners, dangling launchers."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import make_repo

from foss_audit import scan_desktop
from foss_audit.curated import Curated, apply
from foss_audit.model import NO_LICENSE

MIT = "MIT License\n\nPermission is hereby granted, free of charge, to any person...\n"
CURATED = Curated.load()


def desktop(path: Path, exec_line: str | None, name: str | None = None, extra: str = "") -> Path:
    """Write a .desktop file; `exec_line` / `name` of None leave the key out."""
    lines = ["[Desktop Entry]", "Type=Application"]
    lines += [f"Name={name}"] if name is not None else []
    lines += [f"Exec={exec_line}"] if exec_line is not None else []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n" + extra)
    return path


def program(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def fake_owned(paths: list[str]) -> set[str]:
    """Stand-in for pacman: files named owned* belong to a package."""
    return {p for p in paths if Path(p).name.startswith("owned")}


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    system = tmp_path / "sys"
    monkeypatch.setattr(scan_desktop, "HOME", tmp_path)
    monkeypatch.setattr(
        scan_desktop,
        "SYSTEM_DIRS",
        (system / "share/applications", system / "local/applications", system / "flatpak/applications"),
    )
    monkeypatch.setattr(scan_desktop, "SYSTEM_COVERED", (system / "usr/bin", system / "opt"))
    monkeypatch.setattr(scan_desktop, "owned_by_pacman", fake_owned)
    return tmp_path


def apps(home: Path) -> Path:
    return home / ".local/share/applications"


def test_parse_desktop(tmp_path: Path) -> None:
    ok = desktop(tmp_path / "a.desktop", "/x/prog %U", "Prog", "Name[pl]=Prog PL\nName[pl]=dup\n")
    parsed = scan_desktop.parse_desktop(ok)
    assert parsed is not None
    assert (parsed.name, parsed.exec_line) == ("Prog", "/x/prog %U")
    nameless = scan_desktop.parse_desktop(desktop(tmp_path / "stem.desktop", "/x/prog"))
    assert nameless is not None
    assert nameless.name == "stem"
    bad = tmp_path / "bad.desktop"
    bad.write_text("orphan line without a section\n")
    assert scan_desktop.parse_desktop(bad) is None
    no_section = tmp_path / "other.desktop"
    no_section.write_text("[Other]\nExec=/x\n")
    assert scan_desktop.parse_desktop(no_section) is None
    link = tmp_path / "link.desktop"
    link.write_text("[Desktop Entry]\nType=Link\nURL=https://x\nExec=/x\n")
    assert scan_desktop.parse_desktop(link) is None
    assert scan_desktop.parse_desktop(desktop(tmp_path / "noexec.desktop", None)) is None
    assert scan_desktop.parse_desktop(desktop(tmp_path / "hid.desktop", "/x", extra="Hidden=true\n")) is None
    assert scan_desktop.parse_desktop(desktop(tmp_path / "vis.desktop", "/x", extra="Hidden=false\n"))


def test_launchers_user_dir_shadows_system(home: Path) -> None:
    desktop(apps(home) / "same.desktop", "/user/prog", "User copy")
    desktop(scan_desktop.SYSTEM_DIRS[0] / "same.desktop", "/sys/prog", "System copy")
    desktop(scan_desktop.SYSTEM_DIRS[0] / "other.desktop", "/sys/other", "Other")
    desktop(scan_desktop.SYSTEM_DIRS[2] / "flat.desktop", "/sys/flat", "Flat")
    (scan_desktop.SYSTEM_DIRS[0] / "broken.desktop").write_text("junk\n")
    names = [(ln.name, ln.exec_line) for ln in scan_desktop.launchers()]
    assert names == [("User copy", "/user/prog"), ("Other", "/sys/other"), ("Flat", "/sys/flat")]


@pytest.mark.parametrize(
    ("line", "command"),
    [
        ("/opt/app/run %U", "/opt/app/run"),
        ('"/opt/with space/run" --x', "/opt/with space/run"),
        ('env APPIMAGELAUNCHER_DISABLE=TRUE "/h/Joplin.AppImage" %u', "/h/Joplin.AppImage"),
        ('env "WINEPREFIX=/h/p" wine start x', "wine"),
        ("/usr/bin/env -i FOO=1 prog", "prog"),
        ("exec /opt/x", "/opt/x"),
        ('bash -c \'"$HOME/.local/share/mo2/broker.sh" "$@"\' arg0', "{home}/.local/share/mo2/broker.sh"),
        ("sh -c '${HOME}/run.sh'", "{home}/run.sh"),
        ("sh -c", "sh"),
        ("~/bin/tool", "{home}/bin/tool"),
        ("$UNSET/bin/tool", None),
        ("env FOO=1", None),
        ("", None),
        ("prog 'unbalanced", "prog"),
        ("python3 -u /opt/steampipe-gui/main.py", "/opt/steampipe-gui/main.py"),
        ("python3 -m http.server", "python3"),
        ("node -c app.js", "node"),
        ("python3", "python3"),
        ("python3 ~/x/main.py", "{home}/x/main.py"),
    ],
)
def test_exec_command(home: Path, line: str, command: str | None) -> None:
    assert scan_desktop.exec_command(line) == (command.format(home=home) if command else None)


def test_locate(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = program(home / "bin/tool")
    assert scan_desktop.locate(str(target)) == target
    assert scan_desktop.locate(str(home / "bin/missing")) is None
    monkeypatch.setattr(shutil, "which", lambda cmd: str(target) if cmd == "tool" else None)
    assert scan_desktop.locate("tool") == target
    assert scan_desktop.locate("ghost") is None


@pytest.mark.parametrize(
    ("line", "command", "other"),
    [
        ("steam steam://rungameid/1", "steam", True),
        ("/usr/bin/steam %U", "/usr/bin/steam", True),
        ("flatpak run org.x.App", "flatpak", True),
        ("waydroid app launch x", "waydroid", True),
        ("wine start x", "wine", True),
        ("steam://rungameid/9 %u", "steam://rungameid/9", True),
        ("xdg-open steam://rungameid/9", "xdg-open", True),
        ("/opt/winetricks-gui", "/opt/winetricks-gui", True),
        ("/opt/app/run", "/opt/app/run", False),
        ("/opt/stream-tool", "/opt/stream-tool", False),
    ],
)
def test_other_source(line: str, command: str, other: bool) -> None:
    assert scan_desktop.other_source(line, command) is other


def test_covered_elsewhere(home: Path) -> None:
    system = home / "sys"
    covered = [
        system / "usr/bin/x",
        system / "opt/app/run",
        home / ".local/bin/x",
        home / ".local/share/app/run",
        home / "Downloads/App.AppImage",
        home / "a/b/c.appimage",
    ]
    assert all(scan_desktop.covered_elsewhere(p) for p in covered)
    uncovered = [
        home / "a/b/c/d.AppImage",
        Path("/elsewhere/x.AppImage"),
        home / "sdk/firefox/firefox-bin",
        Path("/srv/app"),
    ]
    assert not any(scan_desktop.covered_elsewhere(p) for p in uncovered)


def test_is_kuhys(home: Path) -> None:
    mine = make_repo(home / "src/mine")
    theirs = make_repo(home / "src/theirs", remote="https://github.com/other/x.git")
    assert scan_desktop.is_kuhys(program(mine / "run.sh"))
    assert not scan_desktop.is_kuhys(program(theirs / "run.sh"))
    tracked = program(mine / "tools/copied-tool.sh")
    subprocess.run(["git", "init", "-q", str(mine)], check=True)
    subprocess.run(["git", "-C", str(mine), "add", "tools/copied-tool.sh"], check=True)
    assert scan_desktop.is_kuhys(program(home / "stray/copied-tool"))
    assert not scan_desktop.is_kuhys(program(home / "stray/other-tool"))
    assert tracked.exists()


def test_quote_and_names() -> None:
    assert scan_desktop.quote(Path("/h/it's.desktop")) == "'/h/it'\\''s.desktop'"
    plain = scan_desktop.Launcher(Path("/x/a.desktop"), "Plain", "/y")
    stub = scan_desktop.Launcher(Path("/x/b.desktop"), "Game 12345", "/y")
    assert scan_desktop.display_name(plain, "/opt/rpcs3") == "Plain"
    assert scan_desktop.display_name(stub, "/opt/rpcs3") == "rpcs3"


def test_scan_end_to_end(home: Path) -> None:
    system = home / "sys"
    sdk = program(home / "sdk/fx/firefox-bin")
    licensed = program(home / "opt2/licensed/bin/tool")
    (licensed.parent / "COPYING").write_text(MIT)
    owned = program(home / "sdk/owned-tool")
    mine = make_repo(home / "src/mine")
    program(mine / "app.sh")
    covered = program(system / "usr/bin/covered")
    desktop(apps(home) / "fx.desktop", f"{sdk} %u", "Firefox Beta")
    desktop(apps(home) / "lic.desktop", f"env A=1 {licensed}", "Licensed")
    desktop(apps(home) / "owned.desktop", str(owned), "Owned")
    desktop(apps(home) / "mine.desktop", str(mine / "app.sh"), "Mine")
    desktop(apps(home) / "cov.desktop", str(covered), "Covered")
    desktop(apps(home) / "steam.desktop", "steam steam://rungameid/1", "Some Game")
    desktop(apps(home) / "nocmd.desktop", "env A=1", "Nothing")
    desktop(apps(home) / "d1.desktop", "/opt/rpcs3/usr/bin/rpcs3 %u", "Game 424004941485572097")
    desktop(apps(home) / "d2.desktop", "/tmp/.mount_osu.Ab/usr/bin/osu! %u", "Game 1216669957799018608")
    desktop(apps(home) / "gale.desktop", f"{home}/Downloads/Gale_1.10.0_amd64.AppImage %u", "Gale")
    desktop(apps(home) / "gale2.desktop", "/gone/gale2", "Gale")
    desktop(apps(home) / "owned-pkg.desktop", "/nowhere/optional-dep", "From a package")
    desktop(apps(home) / "quote's.desktop", "ghost-command", "Ghost")
    items = {i.name: i for i in scan_desktop.scan_desktop()}
    assert sorted(items) == [
        "Firefox Beta",
        "Gale",
        "Gale (gale2)",
        "Ghost",
        "Licensed",
        "osu!",
        "rpcs3",
    ]
    fx = items["Firefox Beta"]
    assert (fx.source, fx.verdict, fx.dangling) == ("desktop", "nonfree", False)
    assert fx.removeCommand == f"rm '{sdk}' '{apps(home) / 'fx.desktop'}'"
    assert fx.reason == f"fx.desktop -> {sdk}; {NO_LICENSE}"
    lic = items["Licensed"]
    assert (lic.verdict, lic.license) == ("foss", "MIT")
    assert lic.reason == f"lic.desktop -> {licensed}"
    rpcs3 = items["rpcs3"]
    assert (rpcs3.dangling, rpcs3.verdict, rpcs3.id) == (True, "nonfree", "desktop:rpcs3")
    assert rpcs3.note == "launcher without target: /opt/rpcs3/usr/bin/rpcs3"
    assert rpcs3.removeCommand == f"rm '{apps(home) / 'd1.desktop'}'"
    assert items["Ghost"].note == "launcher without target: ghost-command"
    assert items["Ghost"].removeCommand == "rm '" + str(apps(home)) + "/quote'\\''s.desktop'"


def test_known_dead_launchers_are_curated(home: Path) -> None:
    desktop(apps(home) / "d1.desktop", "/opt/rpcs3/usr/bin/rpcs3 %u", "Game 424004941485572097")
    desktop(apps(home) / "d2.desktop", "/tmp/.mount_osu.Ab/usr/bin/osu! %u", "Game 1216669957799018608")
    desktop(apps(home) / "gale.desktop", f"{home}/Downloads/Gale_1.10.0_amd64.AppImage %u", "Gale")
    items = apply(scan_desktop.scan_desktop(), CURATED)
    got = {i.name: (i.verdict, i.license) for i in items}
    assert got == {
        "rpcs3": ("foss", "GPL-2.0"),
        "osu!": ("foss-partial", "MIT"),
        "Gale": ("foss", "GPL-3.0"),
    }
    assert all(i.dangling for i in items)
    json.dumps([i.to_json() for i in items])
