"""Scan the non-package-manager sources: npm, cargo, flatpak, AppImages, /opt,
~/.local/bin, Steam, Wine and Waydroid.

Most of these carry no license metadata, so they default to "nonfree" (no
license grant) and data/curated.json supplies the real verdict. Scripts are
traced to their pip distribution or their checkout's LICENSE instead.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from foss_audit.licenses import classify_text
from foss_audit.model import NO_LICENSE, Item
from foss_audit.own_license import license_for_path, origin_of, repo_root
from foss_audit.pnpm_shim import pnpm_item
from foss_audit.scan_pacman import owned_by_pacman
from foss_audit.scan_python import dist_license, script_owners

HOME = Path.home()
STEAM_APPS = HOME / ".local/share/Steam/steamapps"
WINE_PREFIX = HOME / ".wine/drive_c"
# Wine's own stub directories; anything else under Program Files is a real install.
WINE_STOCK = {
    "Common Files",
    "Internet Explorer",
    "Windows Media Player",
    "Windows NT",
    "Zero G Registry",
}
# Installers drop these into ~/.local/bin and they belong to another source.
OPT_ROOT = Path("/opt")
WAYDROID_IMAGE = Path("/var/lib/waydroid/images/system.img")
TOOL_ROOTS = (HOME / ".local/share/pipx", HOME / ".local/share/uv")
ACF_FIELD = re.compile(r'^\s*"(name|appid|buildid)"\s+"([^"]*)"', re.MULTILINE)


def unknown(name: str, source: str, **kw: object) -> Item:
    """An Item with no license evidence: nonfree until curated.json says otherwise."""
    kw.setdefault("reason", NO_LICENSE)
    return Item(name=name, source=source, verdict="nonfree", **kw)  # type: ignore[arg-type]


def scan_npm_global() -> list[Item]:
    """Global npm packages of the node first on PATH."""
    npm = shutil.which("npm")
    if not npm:
        return []
    root = Path(
        subprocess.run([npm, "root", "-g"], capture_output=True, text=True, check=True).stdout.strip()
    )
    items: list[Item] = []
    for pkg_json in sorted([*root.glob("*/package.json"), *root.glob("@*/*/package.json")]):
        pkg = pkg_json.parent
        if pkg.is_symlink():
            # `npm link` of a local project: kuhy's own tutorial/tool code.
            items.append(from_checkout(pkg.name, "npm-global", pkg_json.resolve(), "npm link"))
            continue
        data = json.loads(pkg_json.read_text())
        # Some packages (qwen-code) ship only a LICENSE file, no manifest field.
        lic = data.get("license") or license_for_path(pkg_json)[0]
        verdict, reason = classify_text(lic if isinstance(lic, str) else json.dumps(lic))
        items.append(
            Item(
                name=data.get("name", pkg.name),
                version=data.get("version"),
                source="npm-global",
                verdict=verdict,
                license=str(lic),
                reason=reason,
                url=data.get("homepage"),
                removeCommand=f"npm uninstall -g {data.get('name', pkg.name)}",
            ),
        )
    return items


def scan_cargo() -> list[Item]:
    """Crates installed with `cargo install` (license is not recorded locally)."""
    crates = HOME / ".cargo/.crates2.json"
    if not crates.is_file():
        return []
    installs = json.loads(crates.read_text()).get("installs", {})
    items = []
    for key in sorted(installs):
        name, version = key.split(" ")[:2]
        items.append(unknown(name, "cargo", version=version, removeCommand=f"cargo uninstall {name}"))
    return items


def scan_flatpak() -> list[Item]:
    """Flatpak applications (not runtimes)."""
    flatpak = shutil.which("flatpak")
    if not flatpak:
        return []
    out = subprocess.run(
        [flatpak, "list", "--app", "--columns=application,version"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    items = []
    for line in out.splitlines():
        app, _, version = line.partition("\t")
        items.append(
            unknown(
                app,
                "flatpak",
                version=version or None,
                removeCommand=f"flatpak uninstall {app}",
            )
        )
    return items


def scan_appimages() -> list[Item]:
    """AppImages up to three levels below $HOME (bounded walk, no full sweep)."""
    found: list[Path] = []
    for depth in ("*", "*/*", "*/*/*"):
        found += [p for p in HOME.glob(f"{depth}.[Aa]pp[Ii]mage") if p.is_file()]
    return [unknown(p.name.rsplit(".", 1)[0], "appimage", reason=str(p)) for p in sorted(set(found))]


def scan_opt() -> list[Item]:
    """Directories in /opt that no pacman package owns."""
    dirs = sorted(str(p) for p in OPT_ROOT.iterdir() if p.is_dir())
    owned = owned_by_pacman(dirs)
    return [unknown(Path(d).name, "opt", reason=d) for d in dirs if d not in owned]


def _is_elf(path: Path) -> bool:
    with path.open("rb") as fh:
        return fh.read(4) == b"\x7fELF"


def from_checkout(name: str, source: str, path: Path, how: str) -> Item:
    """An Item licensed by the checkout or package directory holding `path`."""
    lic, own = license_for_path(path)
    verdict, reason = classify_text(lic)
    return Item(
        name=name,
        source=source,  # type: ignore[arg-type]
        verdict=verdict,
        license=lic,
        reason=f"{how}; {reason}" if reason else how,
        own=own,
    )


def classify_local_bin(path: Path, owners: dict[str, Path]) -> Item | None:
    """One ~/.local/bin entry; None when it belongs to another scanned source.

    Order: pip entry point (its distribution's license), symlink into a
    checkout, loose copy of a file tracked in one of kuhy's repos, else nothing
    grants a license.
    """
    target = path.resolve()
    if any(target.is_relative_to(r) for r in TOOL_ROOTS):
        return None
    meta = owners.get(str(path))
    if meta is not None:
        dist, _, lic, url, own = dist_license(meta)
        verdict, reason = classify_text(lic)
        how = f"entry point of {dist}"
        return Item(
            name=path.name,
            source="local-bin",
            verdict=verdict,
            license=lic,
            reason=f"{how}; {reason}" if reason else how,
            url=url or None,
            own=own,
        )
    link = f"-> {target}"
    # A symlink into a checkout or a licensed package dir (npm) speaks for itself.
    if path.is_symlink() and (repo_root(target.parent) or license_for_path(target)[0]):
        return from_checkout(path.name, "local-bin", target, link)
    # Otherwise trace it to the tracked file it was copied or compiled from:
    # ~/.local/share/book-guard-desktop/.../book_guard_desktop <- book_guard_desktop.dart.
    origin = origin_of(target)
    if origin is not None:
        how = f"{link}, built from {origin}" if path.is_symlink() else f"copy of {origin}"
        return from_checkout(path.name, "local-bin", origin, how)
    if path.is_symlink():
        return from_checkout(path.name, "local-bin", target, link)
    # A hand-placed script is kuhy's own; a native binary is someone else's.
    # A pnpm-generated shim is licensed by the package it execs.
    script = target.is_file() and not _is_elf(target)
    kind = "script" if script else "binary"
    return (pnpm_item(path, target) if script else None) or unknown(
        path.name, "local-bin", reason=f"{kind} in ~/.local/bin; {NO_LICENSE}", own=script, loose=True
    )


def scan_local_bin() -> list[Item]:
    """Scripts and binaries in ~/.local/bin not owned by pipx/uv."""
    root = HOME / ".local/bin"
    if not root.is_dir():
        return []
    owners = script_owners()
    items = [classify_local_bin(p, owners) for p in sorted(root.iterdir()) if p.exists()]
    return [i for i in items if i is not None]


def scan_steam() -> list[Item]:
    """Installed Steam apps from appmanifest_*.acf (games, Proton, runtimes)."""
    items = []
    for acf in sorted(STEAM_APPS.glob("appmanifest_*.acf")):
        fields = dict(ACF_FIELD.findall(acf.read_text(errors="replace")))
        name = fields.get("name", acf.stem)
        items.append(
            Item(
                name=name,
                version=fields.get("buildid"),
                source="steam",
                verdict="nonfree",
                reason="Steam app (proprietary unless curated)",
                url=f"https://store.steampowered.com/app/{fields.get('appid', '')}",
                removeCommand=f"steam steam://uninstall/{fields.get('appid', '')}",
            ),
        )
    return items


def scan_wine() -> list[Item]:
    """Real installs under the default Wine prefix's Program Files (vendor/product)."""
    items = []
    for pf in ("Program Files", "Program Files (x86)"):
        base = WINE_PREFIX / pf
        if not base.is_dir():
            continue
        for vendor in sorted(p for p in base.iterdir() if p.is_dir() and p.name not in WINE_STOCK):
            # Exactly two levels (vendor/suite/product). rglob would walk the
            # whole install, which was 2.7 GB for CPLEX.
            products = sorted(
                g for c in vendor.iterdir() if c.is_dir() for g in c.iterdir() if g.is_dir()
            ) or [vendor]
            items += [unknown(p.name, "wine", reason=str(p.relative_to(WINE_PREFIX))) for p in products]
    return items


def scan_waydroid() -> list[Item]:
    """The Waydroid Android image, if one is installed."""
    if not WAYDROID_IMAGE.is_file():
        return []
    return [unknown("LineageOS (Waydroid)", "waydroid", reason="/var/lib/waydroid/images")]
