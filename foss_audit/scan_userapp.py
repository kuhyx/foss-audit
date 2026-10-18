"""Self-contained apps unpacked under ~/.local/share (and a few siblings).

Installers that bypass every package manager (GitKraken's `gk`, Tachidesk's
`kcef`, Blender Launcher, the gh Copilot CLI) leave an ELF executable in
`~/.local/share/<app>/`. One item per top-level directory with an executable
ELF (not a `.so`) within three levels, licensed by its LICENSE/COPYING file,
else "nonfree" until data/curated.json says otherwise.

The walk stays cheap: no node_modules, VCS or cache trees, no symlinks, and
only the 4-byte ELF magic is read (license files, capped at 20 kB, aside).
Dirs another scanner owns (Steam, flatpak, pipx, uv, Wine/lutris) and kuhy's
own code are left alone. Installs that are not "one directory, one program"
(gh Copilot, Android SDK, Prism's JREs, Proton builds, Godot export templates,
the Actions runner, mangatl's llama.cpp) get one item each.
"""

from __future__ import annotations

import os
import re
import shlex
import stat
from pathlib import Path
from typing import Final

from foss_audit.cited_terms import is_elf
from foss_audit.licenses import classify_text
from foss_audit.model import Item
from foss_audit.own_license import identify, is_kuhy_repo, origin_of, repo_root
from foss_audit.scan_misc import unknown

SOURCE: Final = "user-app"
HOME = Path.home()
# Directories never entered: dependency trees, VCS metadata and caches.
PRUNE = frozenset({"node_modules", ".git", "cache", "caches", ".cache", "__pycache__"})
OTHER_SCANNERS = frozenset({"steam", "flatpak", "pipx", "uv", "lutris", "wine", "wineprefixes", "bottles"})
# OTHER_SCANNERS: owned by another scanner; SPECIAL: has a dedicated function below.
SPECIAL = frozenset({"gh", "godot", "prismlauncher", "mangatl"})
SHARED_LIB = re.compile(r"\.so($|\.)")
LICENSE_NAME = re.compile(r"(?i)^(licen[cs]e|copying)([._-].*)?$")
LICENSE_READ = 20_000
FREE_JDK = re.compile(r"Temurin|Adoptium|OpenJDK|Microsoft|Azul|Amazon|Red Hat|BellSoft|Arch Linux|Debian")
OPENJDK_LICENSE = "GPL-2.0 WITH Classpath-exception-2.0"


def share() -> Path:
    """The XDG data dir these apps unpack into."""
    return HOME / ".local/share"


def shown(path: Path) -> str:
    """`path` the way a person would type it: ~/..."""
    return f"~/{path.relative_to(HOME)}"


def rm_rf(path: Path) -> str:
    """The shell command that removes an unpacked app."""
    return f"rm -rf {shlex.quote(str(path))}"


def elf_programs(top: Path, depth: int = 3) -> list[Path]:
    """Executable ELF files up to `depth` levels below `top`, `.so` files excluded."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(top):
        here = Path(dirpath)
        deeper = len(here.relative_to(top).parts) + 1 < depth
        dirnames[:] = sorted(d for d in dirnames if d.lower() not in PRUNE) if deeper else []
        found += [here / f for f in sorted(filenames) if is_program(here / f)]
    return found


def is_program(path: Path) -> bool:
    """A regular, executable, non-library file starting with the ELF magic."""
    try:
        mode = path.lstat().st_mode
        return stat.S_ISREG(mode) and bool(mode & 0o111) and not SHARED_LIB.search(path.name) and is_elf(path)
    except OSError:
        return False


def license_file(*directories: Path) -> Path | None:
    """The first LICENSE/COPYING file directly inside any of the directories."""
    for directory in directories:
        for path in sorted(directory.glob("*")):
            if LICENSE_NAME.match(path.name) and path.is_file():
                return path
    return None


def licensed(name: str, where: Path, *lic_dirs: Path, **kw: object) -> Item:
    """An Item licensed by a LICENSE file in `lic_dirs`, else unlicensed (curated fixes it)."""
    found = license_file(*lic_dirs)
    if found is None:
        return unknown(name, SOURCE, **{"reason": f"{shown(where)}; no license file shipped", **kw})
    lic = identify(found.read_text(errors="replace")[:LICENSE_READ])
    verdict, why = classify_text(lic)
    reason = "; ".join(r for r in (shown(where), f"{found.name}: {lic}", why if why != lic else "") if r)
    return Item(name=name, source=SOURCE, verdict=verdict, license=lic, reason=reason, **kw)  # type: ignore[arg-type]


def is_own(top: Path, programs: list[Path]) -> bool:
    """kuhy's code: `top` sits in his checkout, or a program is built from a file he tracks."""
    root = repo_root(top)
    if root is not None and root.is_relative_to(share()) and is_kuhy_repo(root):
        return True
    return any(origin_of(p) is not None for p in programs)


def linked_from_local_bin() -> list[Path]:
    """Targets of the ~/.local/bin symlinks; the local-bin scanner already reports those."""
    root = HOME / ".local/bin"
    return [p.resolve() for p in root.glob("*") if p.is_symlink()]


def scan_apps() -> list[Item]:
    """One item per ~/.local/share/<app> that holds an ELF executable."""
    if not share().is_dir():
        return []
    items: list[Item] = []
    linked = linked_from_local_bin()
    for top in sorted(p for p in share().iterdir() if p.is_dir() and not p.is_symlink()):
        if top.name.lower() in OTHER_SCANNERS | SPECIAL or any(t.is_relative_to(top) for t in linked):
            continue
        programs = elf_programs(top)
        if programs and not is_own(top, programs):
            items.append(licensed(top.name, programs[0], top, removeCommand=rm_rf(top)))
    return items


def scan_gh_copilot() -> list[Item]:
    """The gh Copilot CLI: the gh-copilot extension (gh removes it) and the downloaded `copilot` agent."""
    manifest, agent = share() / "gh/extensions/gh-copilot/manifest.yml", share() / "gh/copilot"
    steps = {"gh extension remove copilot": manifest.is_file(), rm_rf(agent): (agent / "copilot").is_file()}
    if not (remove := " && ".join(step for step, present in steps.items() if present)):
        return []
    tag = re.search(r"^tag:\s*v?(\S+)", manifest.read_text(), re.MULTILINE) if manifest.is_file() else None
    reason = f"{shown(agent.parent)}; no license shipped (GitHub Copilot terms)"
    return [unknown("gh-copilot", SOURCE, version=tag and tag[1], reason=reason, removeCommand=remove)]


def scan_android_sdk() -> list[Item]:
    """~/sdk/Android/Sdk: Google's SDK License is accepted via licenses/* hash files."""
    sdk = HOME / "sdk/Android/Sdk"
    if not sdk.is_dir():
        return []
    accepted = sorted(p.name for p in (sdk / "licenses").glob("*") if p.is_file())
    if "android-sdk-license" not in accepted:
        return [unknown("android-sdk", SOURCE, reason=f"{shown(sdk)}; no SDK license accepted")]
    reason = f"{shown(sdk)}; Android SDK License accepted ({', '.join(accepted)})"
    return [
        Item(
            name="android-sdk",
            source=SOURCE,
            verdict="nonfree",
            license="LicenseRef-Android-SDK-License",
            reason=reason,
        )
    ]


def java_runtime(runtime: Path) -> tuple[str, str]:
    """(JAVA_VERSION, license) of an unpacked JRE; license is "" unless it is OpenJDK.

    The `release` file names the vendor (IMPLEMENTOR); Mojang's runtimes omit it,
    so a GPL `legal/java.base/LICENSE` counts too.
    """
    release = runtime / "release"
    text = release.read_text(errors="replace") if release.is_file() else ""
    version = re.search(r'^JAVA_VERSION="([^"]+)"', text, re.MULTILINE)
    vendor = re.search(r'^IMPLEMENTOR="([^"]+)"', text, re.MULTILINE)
    legal = runtime / "legal/java.base/LICENSE"
    gpl = legal.is_file() and identify(legal.read_text(errors="replace")[:LICENSE_READ]) == "GPL"
    free = bool(vendor and FREE_JDK.search(vendor[1])) or gpl
    return (version[1] if version else "?"), (OPENJDK_LICENSE if free else "")


def scan_prism_java() -> list[Item]:
    """The JREs PrismLauncher downloads (the launcher itself is a pacman package)."""
    java = share() / "PrismLauncher/java"
    runtimes = sorted(p for p in java.glob("*") if p.is_dir())
    if not runtimes:
        return []
    found = {r.name: java_runtime(r) for r in runtimes}
    detail = ", ".join(f"{name} {ver}" for name, (ver, _) in found.items())
    versions = ", ".join(sorted({ver for ver, _ in found.values()}))
    if all(lic for _, lic in found.values()):
        verdict, lic, reason = "foss", OPENJDK_LICENSE, f"OpenJDK builds: {detail}"
    else:
        verdict, lic, reason = "nonfree", "", f"{detail}; not recognisably OpenJDK"
    return [
        Item(
            name="PrismLauncher java runtimes",
            source=SOURCE,
            verdict=verdict,  # type: ignore[arg-type]
            license=lic,
            reason=reason,
            version=versions,
            removeCommand=rm_rf(java),
        )
    ]


def scan_proton_tools() -> list[Item]:
    """Custom Proton builds (GE-Proton...) in Steam's compatibilitytools.d."""
    tools = share() / "Steam/compatibilitytools.d"
    return [licensed(t.name, t, t, removeCommand=rm_rf(t)) for t in sorted(tools.glob("*")) if t.is_dir()]


def scan_godot_templates() -> list[Item]:
    """Godot export templates: one item, with every installed engine version."""
    root = share() / "godot/export_templates"
    versions = sorted(p for p in root.glob("*") if p.is_dir())
    if not versions:
        return []
    return [licensed("godot export templates", root, *versions, version=", ".join(v.name for v in versions))]


def scan_actions_runner() -> list[Item]:
    """The GitHub Actions self-hosted runner(s) under ~/services/actions-runner."""
    root = HOME / "services/actions-runner"
    runners = sorted(p for p in root.glob("*") if (p / "bin/Runner.Listener").exists())
    if not runners:
        return []
    # `bin` is a symlink to bin.<runner version>.
    ver = re.search(r"bin\.(\d[\d.]*)$", (runners[-1] / "bin").resolve().name)
    lic_dirs = [d for r in runners for d in (r, r / "bin")]
    return [licensed("github actions-runner", root, *lic_dirs, version=ver[1] if ver else None)]


def scan_llama_cpp() -> list[Item]:
    """mangatl's vendored llama.cpp (llama-server); mangatl itself is not an item."""
    root = share() / "mangatl/llama.cpp"
    if not any(p.name == "llama-server" for p in elf_programs(root, depth=4)):
        return []
    return [licensed("llama.cpp (llama-server)", root, root)]


def scan_user_apps() -> list[Item]:
    """Every user-installed app under ~/.local/share and the special-cased installs."""
    steps = (
        scan_apps,
        scan_gh_copilot,
        scan_android_sdk,
        scan_prism_java,
        scan_proton_tools,
        scan_godot_templates,
        scan_actions_runner,
        scan_llama_cpp,
    )
    return [item for step in steps for item in step()]
