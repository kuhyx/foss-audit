"""License data inside a cached JAR/AAR, for versions whose POM says nothing.

Read-only and bounded: entries are read one at a time after a size check,
never extracted, and an AAR's nested classes.jar is opened in memory. Only
this artifact's own embedded POM (META-INF/maven/<group>/<artifact>/pom.xml)
counts, and only top-level or META-INF LICENSE/NOTICE files, because a
shaded jar carries the POMs and licenses of everything it bundles.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from foss_audit.own_license import identify
from foss_audit.scan_cache_maven_pom import KNOWN_IDS, parse_pom

LICENSE_ENTRY = re.compile(r"(?i)^(META-INF/)?(licen[cs]e|copying)([._-][^/]*)?$")
NOTICE_ENTRY = re.compile(r"(?i)^(META-INF/)?notice([._-][^/]*)?$")
MAX_ENTRY = 1 << 20
MAX_NESTED = 64 << 20


def _read(archive: zipfile.ZipFile, name: str, limit: int = 0) -> bytes | None:
    """One entry's bytes, or None when it is larger than `limit` (default MAX_ENTRY)."""
    return archive.read(name) if archive.getinfo(name).file_size <= (limit or MAX_ENTRY) else None


def _embedded_pom(archive: zipfile.ZipFile, group: str, artifact: str) -> str:
    """The licenses this artifact's own embedded pom.xml declares, joined."""
    name = f"META-INF/maven/{group}/{artifact}/pom.xml"
    data = _read(archive, name) if name in archive.namelist() else None
    pom = parse_pom(data) if data is not None else None
    return " / ".join(pom.licenses) if pom is not None else ""


def _license_files(archive: zipfile.ZipFile) -> list[str]:
    """LICENSE entries first, then NOTICE ones."""
    names = sorted(archive.namelist())
    return [n for n in names if LICENSE_ENTRY.match(n)] + [n for n in names if NOTICE_ENTRY.match(n)]


def _scan(
    label: str, archive: zipfile.ZipFile, group: str, artifact: str, notes: list[str]
) -> tuple[str, str]:
    embedded = _embedded_pom(archive, group, artifact)
    if embedded:
        return embedded, f"embedded pom in {label}"
    for entry in _license_files(archive):
        data = _read(archive, entry)
        if data is None:
            notes.append(f"{entry} in {label} (too large)")
            continue
        spdx = identify(data.decode("utf-8", errors="replace"))
        if spdx in KNOWN_IDS:
            return spdx, f"{entry} in {label}"
        notes.append(f"{entry} in {label} (unrecognised: {spdx[:60]})")
    return "", ""


def _path_license(path: Path, group: str, artifact: str, notes: list[str]) -> tuple[str, str]:
    """One JAR/AAR, then an AAR's classes.jar (read into memory, size-capped)."""
    with zipfile.ZipFile(path) as outer:
        found = _scan(path.name, outer, group, artifact, notes)
        if found[0] or "classes.jar" not in outer.namelist():
            return found
        data = _read(outer, "classes.jar", MAX_NESTED)
    if data is None:
        notes.append(f"{path.name}!classes.jar (too large)")
        return "", ""
    with zipfile.ZipFile(io.BytesIO(data)) as inner:
        return _scan(f"{path.name}!classes.jar", inner, group, artifact, notes)


def archive_license(paths: list[Path], group: str, artifact: str) -> tuple[str, str]:
    """(license, where it was found), or ("", every place checked)."""
    notes: list[str] = []
    for path in paths:
        try:
            found = _path_license(path, group, artifact, notes)
        except (OSError, zipfile.BadZipFile, EOFError) as exc:
            notes.append(f"{path.name} unreadable ({exc})")
            continue
        if found[0]:
            return found
        notes.append(f"{path.name} (no embedded pom or LICENSE/NOTICE)")
    return "", "; ".join(notes)
