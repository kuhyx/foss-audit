"""The license of a cached Dart package, read from the package's own files.

pubspec.yaml has no license field, so the text decides: the package dir's
LICENSE/COPYING/UNLICENSE, else (a package inside a git monorepo) the nearest
one up to the checkout root, else a "licensed under the X License" line in its
README. `own_license.identify` names the common texts; PHRASES below adds the
ones it does not know, and version/clause detail is added for GPL and BSD.
Flutter's "TODO: Add your license here." template is no license at all and is
skipped, so a monorepo's root LICENSE still applies.

Files are untrusted cache content: read-only, size-capped, never executed.
"""

from __future__ import annotations

import re
from pathlib import Path

from foss_audit.own_license import LICENSE_FILE, TEXT_IDS, identify

MAX_READ = 256 * 1024
KNOWN_IDS = frozenset(spdx for _, spdx in TEXT_IDS)
# LICENSE_FILE starts at "licen", so the Unlicense's own file name needs adding.
UNLICENSE_FILE = re.compile(r"(?i)^unlicen[cs]e([.-].*)?$")
PLACEHOLDER = re.compile(r"(?i)^\s*TODO:? add your license here")
POINTER = re.compile(r"(?i)^\s*see (?:the )?([\w.-]+) file\.?\s*$")
README_LINE = re.compile(r"(?i)licen[cs]ed under (?:the )?(?:terms of the )?([\w.+\- ]{2,40}?) licen[cs]e")
MARKUP = re.compile(r"<[^>]+>|&\w+;")
# Texts own_license.identify does not know, by a phrase only that text has.
# Syncfusion's packages are community-or-commercial licensed, not free.
PHRASES = (
    ("Syncfusion Community License", "LicenseRef-Syncfusion-Community-or-commercial"),
    ("CC0 1.0 Universal", "CC0-1.0"),
    ("Boost Software License", "BSL-1.0"),
)
GNU_VERSION = re.compile(r"(?i)\bversion (\d(?:\.\d)?)\b")
NO_LICENSE_FIELD = "pub has no license field"


def read(path: Path) -> str:
    """At most MAX_READ characters of a cache file."""
    with path.open(errors="replace") as handle:
        return handle.read(MAX_READ)


def _refine(spdx: str, text: str) -> str:
    """Add the clause count to BSD and the version to the GNU licenses."""
    if spdx == "BSD":
        lower = text.lower()
        if "advertising materials" in lower:
            return "BSD-4-Clause"
        # Clause 3 forbids using the names "to endorse or promote" (worded
        # "Neither the name..." or "The names ... may not be used...").
        return "BSD-3-Clause" if "endorse or promote" in lower else "BSD-2-Clause"
    found = GNU_VERSION.search(text[:1000]) if spdx in {"GPL", "LGPL"} else None
    if found:
        number = found.group(1)
        return f"{spdx}-{number if '.' in number else number + '.0'}"
    return spdx


def recognise(text: str) -> str:
    """SPDX-ish id of a license text, its cleaned first line when unknown, "" for none."""
    if not text.strip() or PLACEHOLDER.match(text):
        return ""
    found = identify(text)
    if found in KNOWN_IDS:
        return _refine(found, text)
    plain = MARKUP.sub("", text).lower()
    for phrase, spdx in PHRASES:
        if phrase.lower() in plain:
            return spdx
    return found.lstrip("#").strip()


def license_files(directory: Path) -> list[Path]:
    """LICENSE* before COPYING* before UNLICENSE*, each group alphabetical."""
    names = [p for p in directory.glob("*") if LICENSE_FILE.match(p.name) or UNLICENSE_FILE.match(p.name)]
    order = ("licen", "copying", "unlicen")
    files = [p for p in names if p.is_file()]
    return sorted(
        files, key=lambda p: (next(i for i, o in enumerate(order) if p.name.lower().startswith(o)), p.name)
    )


def _from_file(path: Path) -> tuple[str, str]:
    """(license, where) of one license file; a "See X file." pointer is followed once."""
    text = read(path)
    pointer = POINTER.match(text)
    target = path.parent / pointer.group(1) if pointer else None
    if target is not None and target.is_file():
        return recognise(read(target)), f" -> {target.name}"
    return recognise(text), ""


def _readme(directory: Path) -> str:
    readme = directory / "README.md"
    found = README_LINE.search(read(readme)) if readme.is_file() else None
    return found.group(1).strip() if found else ""


def resolve(package: Path, stop: Path) -> tuple[str, str]:
    """(license, license_from) for a package dir; `stop` is the checkout root.

    When nothing is found the license is "" and license_from names every place
    that was checked.
    """
    checked: list[str] = []
    skipped = ""
    ups = len(package.relative_to(stop).parts)
    for depth, directory in enumerate([package, *package.parents][: ups + 1]):
        rel = directory.relative_to(stop)
        for path in license_files(directory):
            lic, via = _from_file(path)
            if lic:
                return lic, f"{'../' * depth}{path.name} file{via}"
            skipped = f" (placeholder {path.name} skipped)"
        checked.append(stop.name if rel == Path() else f"{stop.name}/{rel}")
    readme = _readme(package)
    if readme:
        return readme, "README.md"
    places = f"LICENSE/COPYING/UNLICENSE in {', '.join(checked)}{skipped}"
    return "", f"{places}, README.md, pubspec.yaml ({NO_LICENSE_FIELD})"
