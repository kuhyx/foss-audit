"""Installed Steam apps (games, Proton, runtimes) from appmanifest_*.acf.

Everything Steam installs ships under the Steam Subscriber Agreement. On top
of that the scanner reports what it can find locally: an app-specific EULA
from Steam's app cache, the install root's own LICENSE files (Proton's BSD),
and the free components a game bundles in a `licenses/` folder. Offline on
purpose: the store site is blocked in /etc/hosts.

Each folder in ~/.steam/steam/compatibilitytools.d (GE-Proton, proton-cachyos)
is a Steam compat tool and an item here too; the user-app scanner skips it. The
id is the folder name, never the display name, which embeds the version.
"""

from __future__ import annotations

import re
import shlex
from collections import defaultdict
from pathlib import Path

from foss_audit.licenses import classify_text
from foss_audit.model import Item
from foss_audit.own_license import LICENSE_FILE, TEXT_IDS, identify
from foss_audit.steam_appinfo import eulas_for

STEAM_APPS = Path.home() / ".local/share/Steam/steamapps"
COMPAT_TOOLS = Path.home() / ".steam/steam/compatibilitytools.d"
NO_TOOL_LICENSE = "no license file shipped (proprietary unless curated)"
ACF_FIELD = re.compile(r'^\s*"(name|appid|buildid|installdir)"\s+"([^"]*)"', re.MULTILINE)
SSA = "LicenseRef-Steam-Subscriber-Agreement"
# Folders where games collect the licenses of the libraries and fonts they ship.
BUNDLE_DIR = re.compile(r"(?i)^(licen[cs]es|third[-_ ]?party([-_ ]licen[cs]es)?)$")
KNOWN_IDS = frozenset(spdx for _, spdx in TEXT_IDS)


def _read(path: Path) -> str:
    return path.read_text(errors="replace")


def root_licenses(root: Path) -> list[str]:
    """Recognised ids of the LICENSE/COPYING files at the install root."""
    if not root.is_dir():
        return []
    files = sorted(f for f in root.iterdir() if f.is_file() and LICENSE_FILE.match(f.name))
    ids = (identify(_read(f)) for f in files)
    return list(dict.fromkeys(i for i in ids if i in KNOWN_IDS))


def bundled_note(root: Path) -> str:
    """'bundled components: MIT: a, b; ...' from a licenses/ folder, else ""."""
    if not root.is_dir():
        return ""
    groups: dict[str, list[str]] = defaultdict(list)
    for folder in sorted(d for d in root.iterdir() if d.is_dir() and BUNDLE_DIR.match(d.name)):
        for f in sorted(p for p in folder.iterdir() if p.is_file()):
            # Every recognised id is a free license; BSD/ISC texts never say
            # "BSD"/"ISC", so only the unrecognised rest goes to classify_text.
            text = _read(f)
            spdx = identify(text)
            if spdx in KNOWN_IDS:
                label = spdx
            else:
                label = "other free" if classify_text(text)[0] == "foss" else "not free"
            groups[label].append(f.stem)
    if not groups:
        return ""
    return "bundled components: " + "; ".join(
        f"{label}: {', '.join(names)}" for label, names in sorted(groups.items())
    )


def tool_version(tool: Path) -> str | None:
    """Last field of the tool's `version` file ("<timestamp> <name>"), None without one."""
    version = tool / "version"
    fields = version.read_text(errors="replace").split() if version.is_file() else []
    return fields[-1] if fields else None


def scan_compat_tools() -> list[Item]:
    """One Item per compat tool folder; Steam does not ship these, so no Subscriber Agreement."""
    items = []
    for tool in sorted(t for t in COMPAT_TOOLS.glob("*") if t.is_dir()):
        ids = root_licenses(tool)
        found = f"LICENSE files: {', '.join(ids)}" if ids else NO_TOOL_LICENSE
        items.append(
            Item(
                name=tool.name,
                version=tool_version(tool),
                source="steam",
                verdict="foss" if ids else "nonfree",
                license=" ".join(ids),
                reason=f"Steam compatibility tool; {found}",
                note=bundled_note(tool),
                removeCommand=f"rm -rf {shlex.quote(str(tool))}",
            ),
        )
    return items


def scan_steam() -> list[Item]:
    """One Item per appmanifest and per compat tool; licenses as described in the module docstring."""
    manifests: list[dict[str, str]] = [
        dict(ACF_FIELD.findall(acf.read_text(errors="replace"))) | {"_stem": acf.stem}
        for acf in sorted(STEAM_APPS.glob("appmanifest_*.acf"))
    ]
    appids = {int(m["appid"]) for m in manifests if m.get("appid", "").isdigit()}
    eulas = eulas_for(appids) if appids else {}
    items = []
    for fields in manifests:
        appid = fields.get("appid", "")
        root = STEAM_APPS / "common" / fields.get("installdir", "")
        own_eulas = eulas.get(int(appid), []) if appid.isdigit() else []
        license_ids = [SSA, *([f"LicenseRef-EULA-{appid}"] if own_eulas else [])]
        license_ids += root_licenses(root) if fields.get("installdir") else []
        notes = [f"EULA: {e.name} <{e.url.replace('.com//', '.com/')}>" for e in own_eulas]
        notes.append(bundled_note(root) if fields.get("installdir") else "")
        items.append(
            Item(
                name=fields.get("name", fields["_stem"]),
                version=fields.get("buildid"),
                source="steam",
                verdict="nonfree",
                license=" ".join(license_ids),
                reason="Steam app (proprietary unless curated)",
                note="; ".join(n for n in notes if n),
                url=f"https://store.steampowered.com/app/{appid}",
                removeCommand=f"steam steam://uninstall/{appid}",
            ),
        )
    return items + scan_compat_tools()
