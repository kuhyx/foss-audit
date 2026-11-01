"""Shared by the package-cache scanners (Maven/Gradle, pub, npm/pnpm, cargo, pip).

A cache holds every version a build ever downloaded. Each scanner reads one
cache into `CachedArtifact`s (one per package, every cached version with the
license it declares) and `to_items` turns them into one Item per package:

- the verdict is the WORST over all cached versions, so a relicense in one
  version (MIT -> BSL) is never hidden by a free newer one;
- a free package whose newest version depends at runtime on a non-free one in
  the same cache is `foss-partial`, naming that dependency;
- `requiredBy` lists the ~/src projects whose lockfile or build file names the
  package; when none does, the note says so instead of implying "unused".

A version with no license data at all must still say where the scanner
looked (`license_from`), never a bare blank: no silent stops.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from foss_audit import http_fetch
from foss_audit.licenses import classify_text
from foss_audit.model import NO_LICENSE, Item, Source, Verdict

HOME = Path.home()
SRC = HOME / "src"
# Lockfiles and build files sit at most this deep under ~/src
# (~/src/<repo>/<app>/android/app/build.gradle is depth 4).
PROJECT_DEPTH = 4
HTTP_CACHE = HOME / ".cache/foss-audit/http"
FETCH_TIMEOUT_S = 15
SEVERITY: dict[Verdict, int] = {"foss": 0, "foss-partial": 1, "nonfree": 2}
# A meta-package's license_from names this many of its dependencies.
MAX_NAMED = 5
Judged = tuple[Verdict, str]


@dataclass
class CachedVersion:
    """One cached version and the license it declares."""

    version: str
    license: str
    # Where the license was read: "pom", "pom parent g:a:v", "LICENSE file",
    # "package.json", ... When `license` is "", every place that was checked.
    license_from: str
    # Runtime dependency names in the same ecosystem (no dev/test/optional).
    deps: tuple[str, ...] = ()
    # Dependencies only an optional extra pulls in: a meta-package's whole payload.
    extra_deps: tuple[str, ...] = ()
    # Ships no code of its own, only dependencies (a pip wheel of bare
    # .dist-info): the one kind of package that may take its deps' license.
    meta: bool = False
    # A meta-package whose dependencies' licenses differ: the worst of their
    # verdicts, which the joined license string cannot carry by itself.
    inherited: Judged | None = None


@dataclass
class CachedArtifact:
    """One package of a cache with every version it holds."""

    name: str
    versions: list[CachedVersion] = field(default_factory=list)
    url: str | None = None


def version_key(version: str) -> tuple[tuple[int, int | str], ...]:
    """Sort key: numeric runs compare as numbers, so 1.10 sorts after 1.9."""
    parts = re.findall(r"\d+|[A-Za-z]+", version)
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in parts)


def classify_version(cv: CachedVersion) -> tuple[Verdict, str]:
    """Verdict and reason for one version's license."""
    if cv.inherited:
        return cv.inherited
    if not cv.license.strip():
        return "nonfree", f"{NO_LICENSE}; checked {cv.license_from}"
    return classify_text(cv.license)


def project_files(names: Iterable[str], root: Path = SRC, depth: int = PROJECT_DEPTH) -> list[Path]:
    """Files matching the glob patterns `names` at most `depth` levels under ~/src (bounded, no deep walk).

    A pattern without a slash is matched during one pass over the directories (a
    per-pattern glob would list them all again); node_modules is never entered.
    """
    wanted = list(names)
    plain = [n for n in wanted if "/" not in n]
    found: list[Path] = []
    for name in (n for n in wanted if "/" in n):
        for level in range(1, depth + 1):
            found += root.glob("/".join(["*"] * level) + "/" + name)
    pending = [(str(root), 0)] if plain else []
    while pending:
        folder, level = pending.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            if level and any(fnmatch.fnmatchcase(entry.name, pattern) for pattern in plain):
                found.append(Path(entry.path))
            if level < depth and entry.name != "node_modules" and entry.is_dir():
                pending.append((entry.path, level + 1))
    return sorted(p for p in set(found) if p.is_file() and "node_modules" not in p.parts)


def project_of(path: Path, root: Path = SRC) -> str:
    """The ~/src repo a file belongs to, as `~/src/<repo>`."""
    return f"~/src/{path.relative_to(root).parts[0]}"


def fetch_cached(url: str, cache_dir: Path = HTTP_CACHE) -> bytes:
    """GET `url`, kept on disk so each license is fetched once.

    Raises OSError on failure; callers turn that into the item's reason so a
    failed lookup is visible, never a blank license.
    """
    path = cache_dir / hashlib.sha256(url.encode()).hexdigest()
    if path.exists():
        return path.read_bytes()
    data = http_fetch.get(url, FETCH_TIMEOUT_S)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _differing_licenses(versions: list[CachedVersion]) -> str:
    """ "licenses differ by version: 1.0 MIT; 2.0 BUSL" when they do, else ""."""
    if len({v.license for v in versions}) < 2:
        return ""
    return "licenses differ by version: " + "; ".join(f"{v.version} {v.license or '?'}" for v in versions)


def artifact_item(source: Source, art: CachedArtifact, used_by: list[str]) -> Item:
    """One Item for a package: worst verdict over its versions, newest first."""
    versions = sorted(art.versions, key=lambda v: version_key(v.version), reverse=True)
    judged = [(classify_version(v), v) for v in versions]
    (verdict, reason), worst = max(judged, key=lambda j: SEVERITY[j[0][0]])
    newest = versions[0]
    notes = [n for n in (_differing_licenses(versions),) if n]
    if worst is not newest and verdict != "foss":
        reason = f"{worst.version}: {reason}"
    notes.append(f"license from {newest.license_from}")
    if not used_by:
        notes.append("no ~/src lockfile or build file names it (transitive or stale)")
    return Item(
        name=art.name,
        source=source,
        verdict=verdict,
        version=", ".join(v.version for v in versions),
        license=newest.license,
        reason=reason,
        url=art.url,
        requiredBy=sorted(used_by),
        note="; ".join(notes),
    )


def _names(names: list[str]) -> str:
    more = f" and {len(names) - MAX_NAMED} more" if len(names) > MAX_NAMED else ""
    return ", ".join(names[:MAX_NAMED]) + more


def _from_deps(name: str, cv: CachedVersion, own: dict[str, str]) -> tuple[str, str, Judged | None]:
    """(license, license_from, inherited verdict) a blank version gets from its cached
    dependencies. When they disagree it takes the worst verdict and every license,
    worst first; one dependency of unknown license blocks it all."""
    present = sorted(d for d in {*cv.deps, *cv.extra_deps} if d in own and d != name)
    if not present:
        return "", cv.license_from, None
    judged = {d: classify_text(own[d]) for d in present}
    unknown = [d for d in present if judged[d][1] == NO_LICENSE or judged[d][1].startswith("unrecognised")]
    if unknown:
        return "", f"{cv.license_from}; dependency {unknown[0]} has no known license", None
    counts = Counter(own[d] for d in present)
    verdict_of = {own[d]: judged[d] for d in present}
    ranked = sorted(counts, key=lambda lic: (-SEVERITY[verdict_of[lic][0]], -counts[lic], lic))
    whence = f"its dependencies {_names(present)} (declares none itself; checked {cv.license_from})"
    if len({verdict for verdict, _ in judged.values()}) == 1:
        return ranked[0], whence, None
    return " + ".join(ranked), whence, verdict_of[ranked[0]]


def inherit_from_deps(arts: list[CachedArtifact]) -> None:
    """Meta-packages: a code-less version that declares no license takes its cached
    dependencies' (extras included): the one they agree on, else all of them under
    the worst verdict. Donors are each package's
    newest version as read from its own data, so an inherited license is never
    passed on."""
    own = {a.name: max(a.versions, key=lambda v: version_key(v.version)).license for a in arts}
    for art in arts:
        for cv in art.versions:
            if cv.meta and not cv.license.strip():
                cv.license, cv.license_from, cv.inherited = _from_deps(art.name, cv, own)


def to_items(source: Source, artifacts: Iterable[CachedArtifact], used_by: dict[str, set[str]]) -> list[Item]:
    """Items for a whole cache, then mark free ones with a non-free dependency."""
    arts = list(artifacts)
    inherit_from_deps(arts)
    items = {a.name: artifact_item(source, a, list(used_by.get(a.name, ()))) for a in arts}
    nonfree = {name for name, item in items.items() if item.verdict == "nonfree"}
    for art in arts:
        item = items[art.name]
        newest = max(art.versions, key=lambda v: version_key(v.version))
        bad = sorted(d for d in newest.deps if d in nonfree and d != art.name)
        if item.verdict == "foss" and bad:
            item.verdict = "foss-partial"
            item.reason = "depends on non-free " + ", ".join(bad)
    return list(items.values())
