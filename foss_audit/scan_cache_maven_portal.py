"""Last Maven fallback: a Gradle plugin's source repository, as the plugin portal names it.

Plugins published to plugins.gradle.org often ship a POM with no <licenses>,
<scm> or <url> and a JAR with no license file; the portal's page for the
plugin id still links its sources. The ids come from the JAR's own
META-INF/gradle-plugins/<id>.properties entries (read, never run), the page
is fetched once and kept by `fetch_cached`, and its "Sources" link (else its
website, when that is a forge) goes to `upstream_license`. That reads the
default branch, so the label says it is not necessarily this version's.
Only versions every earlier step left blank are looked up, in parallel.
"""

from __future__ import annotations

import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from foss_audit import cache_common, progress, upstream_license
from foss_audit.cache_common import CachedArtifact, CachedVersion
from foss_audit.scan_cache_maven_inherit import proven_blank
from foss_audit.scan_cache_maven_pom import Gav
from foss_audit.scan_cache_maven_resolve import FETCH_ERRORS, VersionFiles

PAGE = "https://plugins.gradle.org/plugin/{id}"
PLUGIN_ENTRY = re.compile(r"^META-INF/gradle-plugins/(.+)\.properties$")
# <a id="vcsUrl" href="..."> under "Sources:", <a id="website" href="...">.
LINK = re.compile(rb'id="(vcsUrl|website)"\s+href="([^"]+)"')
WORKERS = 8


def plugin_ids(archives: list[Path]) -> list[str]:
    """The plugin ids a JAR declares, from its entry names only."""
    ids: list[str] = []
    for path in archives:
        try:
            with zipfile.ZipFile(path) as archive:
                ids += [m.group(1) for m in map(PLUGIN_ENTRY.match, archive.namelist()) if m]
        except OSError, zipfile.BadZipFile:
            continue
    return list(dict.fromkeys(ids))


def source_link(page: bytes) -> str:
    """The repository a portal page links: its Sources link, else a forge website."""
    links = sorted(LINK.findall(page), key=lambda link: link[0] != b"vcsUrl")
    found = (upstream_license.repository(url.decode(errors="replace")) for _, url in links)
    return next((repo for repo in found if repo), "")


def portal_license(ids: list[str], version: str) -> tuple[str, str]:
    """(license, where) from the first plugin id whose sources name one; ("", tried)."""
    tried: list[str] = []
    for plugin_id in ids:
        page = PAGE.format(id=plugin_id)
        try:
            repo = source_link(cache_common.fetch_cached(page))
        except FETCH_ERRORS as exc:
            tried.append(f"gradle plugin portal {page}: fetch failed: {exc}")
            continue
        if not repo:
            tried.append(f"gradle plugin portal {page} (no source repository link)")
            continue
        found, checked = upstream_license.upstream_license(repo)
        where = f"gradle plugin portal {page} sources -> {checked}"
        if found:
            return found, where + upstream_license.not_this_version(version)
        tried.append(where)
    return "", "; ".join(tried)


def _ask_portal(job: tuple[CachedVersion, list[str]]) -> tuple[str, str]:
    answer = portal_license(job[1], job[0].version)
    progress.counter("maven-cache").advance()
    return answer


def fill(arts: list[CachedArtifact], files: dict[Gav, VersionFiles]) -> None:
    """Blank versions of Gradle plugins take their portal source repository's license."""
    todo: list[tuple[CachedVersion, list[str]]] = []
    for art in arts:
        group, artifact = art.name.split(":", 1)
        for cv in art.versions:
            gav = (group, artifact, cv.version)
            ids = plugin_ids(files.get(gav, VersionFiles()).archives) if proven_blank(cv) else []
            if ids:
                todo.append((cv, ids))
    progress.counter("maven-cache").add_total(len(todo))
    with ThreadPoolExecutor(WORKERS) as pool:
        answers = list(pool.map(_ask_portal, todo))
    for (cv, _), (found, where) in zip(todo, answers, strict=True):
        if found:
            cv.license, cv.license_from = found, f"{where}; {cv.version} itself: {cv.license_from}"
        else:
            cv.license_from = f"{cv.license_from}; {where}"
