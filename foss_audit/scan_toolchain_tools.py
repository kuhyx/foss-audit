"""Global third-party tools of the language toolchains (source "toolchain").

One item per .NET global tool, Dart `pub global` package, user-level gem and
`go install`ed module;
scan_toolchain.py passes in the home directory. The license comes from what the
install records (LICENSE, nuspec, gemspec); without one the tool is "nonfree".
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Final

from foss_audit.licenses import classify_text
from foss_audit.model import Item
from foss_audit.own_license import identify
from foss_audit.scan_misc import unknown

SOURCE: Final = "toolchain"

NUSPEC_LICENSE = re.compile(r'<license type="expression">([^<]+)</license>')
PUB_HEADER = re.compile(r"^# (Package|Version): (\S+)", re.MULTILINE)
GEM_BIN_OWNER = re.compile(r"Gem\.activate_bin_path\(\s*'([^']+)'")
GEMSPEC_LICENSES = re.compile(r"\bs\.licenses = \[([^\]]*)\]")
QUOTED = re.compile(r'"([^"]+)"')
# `go version -m <dir>`: a "<binary>: go1.x" header, then a tab-indented "mod" line.
GO_BIN_HEADER = re.compile(r"^(\S.*): go\S*$")
GO_MOD_LINE = re.compile(r"^\tmod\t(\S+)\t(\S+)")
GOPATHS: Final = ("sdk/go", "go")


def natural_key(text: str) -> list[object]:
    """Sort key that orders 3.9 before 3.10 and v22.2 before v22.13."""
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", text)]


def subdirs(root: Path) -> list[Path]:
    """Real subdirectories of `root` in natural name order; empty if root is absent."""
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: natural_key(p.name))


def first_text(files: list[Path]) -> str:
    """Text of the first existing file in `files`, else the empty string."""
    return next((p.read_text(errors="replace") for p in files if p.is_file()), "")


def tool_item(name: str, version: str | None, lic: str, remove: str, where: str) -> Item:
    """A third-party tool: licensed by `lic` when the install records one, else unknown."""
    if not lic:
        return unknown(
            name, SOURCE, version=version, reason=f"{where}; no license shipped", removeCommand=remove
        )
    verdict, reason = classify_text(lic)
    return Item(
        name=name,
        source=SOURCE,
        version=version,
        verdict=verdict,
        license=lic,
        reason="; ".join(r for r in (where, reason) if r),
        removeCommand=remove,
    )


def license_of(files: list[Path]) -> str:
    """SPDX-ish id of the first existing license file, else the empty string."""
    text = first_text(files)
    return identify(text) if text else ""


def scan_dotnet_tools(home: Path) -> list[Item]:
    """`dotnet tool install -g` tools; the package keeps its LICENSE or nuspec in .store."""
    root = home / ".dotnet/tools"
    if not root.is_dir():
        return []
    items = []
    for shim in sorted(p for p in root.iterdir() if p.is_file()):
        versions = subdirs(root / ".store" / shim.name)
        latest = versions[-1] if versions else None
        lic = ""
        if latest is not None:
            lic = license_of(sorted(latest.glob("LICENSE*")) + sorted(latest.glob("*/*/LICENSE*")))
            nuspec = first_text(sorted(latest.glob("*/*/*.nuspec")))
            lic = lic or (m.group(1) if (m := NUSPEC_LICENSE.search(nuspec)) else "")
        items.append(
            tool_item(
                shim.name,
                latest.name if latest else None,
                lic,
                f"dotnet tool uninstall -g {shim.name}",
                "~/.dotnet/tools",
            )
        )
    return items


def scan_pub_global(home: Path) -> list[Item]:
    """`dart pub global activate` packages, found through their ~/.pub-cache/bin stubs."""
    root = home / ".pub-cache"
    if not (root / "bin").is_dir():
        return []
    packages: dict[str, str | None] = {}
    for stub in sorted(p for p in (root / "bin").iterdir() if p.is_file()):
        header = dict(PUB_HEADER.findall(stub.read_text(errors="replace")))
        packages.setdefault(header.get("Package", stub.name), header.get("Version"))
    items = []
    for pkg, version in packages.items():
        files = sorted((root / "hosted/pub.dev" / f"{pkg}-{version}").glob("LICENSE*")) if version else []
        items.append(
            tool_item(
                pkg, version, license_of(files), f"dart pub global deactivate {pkg}", "~/.pub-cache/bin"
            )
        )
    return items


def scan_gems(home: Path) -> list[Item]:
    """User-level gems (--user-install), found through their bin stubs."""
    ruby_dirs = [*home.glob(".local/share/gem/ruby/*"), *home.glob(".gem/ruby/*")]
    owners: dict[str, Path] = {}
    for ruby in sorted(ruby_dirs):
        for stub in sorted(p for p in (ruby / "bin").glob("*") if p.is_file()):
            match = GEM_BIN_OWNER.search(stub.read_text(errors="replace"))
            owners.setdefault(match.group(1) if match else stub.name, ruby)
    items = []
    for gem, ruby in owners.items():
        specs = sorted(
            (ruby / "specifications").glob(f"{gem}-[0-9]*.gemspec"), key=lambda p: natural_key(p.name)
        )
        versions = [s.stem.removeprefix(f"{gem}-") for s in specs]
        found = GEMSPEC_LICENSES.search(first_text(specs[::-1]))
        lic = " OR ".join(QUOTED.findall(found.group(1))) if found else ""
        items.append(
            tool_item(
                gem,
                ", ".join(versions) or None,
                lic,
                f"gem uninstall {gem}",
                "~/.local/share/gem" if ".local" in ruby.parts else "~/.gem",
            )
        )
    return items


def go_module_dir(gopath: Path, module: str, version: str) -> Path:
    """The module cache dir; Go escapes upper-case letters as "!" plus lower-case."""
    escaped = re.sub(r"[A-Z]", lambda m: "!" + m.group(0).lower(), module)
    return gopath / "pkg/mod" / f"{escaped}@{version}"


def go_bin_modules(go: str, bindir: Path) -> dict[tuple[str, str], list[str]]:
    """(module, version) -> binary names, from one `go version -m` over the bin dir."""
    out = subprocess.run(
        [go, "version", "-m", str(bindir)], capture_output=True, text=True, check=False, timeout=30
    ).stdout
    modules: dict[tuple[str, str], list[str]] = {}
    binary = ""
    for line in out.splitlines():
        if header := GO_BIN_HEADER.match(line):
            binary = Path(header.group(1)).name
        elif binary and (mod := GO_MOD_LINE.match(line)):
            modules.setdefault((mod.group(1), mod.group(2)), []).append(binary)
            binary = ""
    return modules


def scan_go_bins(home: Path) -> list[Item]:
    """`go install`ed tools in a GOPATH bin; one item per module, not per binary."""
    go = shutil.which("go")
    items = []
    for gopath in (home / sub for sub in GOPATHS):
        bindir = gopath / "bin"
        if not go or not bindir.is_dir() or (bindir / "go").exists():
            continue
        for (module, version), bins in go_bin_modules(go, bindir).items():
            files = sorted(go_module_dir(gopath, module, version).glob("LICENSE*"))
            remove = "rm " + " ".join(str(bindir / b) for b in bins)
            items.append(
                tool_item(module, version, license_of(files), remove, f"~/{gopath.relative_to(home)}/bin")
            )
    return items
