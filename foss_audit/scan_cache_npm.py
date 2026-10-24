"""npm packages in the pnpm store(s) and npm's _cacache, one Item per name.

Every cached version gets the license its own files declare (see
scan_cache_npm_manifest); a version found in several stores is read once.
`requiredBy` lists the ~/src projects whose pnpm-lock.yaml or
package-lock.json names the package.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

from foss_audit import cache_remove_npm, scan_cache_npm_cacache, scan_cache_npm_pnpm
from foss_audit.cache_common import SRC, CachedArtifact, project_files, project_of, to_items
from foss_audit.model import Item, Source
from foss_audit.scan_cache_npm_cacache import scan_cacache
from foss_audit.scan_cache_npm_manifest import Found
from foss_audit.scan_cache_npm_pnpm import scan_pnpm_store

SOURCE: Source = "npm-cache"
LOCKFILES = ("pnpm-lock.yaml", "package-lock.json")
# A pnpm-lock.yaml package key at indent 2: `  /name@1.0.0:`, `  name@1.0.0(peer@2):`
# or `  '@scope/name@1.0.0':` (`"` when prettier rewrote it), under `packages:` / `snapshots:`.
LOCK_KEY = re.compile(r"""^  ['"]?/?((?:@[^/@\s'"]+/)?[^@\s'"/(]+)@""")
LOCK_SECTIONS = ("packages:", "snapshots:")


def pnpm_lock_names(text: str) -> set[str]:
    """Package names a pnpm-lock.yaml resolves (no YAML parser needed)."""
    names: set[str] = set()
    in_packages = False
    for line in text.splitlines():
        if line and not line[0].isspace():
            in_packages = line.strip() in LOCK_SECTIONS
        elif in_packages and (match := LOCK_KEY.match(line)):
            names.add(match.group(1))
    return names


def _v1_names(deps: object) -> set[str]:
    """Names in a lockfileVersion 1 nested `dependencies` tree."""
    if not isinstance(deps, dict):
        return set()
    names = set(deps)
    for spec in deps.values():
        if isinstance(spec, dict):
            names |= _v1_names(spec.get("dependencies"))
    return names


def package_lock_names(text: str) -> set[str]:
    """Package names a package-lock.json resolves (v2/v3 `packages`, v1 tree)."""
    try:
        doc = json.loads(text)
    except ValueError:
        return set()
    if not isinstance(doc, dict):
        return set()
    packages = doc.get("packages")
    names = {
        key.rpartition("node_modules/")[2]
        for key in (packages if isinstance(packages, dict) else {})
        if "node_modules/" in key
    }
    return names | _v1_names(doc.get("dependencies"))


def lock_users(files: Iterable[Path], root: Path) -> dict[str, set[str]]:
    """Package name -> the ~/src projects whose lockfile names it."""
    users: dict[str, set[str]] = {}
    for path in files:
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        names = pnpm_lock_names(text) if path.name.endswith(".yaml") else package_lock_names(text)
        for name in names:
            users.setdefault(name, set()).add(project_of(path, root))
    return users


def merge(found: Iterable[Found]) -> list[CachedArtifact]:
    """One artifact per name, one version per (name, version); a licensed
    reading of a version beats a blank one from another store."""
    arts: dict[str, CachedArtifact] = {}
    for item in found:
        art = arts.setdefault(item.name, CachedArtifact(item.name, url=item.url))
        same = next((v for v in art.versions if v.version == item.cached.version), None)
        if same is None:
            art.versions.append(item.cached)
        elif not same.license and item.cached.license:
            art.versions[art.versions.index(same)] = item.cached
    return [arts[name] for name in sorted(arts)]


def scan_npm_cache() -> list[Item]:
    """Every npm package cached by pnpm or npm on this machine."""
    found = scan_pnpm_store()
    # A blank pnpm reading still lets npm's copy of the same version be read.
    found += scan_cacache({(f.name, f.cached.version) for f in found if f.cached.license})
    used_by = lock_users(project_files(LOCKFILES, SRC), SRC)
    arts = merge(found)
    items = to_items(SOURCE, arts, used_by)
    cache_remove_npm.fill(items, arts, SRC, scan_cache_npm_cacache.CACACHE, scan_cache_npm_pnpm.STORE)
    return items
