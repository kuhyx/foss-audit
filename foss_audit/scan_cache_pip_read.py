"""Read cached wheels, sdists and metadata bodies of pip's and uv's caches.

Caches are untrusted: everything is opened read-only, nothing is extracted to
disk, imported or executed, and every member read is capped. A wheel is a zip,
so `zipfile` reads only its central directory plus the METADATA member (a
300 MB torch wheel costs a few kB); an sdist tar is streamed and dropped as
soon as its top-level PKG-INFO (and, if needed, a license file) has been seen.
"""

from __future__ import annotations

import gzip
import io
import re
import tarfile
import zipfile
import zlib
from dataclasses import replace
from pathlib import Path
from typing import IO, Any

from foss_audit import upstream_license
from foss_audit.own_license import LICENSE_FILE, declared_license, repo_root
from foss_audit.scan_cache_pip_meta import Record, known, license_file_names, norm, parse

# No metadata or license file worth reading is bigger than this.
MAX_MEMBER = 1 << 20
ZIP_MAGIC = b"PK\x03\x04"
GZIP_MAGIC = b"\x1f\x8b"
META_MAGIC = b"Metadata-Version"
# A gzip body starting like this is a compressed JSON/HTML index page.
INDEX_START = (b"{", b"<", b"[")
# Errors a truncated or hostile archive raises; such a body is counted as bad.
BAD_ARCHIVE = (OSError, zipfile.BadZipFile, tarfile.TarError, EOFError, zlib.error, ValueError)
WHEEL_META = re.compile(r"^[^/]+\.dist-info/METADATA$")
SDIST_META = re.compile(r"^[^/]+/PKG-INFO$")
# Legacy pip http cache: "cc=4," + msgpack {"response": {"body": <bin>, ...}}.
MSGPACK_BODY = b"\xa4body"
BIN_LEN = {0xC4: 1, 0xC5: 2, 0xC6: 4}
# Absolute source paths an editable install's .pth / finder module points at.
EDITABLE_PATH = re.compile(r"""(?:^|['"])(/[^'"\n]+)""", re.MULTILINE)


def _text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def is_license_file(rel: str, header: Any) -> bool:
    """A path (relative to the metadata's directory) that holds a license text."""
    return rel in license_file_names(header) or rel.startswith("licenses/") or bool(LICENSE_FILE.match(rel))


def _zip_record(archive: zipfile.ZipFile, origin: str) -> Record | None:
    names = archive.namelist()
    meta = next((n for n in names if WHEEL_META.match(n)), None) or next(
        (n for n in names if SDIST_META.match(n)), None
    )
    if meta is None:
        return None
    base = meta.rsplit("/", 1)[0] + "/"

    def read(name: str) -> str:
        with archive.open(name) as member:
            return _text(member.read(MAX_MEMBER))

    def files(header: Any) -> list[tuple[str, str]]:
        inside = [n for n in names if n.startswith(base) and not n.endswith("/")]
        return [(n, read(n)) for n in inside if is_license_file(n.removeprefix(base), header)]

    record = parse(read(meta), origin, files)
    only_meta = WHEEL_META.match(meta) is not None and all(n.startswith(base) for n in names)
    return replace(record, meta=True) if record and only_meta else record


def _peek(meta: str) -> str:
    """The license a PKG-INFO settles on without any license file."""
    record = parse(meta, "", lambda _header: [])
    return record.license if record else ""


def _tar_record(stream: IO[bytes], origin: str) -> Record | None:
    meta: str | None = None
    found: list[tuple[str, str]] = []
    with tarfile.open(fileobj=stream, mode="r|*") as archive:
        for member in archive:
            parts = member.name.removeprefix("./").split("/")
            is_meta = parts[1:] == ["PKG-INFO"]
            if not member.isfile() or len(parts) != 2 or not (is_meta or LICENSE_FILE.match(parts[1])):
                continue
            data = _text((archive.extractfile(member) or io.BytesIO()).read(MAX_MEMBER))
            if is_meta:
                meta = data
            else:
                found.append((member.name, data))
            if meta is not None and (found or known(_peek(meta))):
                break
    return parse(meta, origin, lambda _header: found) if meta is not None else None


def records_from(data: IO[bytes], origin: str) -> list[Record] | None:
    """Records in one body by its magic bytes; [] when it is no distribution, None when corrupt."""
    head = data.read(len(META_MAGIC))
    data.seek(0)
    try:
        if head.startswith(ZIP_MAGIC):
            with zipfile.ZipFile(data) as archive:
                record = _zip_record(archive, origin)
        elif head.startswith(GZIP_MAGIC):
            if gzip.GzipFile(fileobj=data).read(64).lstrip().startswith(INDEX_START):
                return []
            data.seek(0)
            record = _tar_record(data, origin)
        elif head == META_MAGIC:
            record = parse(_text(data.read(MAX_MEMBER)), origin, lambda _header: [])
        else:
            return []
    except BAD_ARCHIVE:
        return None
    return [record] if record else []


def read_body(path: Path, origin: str) -> list[Record] | None:
    """Records in one cached response body or wheel file."""
    try:
        with path.open("rb") as handle:
            return records_from(handle, origin)
    except OSError:
        return None


def read_legacy(path: Path, origin: str) -> list[Record] | None:
    """Records in a legacy pip http cache entry (body inside a msgpack map)."""
    try:
        blob = path.read_bytes()
    except OSError:
        return None
    key = blob.find(MSGPACK_BODY)
    at = key + len(MSGPACK_BODY)
    width = BIN_LEN.get(blob[at], 0) if key >= 0 and at < len(blob) else 0
    if not width:
        return []
    size = int.from_bytes(blob[at + 1 : at + 1 + width], "big")
    return records_from(io.BytesIO(blob[at + 1 + width : at + 1 + width + size]), origin)


def editable_sources(root: Path, name: str) -> list[Path]:
    """Source dirs the editable install of `name` at `root` points at (read as text, never run)."""
    candidates = sorted([*root.glob("*.pth"), *root.glob("__editable__*.py")])
    pointers = [p for p in candidates if name in norm(p.stem)]
    paths = [Path(m) for p in pointers for m in EDITABLE_PATH.findall(_text(p.read_bytes()[:MAX_MEMBER]))]
    # A finder maps a module either to its package dir or to a module path minus ".py".
    dirs = [p if p.is_dir() else p.parent for p in paths]
    return [d for d in dict.fromkeys(dirs) if d.is_dir() and d != Path("/")]


def from_editable(record: Record, root: Path) -> Record:
    """An editable install's license, read from the source tree it points at."""
    sources = editable_sources(root, record.name)
    for source in sources:
        try:
            lic = declared_license(source, repo_root(source) or source)
        except OSError, ValueError:
            continue
        if lic.strip():
            where = f"LICENSE of editable source {source}"
            return replace(record, license=lic, license_from=where, local=True)
    if not sources:
        return record
    for checkout in dict.fromkeys(r for r in map(repo_root, sources) if r is not None):
        lic, where = upstream_license.local_readme_license(checkout)
        if lic:
            return replace(record, license=lic, license_from=where, local=True)
    tried = ", ".join(map(str, sources))
    return replace(
        record, license_from=f"{record.license_from}; no license in editable source {tried}", local=True
    )


def read_dist_dir(meta: Path, origin: str) -> list[Record] | None:
    """Record of an unpacked METADATA/PKG-INFO; license files sit beside it or in licenses/."""
    folder = meta.parent

    def files(header: Any) -> list[tuple[str, str]]:
        found = [*sorted(folder.glob("*")), *sorted(folder.glob("licenses/**/*"))]
        hits = [p for p in found if p.is_file() and is_license_file(str(p.relative_to(folder)), header)]
        return [(p.name, _text(p.read_bytes()[:MAX_MEMBER])) for p in hits]

    try:
        record = parse(_text(meta.read_bytes()[:MAX_MEMBER]), origin, files)
        if record and all(p.name.endswith(".dist-info") for p in folder.parent.iterdir()):
            record = replace(record, meta=True)
        if record and not record.license:
            record = from_editable(record, folder.parent)
    except OSError:
        return None
    return [record] if record else []
