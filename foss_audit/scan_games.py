"""Scan Wine's Program Files and the Waydroid image (Steam is scan_steam.py).

Neither records a license, so both are "nonfree" until data/curated.json says
otherwise.
"""

from __future__ import annotations

from pathlib import Path

from foss_audit.model import Item
from foss_audit.remove_cmd import removing, shell_path
from foss_audit.scan_misc import unknown

HOME = Path.home()
WINE_PREFIX = HOME / ".wine/drive_c"
# Wine's own stub directories; anything else under Program Files is a real install.
WINE_STOCK = {
    "Common Files",
    "Internet Explorer",
    "Windows Media Player",
    "Windows NT",
    "Zero G Registry",
}
WAYDROID_IMAGE = Path("/var/lib/waydroid/images/system.img")


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
            items += [
                removing(
                    unknown(p.name, "wine", reason=str(p.relative_to(WINE_PREFIX))),
                    f"rm -rf {shell_path(p, HOME)}",
                    "files only; Wine's uninstall registry entry stays",
                )
                for p in products
            ]
    return items


def scan_waydroid() -> list[Item]:
    """The Waydroid Android image, if one is installed.

    Removing it undoes `waydroid init`: /var/lib/waydroid (image, rootfs,
    overlay, config) and the Android user data in ~/.local/share/waydroid.
    """
    if not WAYDROID_IMAGE.is_file():
        return []
    user_data = HOME / ".local/share/waydroid"
    gone = [WAYDROID_IMAGE.parents[1]] + ([user_data] if user_data.is_dir() else [])
    command = "sudo systemctl stop waydroid-container && sudo rm -rf " + " ".join(
        shell_path(d, HOME) for d in gone
    )
    item = unknown("LineageOS (Waydroid)", "waydroid", reason="/var/lib/waydroid/images")
    return [removing(item, command, "image, overlay and Android user data; the waydroid package stays")]
