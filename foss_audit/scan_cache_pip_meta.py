"""Core-metadata parsing for the pip/uv cache scanner (METADATA and PKG-INFO).

Pure functions over text: the readers in `scan_cache_pip_read` hand over the
metadata of one cached wheel or sdist plus a lazy loader for the license files
next to it, and get back one `Record`. Nothing here touches the cache itself.

License precedence: PEP 639 `License-Expression`, then the `License` field
(a whole license text there is identified, not quoted), then `License ::`
trove classifiers, then the license files shipped beside the metadata. Only
a License field `classify_text` cannot place (a copyright line) is passed over,
and it is still the answer when nothing later names a license.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from email.parser import HeaderParser
from typing import Any

from foss_audit.licenses import classify_text
from foss_audit.model import NO_LICENSE
from foss_audit.own_license import identify

# The leading distribution name of a Requires-Dist / requirements line.
REQ_NAME = re.compile(r"^\s*([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)")
EXTRA_MARKER = re.compile(r"\bextra\s*==")
PLACEHOLDERS = frozenset({"", "unknown", "none", "?", "n/a", "license", "other"})
# A License field longer than this, or spanning lines, is a pasted license text.
SHORT_LICENSE = 120
# Project-URL labels that point at the project itself, normalised.
URL_LABELS = ("homepage", "source", "sourcecode", "repository", "code")
FIELDS = "License-Expression, License, License classifiers, license files"

LicenseFiles = Callable[[], list[tuple[str, str]]]


@dataclass(frozen=True)
class Record:
    """What one cached wheel or sdist says about itself."""

    name: str
    version: str
    license: str
    license_from: str
    deps: tuple[str, ...]
    url: str | None
    # Requires-Dist names an optional extra gates (a meta-package's payload).
    extra_deps: tuple[str, ...] = ()
    # Ships nothing but its .dist-info: a meta-package (see cache_common).
    meta: bool = False
    # Built from a local source tree (editable install), not from an index.
    local: bool = False

    def to_json(self) -> dict[str, Any]:
        """Plain dict for the on-disk index."""
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Record:
        """Inverse of `to_json`."""
        return cls(**{**data, "deps": tuple(data["deps"]), "extra_deps": tuple(data.get("extra_deps", ()))})


def norm(name: str) -> str:
    """PEP 503 normalised distribution name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def known(lic: str) -> bool:
    """True when `classify_text` recognises the string (free or not)."""
    reason = classify_text(lic)[1]
    return bool(lic.strip()) and reason != NO_LICENSE and not reason.startswith("unrecognised license")


def _dep_names(requires: list[str], *, extras: bool) -> tuple[str, ...]:
    names = set()
    for req in requires:
        _, _, marker = req.partition(";")
        match = REQ_NAME.match(req)
        if match and bool(EXTRA_MARKER.search(marker)) == extras:
            names.add(norm(match.group(1)))
    return tuple(sorted(names))


def runtime_deps(requires: list[str]) -> tuple[str, ...]:
    """Normalised Requires-Dist names that no `extra ==` marker gates."""
    return _dep_names(requires, extras=False)


def extra_deps(requires: list[str]) -> tuple[str, ...]:
    """Normalised Requires-Dist names only an `extra ==` marker pulls in."""
    return _dep_names(requires, extras=True)


def project_url(home: str, project_urls: list[str], name: str) -> str:
    """Home-page, else a Homepage/Source Project-URL, else the PyPI page."""
    if home.strip() and home.strip().lower() not in PLACEHOLDERS:
        return home.strip()
    for entry in project_urls:
        label, _, url = entry.partition(",")
        if re.sub(r"[^a-z]", "", label.lower()) in URL_LABELS and url.strip():
            return url.strip()
    return f"https://pypi.org/project/{norm(name)}/"


def _license_field(raw: str) -> tuple[str, str]:
    text = raw.strip()
    if "\n" in text or len(text) > SHORT_LICENSE:
        ident = identify(text)
        # A long one-liner identify cannot place is kept whole, not cut to 80 chars.
        if "\n" in text or known(ident):
            return ident, "License field (license text)"
    return text, "License field"


def classifier_license(classifiers: list[str]) -> str:
    """'License :: OSI Approved :: MIT License' -> 'MIT License', joined by '; '."""
    tails = [c.split("::")[-1].strip() for c in classifiers if c.strip().startswith("License ::")]
    return "; ".join(t for t in tails if t and t != "OSI Approved")


def choose(header: Any, files: LicenseFiles) -> tuple[str, str] | None:
    """The license the metadata states, as (license, where); None when it states none.

    A License-Expression is final, and so are classifiers once reached: a stale
    "OSI Approved" classifier must never paper over a BUSL expression. Only the
    free-text License field falls through when it is a copyright line or a text
    `identify` cannot place; license files are read only after that.
    """
    expr = (header.get("License-Expression") or "").strip()
    if expr:
        return expr, "License-Expression"
    raw = header.get("License") or ""
    field = _license_field(raw) if raw.strip().lower() not in PLACEHOLDERS else None
    if field and known(field[0]):
        return field
    classified = classifier_license(header.get_all("Classifier") or [])
    if classified:
        return classified, "License classifier"
    found = [(identify(text), f"license file {path}") for path, text in files() if text.strip()]
    return next((c for c in found if known(c[0])), None) or field or next(iter(found), None)


def license_file_names(header: Any) -> list[str]:
    """Paths the metadata's License-File headers name."""
    return [str(p).strip() for p in header.get_all("License-File") or [] if str(p).strip()]


def parse(text: str, origin: str, files: Callable[[Any], list[tuple[str, str]]]) -> Record | None:
    """Record for one METADATA/PKG-INFO text; None when it names no distribution.

    `files(header)` loads the license files beside the metadata; it only runs
    when the header fields alone give no recognised license.
    """
    header = HeaderParser().parsestr(text)
    name = (header.get("Name") or "").strip()
    if not name:
        return None
    chosen = choose(header, lambda: files(header))
    lic, where = chosen or ("", FIELDS)
    return Record(
        name=norm(name),
        version=(header.get("Version") or "").strip(),
        license=lic,
        license_from=f"{where} in {origin}",
        deps=runtime_deps(header.get_all("Requires-Dist") or []),
        url=project_url(header.get("Home-page") or "", header.get_all("Project-URL") or [], name),
        extra_deps=extra_deps(header.get_all("Requires-Dist") or []),
    )
