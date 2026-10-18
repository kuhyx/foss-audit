"""Text helpers and the remote fallbacks for an npm package's license.

Used when package.json's `license` is something the classifier cannot judge:
a URL to a license text (fetched once through cache_common.fetch_cached) or
wording like "Open Source". The last resort is the package's repository via
upstream_license. Every failure is returned as text so the item names it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from foss_audit import cache_common, upstream_license
from foss_audit.licenses import classify_text
from foss_audit.own_license import TEXT_IDS, identify

KNOWN_IDS = frozenset(spdx for _, spdx in TEXT_IDS)
EXCERPT_LINES = 3
EXCERPT_CHARS = 200
UNRECOGNISED = "unrecognised license"
LICENSE_URL = re.compile(r"^https?://\S+$")
WORD = re.compile(r"\w")
# npm repository shorthands: "github:u/r", "gitlab:u/r", "bitbucket:u/r", "u/r".
SHORTHAND = re.compile(r"^(?:(github|gitlab|bitbucket):)?([\w.-]+/[\w.-]+)$")
HOSTS = {"github": "github.com", "gitlab": "gitlab.com", "bitbucket": "bitbucket.org"}


def known_id(text: str) -> str:
    """The SPDX-ish id when the text is a license `identify` recognises, else ""."""
    found = identify(text)
    return found if found in KNOWN_IDS else ""


def excerpt(text: str) -> str:
    """The first few worded lines of an unrecognised license text ("/*" and
    "=====" skipped), so "All rights reserved" or "public domain" reaches the
    classifier, not just a title."""
    lines = [ln.strip() for ln in text.splitlines() if WORD.search(ln)]
    return " ".join(lines[:EXCERPT_LINES])[:EXCERPT_CHARS]


def recognised(lic: str) -> bool:
    """True when classify_text gives a verdict rather than "unrecognised"."""
    return bool(lic) and not classify_text(lic)[1].startswith(UNRECOGNISED)


def url_license(url: str) -> tuple[str, str]:
    """(license, where) of the text a license URL serves; license "" when the
    fetch failed or the text is not recognised (`where` says which)."""
    try:
        text = cache_common.fetch_cached(url).decode(errors="replace")
    except OSError as exc:
        return "", f"license URL {url}: fetch failed: {exc}"
    lic = known_id(text) or excerpt(text)
    if recognised(lic):
        return lic, f"license URL {url}"
    return "", f"license URL {url}: unrecognised text {lic!r}"


def repository_url(data: Mapping[str, Any]) -> str:
    """package.json `repository` as a URL (shorthands expanded), "" when absent."""
    repo = data.get("repository")
    url = repo.get("url") if isinstance(repo, dict) else repo
    if not isinstance(url, str):
        return ""
    short = SHORTHAND.match(url.strip())
    if short:
        return f"https://{HOSTS[short[1] or 'github']}/{short[2]}"
    return url.strip()


def upstream(data: Mapping[str, Any]) -> tuple[str, str]:
    """(license, where checked) of the package's repository HEAD."""
    url = repository_url(data)
    if not url:
        return "", "no repository URL"
    return upstream_license.upstream_license(url)
