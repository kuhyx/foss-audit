"""Remove commands for ~/.local/bin entries, matched to whatever put them there.

A pip --user entry point goes with its distribution, a pnpm shim with its global
package, a link into another node's global node_modules with that npm's
uninstall, and the claude native install with every version it downloaded.
Anything else is the entry itself: loose files are removed, and a symlink
loses only the link, never the checkout or install it points into (those can
hold data: ~/.local/share/kuhytrack keeps kt.db next to the binary).
"""

from __future__ import annotations

from pathlib import Path

from foss_audit.cited_terms import CITED_TERMS, is_elf
from foss_audit.model import Item
from foss_audit.pnpm_shim import package_dir, shim_target
from foss_audit.remove_cmd import module_name, removing, shell_path
from foss_audit.scan_python import PIP_USER_REMOVE, read_metadata

CITED_LICENSES = frozenset(ref for _, ref in CITED_TERMS)


def npm_global(target: Path) -> tuple[Path, str] | None:
    """(prefix, package) when `target` sits in `<prefix>/lib/node_modules/<package>`."""
    if "node_modules" not in target.parts:
        return None
    package = package_dir(target)
    modules = package.parent.parent if package.parent.name.startswith("@") else package.parent
    if modules.parent.name != "lib":
        return None
    return modules.parent.parent, module_name(package)


def link_command(item: Item, path: Path, home: Path) -> tuple[str, str]:
    """(command, why) for a symlink entry."""
    entry = f"rm {shell_path(path, home)}"
    target = path.resolve()
    if item.license in CITED_LICENSES and target.parent.name == "versions":
        versions = shell_path(target.parent, home)
        return f"{entry} && rm -rf {versions}", "native install: the link and every downloaded version"
    npm = npm_global(target)
    if npm is not None:
        prefix, package = npm
        command = f"npm uninstall -g --prefix {shell_path(prefix, home)} {package} && {entry}"
        return command, f"npm global package {package}"
    return entry, f"symlink only; {shell_path(target, home)} stays"


def file_command(path: Path, home: Path) -> tuple[str, str]:
    """(command, why) for a regular file or directory entry."""
    shim = shim_target(path) if path.is_file() and not is_elf(path) else None
    if shim is not None:
        package = module_name(package_dir(shim))
        return f"pnpm remove -g {package}", f"pnpm global package {package}"
    flag = "-r " if path.is_dir() else ""
    return f"rm {flag}{shell_path(path, home)}", ""


def bin_remove(item: Item, path: Path, meta: Path | None, home: Path) -> Item:
    """`item` for ~/.local/bin entry `path`; `meta` is its pip --user dist's METADATA."""
    if meta is not None:
        dist = read_metadata(meta)[0]
        return removing(item, PIP_USER_REMOVE.format(name=dist), f"entry point of pip-user package {dist}")
    command = link_command(item, path, home) if path.is_symlink() else file_command(path, home)
    return removing(item, *command)
