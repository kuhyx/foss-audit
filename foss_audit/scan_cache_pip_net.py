"""Last-resort license lookups for cached Python distributions.

Only for versions whose cached metadata and license files named nothing
recognisable: first the ~/src checkout that builds the distribution (kuhy's
own projects ship no license metadata), then PyPI's per-version JSON, then the
LICENSE file inside that version's sdist on PyPI, then the default branch of the
project's source repository on any forge (upstream_license; labelled as not
necessarily this version's). Every place tried is kept in `license_from`, and a
failed fetch says which URL failed and why.
"""

from __future__ import annotations

import io
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

from foss_audit import cache_common, progress, upstream_license
from foss_audit.own_license import declared_license, repo_root
from foss_audit.scan_cache_pip_meta import Record, classifier_license, known
from foss_audit.scan_cache_pip_read import records_from

# project_urls keys that name the source repository rather than docs or funding.
REPO_KEY = re.compile(r"(?i)source|repo|code|git")
PYPI_JSON = "https://pypi.org/pypi/{name}/{version}/json"
# Parallel fetches bound a cold network fallback to about one timeout.
WORKERS = 8


def from_checkout(record: Record, dirs: list[Path]) -> Record:
    """The license of the ~/src checkout that builds `record`, when it declares one."""
    for directory in dirs:
        try:
            lic = declared_license(directory, repo_root(directory) or directory)
        except OSError, ValueError:
            continue
        if lic.strip():
            return replace(
                record, license=lic, license_from=f"LICENSE/pyproject of ~/src checkout {directory}"
            )
    for root in dict.fromkeys(r for r in map(repo_root, dirs) if r is not None):
        lic, where = upstream_license.local_readme_license(root)
        if lic:
            return replace(record, license=lic, license_from=where)
    tried = ", ".join(str(d) for d in dirs)
    return replace(record, license_from=f"{record.license_from}; no license in ~/src checkout {tried}")


def _json_license(info: dict[str, Any]) -> str:
    """Same precedence as cached metadata: expression, a recognised License, classifiers."""
    expr, lic = str(info.get("license_expression") or "").strip(), str(info.get("license") or "")
    return expr or (lic if known(lic) else "") or classifier_license(info.get("classifiers") or [])


def _sdist_url(data: dict[str, Any]) -> str:
    return str(
        next((u.get("url", "") for u in data.get("urls") or [] if u.get("packagetype") == "sdist"), "")
    )


def _archive_license(blob: bytes) -> str:
    found = records_from(io.BytesIO(blob), "PyPI sdist") or []
    return next((r.license for r in found if known(r.license)), "")


def source_repo(info: dict[str, Any], url: str | None) -> str:
    """The project's source repository on any forge: a project_urls link keyed like
    one (Source, Repository, Code), then any other link, home_page, the record's URL."""
    links = info.get("project_urls") or {}
    keyed = [v for k, v in links.items() if REPO_KEY.search(k)]
    candidates = [*keyed, *links.values(), info.get("home_page"), url]
    return next(
        (repo for repo in (upstream_license.repository(str(c or "")) for c in candidates) if repo), ""
    )


def from_pypi(record: Record) -> Record:
    """`record` with the license PyPI (or its source repo) states, or every place tried spelled out."""
    tried = [record.license_from]
    url = PYPI_JSON.format(name=record.name, version=record.version)
    try:
        data = json.loads(cache_common.fetch_cached(url))
        info = data.get("info") or {}
        lic = _json_license(info)
        if lic:
            return replace(record, license=lic, license_from=f"PyPI JSON {url}")
        tried.append(f"PyPI JSON {url} (no license)")
        url = _sdist_url(data)
        lic = _archive_license(cache_common.fetch_cached(url)) if url else ""
        if lic:
            return replace(record, license=lic, license_from=f"license file in PyPI sdist {url}")
        tried.append(f"PyPI sdist {url} (no license file)" if url else "PyPI lists no sdist")
        url = source_repo(info, record.url)
        lic, checked = upstream_license.upstream_license(url) if url else ("", "no source repository URL")
        if lic:
            where = f"{checked}{upstream_license.not_this_version(record.version)}"
            return replace(record, license=lic, license_from=where)
        tried.append(checked)
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        tried.append(f"fetch failed: {url}: {exc}")
    return replace(record, license_from="; ".join(tried))


def _from_pypi_counted(record: Record) -> Record:
    fixed = from_pypi(record)
    progress.counter("pip-cache").advance()
    return fixed


def resolve(records: list[Record], checkouts: dict[str, list[Path]]) -> list[Record]:
    """Records that found no license string at all, filled from a checkout or PyPI.

    A name some ~/src checkout builds, or an editable install, is never looked
    up on PyPI: a local project's name can belong to someone else's package.
    """
    blank = [not r.license.strip() for r in records]
    local = [
        from_checkout(r, checkouts[r.name]) if b and r.name in checkouts else r
        for r, b in zip(records, blank, strict=True)
    ]
    todo = [i for i, r in enumerate(local) if blank[i] and not r.local and r.name not in checkouts]
    progress.counter("pip-cache").add_total(len(todo))
    with ThreadPoolExecutor(WORKERS) as pool:
        for i, fixed in zip(todo, pool.map(_from_pypi_counted, [local[i] for i in todo]), strict=True):
            local[i] = fixed
    return local
