"""Scan Python installs: pip --user, pipx venvs, uv tools and conda envs."""

from __future__ import annotations

import json
from email.parser import HeaderParser
from pathlib import Path

from foss_audit.licenses import classify_text
from foss_audit.model import Item, Source

HOME = Path.home()
PIPX_VENVS = HOME / ".local/share/pipx/venvs"
UV_TOOLS = HOME / ".local/share/uv/tools"
CONDA_ROOTS = (Path("/opt/miniconda3"), HOME / "miniconda3", HOME / "micromamba")


def _norm(name: str) -> str:
    return name.lower().replace("_", "-")


def read_metadata(meta: Path) -> tuple[str, str, str, str]:
    """Return (name, version, license, homepage) from a dist-info METADATA file.

    License-Expression wins, then trove classifiers, then the free-text License
    field (which is often a copyright header, e.g. mitmproxy's BSD preamble).
    """
    msg = HeaderParser().parsestr(meta.read_text(errors="replace"))
    lic = msg.get("License-Expression") or ""
    if not lic:
        classifiers = [
            c.split("::")[-1].strip() for c in msg.get_all("Classifier") or [] if c.startswith("License ::")
        ]
        lic = "; ".join(classifiers)
    if not lic:
        raw = (msg.get("License") or "").strip().splitlines()
        lic = raw[0][:80] if raw else ""
    url = msg.get("Home-page") or ""
    if not url:
        for entry in msg.get_all("Project-URL") or []:
            url = entry.split(",", 1)[-1].strip()
            break
    return msg.get("Name", meta.parent.name), msg.get("Version", ""), lic, url


OWN_URL_MARKERS = ("file://", "github.com/kuhyx/")


def is_own_install(dist_info: Path) -> bool:
    """True when pip installed from a local checkout or one of kuhy's repos."""
    direct = dist_info / "direct_url.json"
    if not direct.is_file():
        return False
    data = json.loads(direct.read_text())
    url = str(data.get("url", ""))
    return any(m in url for m in OWN_URL_MARKERS)


def _dist_item(meta: Path, source: Source, remove: str) -> Item:
    name, version, lic, url = read_metadata(meta)
    if is_own_install(meta.parent):
        verdict, reason = "own", "installed from kuhy's own repo/checkout"
    else:
        verdict, reason = classify_text(lic)
    return Item(
        name=name,
        version=version or None,
        source=source,
        verdict=verdict,  # type: ignore[arg-type]
        license=lic,
        reason=reason,
        url=url or None,
        removeCommand=remove.format(name=name),
    )


def scan_pip_user() -> list[Item]:
    """Distributions in ~/.local/lib/python3*/site-packages."""
    items: list[Item] = []
    for site in sorted(HOME.glob(".local/lib/python3*/site-packages")):
        items += [
            _dist_item(m, "pip-user", "pip uninstall --user {name}")
            for m in sorted(site.glob("*.dist-info/METADATA"))
        ]
    return items


def _tool_venvs(root: Path, source: Source, remove: str) -> list[Item]:
    """One Item per tool venv: the distribution whose name matches the venv dir."""
    items: list[Item] = []
    for venv in sorted(p for p in root.glob("*") if p.is_dir()):
        target = _norm(venv.name)
        # dist-info dirs are "<name>-<version>.dist-info", so the name is
        # everything before the last dash; no need to parse every METADATA.
        for meta in venv.glob("lib/python3*/site-packages/*.dist-info/METADATA"):
            if _norm(meta.parent.name.removesuffix(".dist-info").rsplit("-", 1)[0]) == target:
                items.append(_dist_item(meta, source, remove))
                break
    return items


def scan_pipx() -> list[Item]:
    """Tools installed with pipx."""
    return _tool_venvs(PIPX_VENVS, "pipx", "pipx uninstall {name}")


def scan_uv_tools() -> list[Item]:
    """Tools installed with `uv tool install`."""
    return _tool_venvs(UV_TOOLS, "uv-tool", "uv tool uninstall {name}")


def scan_conda() -> list[Item]:
    """Packages in every conda env (base + envs/*) under the known roots."""
    items: list[Item] = []
    for root in CONDA_ROOTS:
        for meta_dir in [root / "conda-meta", *sorted(root.glob("envs/*/conda-meta"))]:
            env = meta_dir.parent.name if meta_dir.parent != root else "base"
            for rec in sorted(meta_dir.glob("*.json")):
                data = json.loads(rec.read_text())
                lic = str(data.get("license") or "")
                verdict, reason = classify_text(lic)
                items.append(
                    Item(
                        name=f"{data.get('name', rec.stem)} [{env}]",
                        version=data.get("version"),
                        source="conda",
                        verdict=verdict,
                        license=lic,
                        reason=reason,
                        url=None,
                    ),
                )
    return items
