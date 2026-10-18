"""License, deps and URL of one cached npm package, from its own files only.

Every store (pnpm v3/v10/v11, npm's _cacache tarballs) hands over the parsed
package.json plus lazy readers for the package's top-level files. The license
comes from, in order: the package.json `license` / legacy `licenses` field (a
"SEE LICENSE IN <file>" pointer reads that file); a LICENSE/LICENCE/COPYING
file; the README's "License" section; last, the repository's default branch
(labelled "default branch, not <version>"). Nothing curated, nothing guessed:
when all are silent the license stays "" and `license_from` names them.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from foss_audit.cache_common import CachedVersion
from foss_audit.scan_cache_npm_fallback import (
    EXCERPT_CHARS,
    LICENSE_URL,
    excerpt,
    known_id,
    recognised,
    upstream,
    url_license,
)
from foss_audit.upstream_license import not_this_version

README_FILE = re.compile(r"(?i)^readme([.-].*)?$")
# LICENSE, LICENCE.md, COPYING, LICENSE-MIT, MIT-LICENSE.txt, UNLICENSE; not the
# "._LICENSE" AppleDouble junk old tarballs carry, nor code (license-checker.js).
LICENSE_NAME = re.compile(
    r"(?i)^(?!\._)(?!.*\.(?:[cm]?[jt]sx?|json|map)$)(?:[\w.]+[-_.])?(?:un)?(licen[cs]e|copying)([-_.].*)?$"
)
# "SEE LICENSE IN <file>", or a bare "SEE LICENSE" meaning the LICENSE file.
SEE_FILE = re.compile(r"(?i)^SEE LICEN[CS]E(?:\s+IN\s+(\S+))?")
# A README heading (markdown "#", setext or bold) whose text starts with
# "license"; "License: MIT" carries the answer on the heading line itself.
LICENSE_HEADING = re.compile(
    r"(?im)^[#=*\s]*licen[cs]es?\b[*_ \t]*(?::[ \t]*(?P<inline>[^\n]*))?[^\n]*(?:\n|$)"
)
SECTION_END = re.compile(r"(?m)^#{1,6}\s")
SECTION_CHARS = 4000
NPM_PAGE = "https://www.npmjs.com/package/"
NOWHERE = "package.json license field, LICENSE file, README license section"

# Top-level file name -> reader of its text (called only when needed).
Files = Mapping[str, Callable[[], str]]


@dataclass(frozen=True)
class Found:
    """One cached version of an npm package and where it was read."""

    name: str
    url: str
    cached: CachedVersion


def field_text(value: Any) -> str:
    """A license field as text: a string, a legacy {type} object, or an array
    of either (dual licensing, joined as an SPDX OR-expression)."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return field_text(value.get("type") or value.get("name"))
    if isinstance(value, list):
        parts = [p for p in (field_text(v) for v in value) if p]
        if len(parts) > 1:
            return f"({' OR '.join(parts)})"
        return parts[0] if parts else ""
    return ""


def manifest_license(data: Mapping[str, Any]) -> str:
    """The package.json license field, `license` before legacy `licenses`."""
    return field_text(data.get("license")) or field_text(data.get("licenses"))


def readme_license(text: str) -> str:
    """The README's own words for its license: "License: MIT" on the heading
    line, a recognised license text in the "License" section, else that
    section's first line ("MIT (c) Sindre")."""
    heading = LICENSE_HEADING.search(text)
    if heading is None:
        return ""
    inline = (heading["inline"] or "").strip(" *_`")
    if inline:
        return inline[:EXCERPT_CHARS]
    body = text[heading.end() : heading.end() + SECTION_CHARS]
    end = SECTION_END.search(body)
    section = body[: end.start()] if end else body
    lines = [ln.strip(" \t#*_>`-=[]()") for ln in section.splitlines()]
    return known_id(section) or next((ln for ln in lines if ln), "")[:EXCERPT_CHARS]


def _from_files(files: Files) -> tuple[str, str, str]:
    """(license, from, unrecognised LICENSE excerpt) out of the LICENSE then README files."""
    unrecognised = ""
    for name in sorted(n for n in files if LICENSE_NAME.match(n)):
        text = files[name]()
        if spdx := known_id(text):
            return spdx, f"{name} file", ""
        unrecognised = unrecognised or excerpt(text)
    for name in sorted(n for n in files if README_FILE.match(n)):
        if lic := readme_license(files[name]()):
            return lic, f"{name} license section", unrecognised
    return "", "", unrecognised


def _pointed(field: str, target: str, files: Files) -> str:
    """The license in the file "SEE LICENSE IN <target>" names ("" if none).

    A README with no license section yields "", so the LICENSE files are next.
    """
    if target not in files:
        return ""
    text = files[target]()
    if README_FILE.match(target):
        return readme_license(text)
    return known_id(text) or f"{field}: {excerpt(text)}"


def _pointer_fallback(field: str, target: str, files: Files) -> tuple[str, str]:
    """A "SEE LICENSE" pointer without a usable file: a recognised LICENSE or
    README wins, else the pointer with whatever the LICENSE file says."""
    lic, where, unrecognised = _from_files(files)
    if recognised(lic):
        return lic, f"{where} (package.json: {field})"
    pointed = f"{field}: {unrecognised}" if unrecognised else field
    return pointed, f"package.json, nothing in {target}" if target else "package.json"


def _unknown_field(field: str, data: Mapping[str, Any], files: Files) -> tuple[str, str]:
    """A field the classifier cannot judge ("Open Source", a license URL): the
    URL's text, then LICENSE/README, then the repository's HEAD. Nothing
    recognised keeps the LICENSE file's own words, else the field, and names
    every place tried."""
    tried = ["package.json"]
    if LICENSE_URL.match(field):
        lic, where = url_license(field)
        if lic:
            return lic, where
        tried.append(where)
    lic, where, unrecognised = _from_files(files)
    if recognised(lic):
        return lic, f"{where} (package.json: {field})"
    tried.append("LICENSE file, README license section")
    lic, where = upstream(data)
    if recognised(lic):
        return lic, f"{where}{not_this_version(data.get('version'))} (package.json: {field})"
    tried.append(where)
    if unrecognised:
        return unrecognised, "LICENSE file (unrecognised text); checked " + "; ".join(tried)
    return field, "; ".join(tried)


def _without_field(data: Mapping[str, Any], files: Files) -> tuple[str, str]:
    """No license field: LICENSE/README, else the repository's HEAD (labelled as
    not necessarily this version's), else "" naming every place tried."""
    lic, where, unrecognised = _from_files(files)
    if lic:
        return lic, where
    if unrecognised:
        return unrecognised, "LICENSE file (unrecognised text)"
    lic, where = upstream(data)
    if lic:
        return lic, f"{where}{not_this_version(data.get('version'))}"
    return "", f"{NOWHERE}; {where}"


def resolve_license(data: Mapping[str, Any], files: Files) -> tuple[str, str]:
    """(license, license_from) for one package, or ("", every place checked)."""
    field = manifest_license(data)
    if not field:
        return _without_field(data, files)
    pointer = SEE_FILE.match(field)
    if pointer is None:
        return (field, "package.json") if recognised(field) else _unknown_field(field, data, files)
    target = (pointer.group(1) or "").removeprefix("./")
    if lic := _pointed(field, target, files):
        return lic, f"{target} (package.json: {field})"
    return _pointer_fallback(field, target, files)


def project_url(data: Mapping[str, Any], name: str) -> str:
    """package.json homepage, else its repository URL, else the npm page."""
    home = data.get("homepage")
    if isinstance(home, str) and "://" in home:
        return home
    repo = data.get("repository")
    url = repo.get("url") if isinstance(repo, dict) else repo
    if isinstance(url, str) and "://" in url:
        return url.removeprefix("git+")
    return NPM_PAGE + name


def runtime_deps(data: Mapping[str, Any]) -> tuple[str, ...]:
    """Names in `dependencies` only (dev/peer/optional are not runtime)."""
    deps = data.get("dependencies")
    return tuple(sorted(deps)) if isinstance(deps, dict) else ()


def found(data: Mapping[str, Any], files: Files, name: str, version: str, where: str) -> Found:
    """The Found for a parsed package.json; `name`/`version` fill gaps in it."""
    real_name = _text(data.get("name")) or name
    lic, lic_from = resolve_license(data, files)
    cached = CachedVersion(
        _text(data.get("version")) or version, lic, f"{lic_from} ({where})", runtime_deps(data)
    )
    return Found(real_name, project_url(data, real_name), cached)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def unreadable(name: str, version: str, where: str, error: str) -> Found:
    """A version whose package.json could not be read: blank license, visible why."""
    cached = CachedVersion(version, "", f"{where}: package.json unreadable ({error})")
    return Found(name, NPM_PAGE + name, cached)
