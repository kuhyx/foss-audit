"""Scan Python installs: pip --user, pipx venvs, uv tools and conda envs."""

from __future__ import annotations

import json
import os
import shlex
from email.parser import HeaderParser
from pathlib import Path
from urllib.parse import unquote

from foss_audit.licenses import classify_text
from foss_audit.model import Item, Source
from foss_audit.own_license import OWN_MARKER, checkout_for_url, declared_license, is_kuhy_repo, repo_root
from foss_audit.remove_cmd import shell_path, sudo_for

HOME = Path.home()
PIPX_VENVS = HOME / ".local/share/pipx/venvs"
UV_TOOLS = HOME / ".local/share/uv/tools"
CONDA_ROOTS = (Path("/opt/miniconda3"), HOME / "miniconda3", HOME / "micromamba")
# Shared with the ~/.local/bin entry points a pip --user dist installs.
PIP_USER_REMOVE = "pip uninstall --break-system-packages {name}"


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


def _direct_url(dist_info: Path) -> dict[str, str]:
    direct = dist_info / "direct_url.json"
    return json.loads(direct.read_text()) if direct.is_file() else {}


def checkout_of(dist_info: Path) -> Path | None:
    """The local source dir pip installed from: a file:// URL, or the local
    checkout of a github.com/kuhyx VCS URL (plus its subdirectory)."""
    data = _direct_url(dist_info)
    url = str(data.get("url", ""))
    if url.startswith("file://"):
        return Path(unquote(url.removeprefix("file://")))
    repo = checkout_for_url(url)
    return repo / str(data.get("subdirectory", "")) if repo else None


def is_own_install(dist_info: Path, homepage: str) -> bool:
    """True when pip installed one of kuhy's repos (by URL or from his checkout).

    A kuhyx checkout can vendor someone else's project (mcp-servers holds
    blender-mcp), so a homepage on another GitHub account wins over the checkout.
    """
    if OWN_MARKER in str(_direct_url(dist_info).get("url", "")):
        return True
    if "github.com/" in homepage and OWN_MARKER not in homepage:
        return False
    checkout = checkout_of(dist_info)
    root = repo_root(checkout) if checkout else None
    return root is not None and is_kuhy_repo(root)


def dist_license(meta: Path) -> tuple[str, str, str, str, bool]:
    """(name, version, license, homepage, own); local installs fall back to the checkout's LICENSE."""
    name, version, lic, url = read_metadata(meta)
    checkout = checkout_of(meta.parent)
    if not lic and checkout and checkout.is_dir():
        lic = declared_license(checkout, repo_root(checkout) or checkout)
    return name, version, lic, url, is_own_install(meta.parent, url)


def _dist_item(meta: Path, source: Source, remove: str) -> Item:
    name, version, lic, url, own = dist_license(meta)
    verdict, reason = classify_text(lic)
    return Item(
        name=name,
        version=version or None,
        source=source,
        verdict=verdict,
        license=lic,
        reason=reason,
        url=url or None,
        own=own,
        removeCommand=remove.format(name=name),
    )


def user_sites() -> list[Path]:
    """Every pip --user site-packages dir."""
    return sorted(HOME.glob(".local/lib/python3*/site-packages"))


def script_owners() -> dict[str, Path]:
    """~/.local/bin/<script> path -> METADATA of the pip --user dist whose RECORD lists it."""
    owners: dict[str, Path] = {}
    for site in user_sites():
        for record in site.glob("*.dist-info/RECORD"):
            for line in record.read_text(errors="replace").splitlines():
                rel = line.split(",", 1)[0]
                if "/bin/" in rel:
                    owners[os.path.normpath(site / rel)] = record.parent / "METADATA"
    return owners


def scan_pip_user() -> list[Item]:
    """Distributions in ~/.local/lib/python3*/site-packages."""
    items: list[Item] = []
    for site in user_sites():
        items += [
            _dist_item(m, "pip-user", PIP_USER_REMOVE) for m in sorted(site.glob("*.dist-info/METADATA"))
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


def conda_remove(root: Path, prefix: Path, env: str, package: str) -> str:
    """Remove `package` from one env with the root's own conda; micromamba when the root has none."""
    conda, name = root / "bin/conda", shlex.quote(package)
    if conda.is_file():
        return f"{sudo_for(root)}{shell_path(conda, HOME)} remove -n {shlex.quote(env)} {name}"
    return f"{sudo_for(root)}micromamba remove -p {shell_path(prefix, HOME)} {name}"


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
                package = str(data.get("name", rec.stem))
                items.append(
                    Item(
                        name=f"{package} [{env}]",
                        version=data.get("version"),
                        source="conda",
                        verdict=verdict,
                        license=lic,
                        reason=reason,
                        url=None,
                        removeCommand=conda_remove(root, meta_dir.parent, env, package),
                    ),
                )
    return items
