"""Find the license of every cached Maven version, in the order the data allows.

Per version: its POM's <licenses>, then the nearest <parent> POM that
declares one, then the Gradle .module (which has no license field, but is
noted as checked), then the JAR/AAR's own embedded POM and LICENSE/NOTICE
files. Only when all of that is silent is the missing POM or parent POM
fetched from Google Maven / Maven Central (once per URL, kept on disk by
`fetch_cached`), in parallel rounds because a fetched POM can name a parent
that is not cached either. A failed fetch lands in `license_from`, so the
item's reason says exactly where the lookup stopped.
"""

from __future__ import annotations

import http.client
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from foss_audit import cache_common, progress
from foss_audit.licenses import classify_text
from foss_audit.own_license import identify
from foss_audit.scan_cache_maven_jar import archive_license
from foss_audit.scan_cache_maven_pom import KNOWN_IDS, Gav, Pom, gav_name, parse_pom, pom_path
from foss_audit.scan_cache_maven_repos import repo_order
from foss_audit.scan_cache_maven_source import Upstream

FETCH_WORKERS = 24
MAX_ROUNDS = 8
SOURCE = "maven-cache"
MAX_MARKER_HOPS = 3
FETCH_ERRORS = (OSError, http.client.HTTPException, ValueError)
# One fetch job: candidate URLs for the same file, tried in order.
Want = tuple[str, ...]


@dataclass
class VersionFiles:
    """The cached files of one group:artifact:version, from either cache."""

    poms: list[Path] = field(default_factory=list)
    archives: list[Path] = field(default_factory=list)
    # Gradle .module metadata files: no license field, but the dependencies Gradle resolves.
    modules: list[Path] = field(default_factory=list)


@dataclass
class Found:
    """A version's license, where it came from, and what a fetch could add."""

    license: str
    license_from: str
    deps: tuple[str, ...] = ()
    wants: tuple[Want, ...] = ()


@dataclass
class Store:
    """Every POM the lookup can read: cached files first, fetched ones after."""

    files: dict[Gav, VersionFiles]
    # (group, artifact) -> the repository Gradle downloaded it from.
    repos: dict[tuple[str, str], str] = field(default_factory=dict)
    upstream: Upstream = field(default_factory=Upstream)
    fetched: dict[str, bytes] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)
    _parsed: dict[Gav, tuple[Pom | None, str]] = field(default_factory=dict)
    _archive: dict[Gav, tuple[str, str]] = field(default_factory=dict)

    def pom(self, gav: Gav) -> tuple[Pom | None, str]:
        """(POM, label) from the caches, else from a fetch; label says which."""
        if gav not in self._parsed:
            self._parsed[gav] = self._load(gav)
        return self._parsed[gav]

    def _load(self, gav: Gav) -> tuple[Pom | None, str]:
        for path in self.files.get(gav, VersionFiles()).poms:
            pom = parse_pom(path.read_bytes())
            if pom is not None:
                return pom, ""
        for url in self.urls(gav):
            pom = parse_pom(self.fetched[url]) if url in self.fetched else None
            if pom is not None:
                return pom, f" from {url}"
        return None, ""

    def archive(self, gav: Gav) -> tuple[str, str]:
        """The JAR/AAR lookup, done once per version."""
        if gav not in self._archive:
            self._archive[gav] = archive_license(self.files.get(gav, VersionFiles()).archives, gav[0], gav[1])
        return self._archive[gav]

    def urls(self, gav: Gav) -> Want:
        """Where `gav`'s POM may be published, the recorded repository first."""
        bases = repo_order(gav[0], self.repos.get((gav[0], gav[1])))
        return tuple(f"{base}/{pom_path(gav)}" for base in bases)

    def missing(self, gav: Gav) -> tuple[str, tuple[Want, ...]]:
        """Why `gav`'s POM is absent, and the fetch still worth trying."""
        urls = self.urls(gav)
        left = tuple(u for u in urls if u not in self.failed and u not in self.fetched)
        if not left:
            tried = "; ".join(f"{u}: {self.failed.get(u, 'not a POM')}" for u in urls)
            return f"license fetch failed: {tried}", ()
        why = "unreadable" if self.files.get(gav, VersionFiles()).poms else "not cached"
        return why, (left,)

    def forget_missing(self) -> None:
        """Drop the "no POM" answers so freshly fetched POMs are seen."""
        self._parsed = {gav: got for gav, got in self._parsed.items() if got[0] is not None}


def _url_license(store: Store, pom: Pom) -> tuple[str, str, tuple[Want, ...]]:
    """An unnamed license's URL, read and identified: (license, url, wants)."""
    for url in pom.unnamed_urls:
        if url in store.fetched:
            spdx = identify(store.fetched[url].decode("utf-8", errors="replace"))
            if spdx in KNOWN_IDS:
                return spdx, url, ()
        elif url not in store.failed:
            return "", "", ((url,),)
    return "", "", ()


def _declared(store: Store, gav: Gav, pom: Pom, label: str) -> Found:
    """The license a POM declares; a bare URL is followed when unrecognised,
    then the source repository's LICENSE when the URL's page names none."""
    text = " / ".join(pom.licenses)
    if not pom.unnamed_urls or not classify_text(text)[1].startswith("unrecognised"):
        return Found(text, label)
    spdx, url, wants = _url_license(store, pom)
    if spdx:
        return Found(spdx, f"{label} license url {url}")
    if wants:
        return Found(text, label, wants=wants)
    found, where = store.upstream.license(gav, pom.source_urls)
    if found:
        return Found(found, f"{label} license url unidentified; {where}")
    return Found(text, label)


def resolve(store: Store, gav: Gav, hops: int = 0) -> Found:
    """`gav`'s license, or every place checked and the fetches that could help."""
    checked: list[str] = []
    wants: list[Want] = []
    pom, origin = store.pom(gav)
    deps = pom.deps if pom is not None else ()
    label = "pom" + origin
    sources = pom.source_urls if pom is not None else ()
    if pom is None:
        why, urls = store.missing(gav)
        checked.append(f"pom ({why})")
        wants += urls
    while pom is not None:
        if pom.licenses:
            found = _declared(store, gav, pom, label)
            return Found(found.license, found.license_from, deps, found.wants)
        checked.append(f"{label} (no <licenses>)")
        if pom.marker is not None and hops < MAX_MARKER_HOPS:
            target = resolve(store, pom.marker, hops + 1)
            via = f"plugin marker -> {gav_name(pom.marker)}: {target.license_from}"
            return Found(target.license, via, deps, target.wants)
        if pom.parent is None:
            break
        parent = pom.parent
        pom, origin = store.pom(parent)
        label = f"pom parent {gav_name(parent)}{origin}"
        if pom is not None and pom.group == gav[0]:
            sources += pom.source_urls
        if pom is None:
            why, urls = store.missing(parent)
            checked.append(f"{label} ({why})")
            wants += urls
    if store.files.get(gav, VersionFiles()).modules:
        checked.append("gradle .module (no license field)")
    license_text, where = store.archive(gav)
    if license_text:
        return Found(license_text, where, deps)
    checked += [where] if where else ["no jar/aar cached"]
    own = store.pom(gav)[0]
    if own is not None and own.header:
        return Found(own.header, f"{'; '.join(checked)}; license comment atop the pom", deps)
    if not wants:
        license_text, where = store.upstream.license(gav, sources)
        if license_text:
            return Found(license_text, where, deps)
        checked += [where] if where else []
    return Found("", "; ".join(checked), deps, tuple(wants))


def _fetch(want: Want) -> list[tuple[str, bytes | None, str]]:
    """Try each candidate URL until one answers; every failure is kept."""
    tried: list[tuple[str, bytes | None, str]] = []
    for url in want:
        try:
            tried.append((url, cache_common.fetch_cached(url), ""))
        except FETCH_ERRORS as exc:
            tried.append((url, None, str(exc) or type(exc).__name__))
            continue
        break
    progress.counter(SOURCE).advance()
    return tried


def fetch_all(store: Store, wants: Iterable[Want]) -> None:
    """Run the fetch jobs in parallel into the store."""
    jobs = sorted(set(wants))
    progress.counter(SOURCE).add_total(len(jobs))
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        for tried in pool.map(_fetch, jobs):
            for url, data, error in tried:
                if data is None:
                    store.failed[url] = error
                else:
                    store.fetched[url] = data


def resolve_all(store: Store, gavs: Iterable[Gav]) -> dict[Gav, Found]:
    """Every version's license, fetching missing POMs only for unresolved ones;
    the source-repository lookups are collected, run in parallel, then used."""
    store.upstream.collecting = True
    results = {gav: resolve(store, gav) for gav in progress.counted(SOURCE, gavs)}
    for _ in range(MAX_ROUNDS):
        pending = {gav: found.wants for gav, found in results.items() if found.wants}
        if not pending:
            break
        fetch_all(store, (url for wants in pending.values() for url in wants))
        store.forget_missing()
        results.update({gav: resolve(store, gav) for gav in progress.counted(SOURCE, pending)})
    store.upstream.collecting = False
    if store.upstream.run_queued():  # POMs and archives are memoised: resolving again is cheap
        results = {gav: resolve(store, gav) for gav in progress.counted(SOURCE, list(results))}
    return results
