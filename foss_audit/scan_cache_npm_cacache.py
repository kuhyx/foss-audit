"""Read every package tarball in npm's cache (~/.npm/_cacache).

`index-v5/<xx>/<yy>/<rest>` bucket files hold one "<sha1>\\t<json>" line per
write; the last line of a key wins and a null `integrity` is a deletion. A
`make-fetch-happen:request-cache:<url>` key whose URL is a tarball
(`.../<name>/-/<base>-<version>.tgz`, or a codeload.github.com git archive)
points at `content-v2/<algo>/<hex[:2]>/<hex[2:4]>/<hex[4:]>`. Packuments
(registry JSON documents) are metadata, not packages, and are skipped.

Tarballs are untrusted: streamed (`r|gz`), never extracted; only the top-level
package.json, LICENSE* and README* members are read. Reading stops at
package.json when it already declares a license. Tarballs are read on a
bounded thread pool, so a package's upstream-repository lookup (a git fetch)
overlaps the others'.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import tarfile
import zlib
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import unquote

from foss_audit import memo, progress
from foss_audit.scan_cache_npm_manifest import (
    LICENSE_NAME,
    README_FILE,
    SEE_FILE,
    Found,
    found,
    manifest_license,
    unreadable,
)
from foss_audit.scan_cache_npm_memo import memoised

CACACHE = Path.home() / ".npm/_cacache"
REQUEST_CACHE = "make-fetch-happen:request-cache:"
PACOTE = "pacote:tarball:"
TARBALL_LINE = re.compile(
    r'"key":"(?:pacote:tarball:|make-fetch-happen:request-cache:[^"]*(?:\.tgz|codeload))'
)
PACOTE_SPEC = re.compile(r"^(?P<name>(?:@[^/@]+/)?[^@/:]+)@(?P<version>[^/:@]+)$")
TARBALL_URL = re.compile(r"^https?://[^/]+/(?P<name>.+?)/-/(?:@[^/]+/)?(?P<file>[^/]+)\.tgz$")
TEXT_LIMIT = 256 * 1024
WHERE = "npm _cacache tarball"
READ_WORKERS = 16
SOURCE = "npm-cache"
READ_ERRORS = (OSError, EOFError, ValueError, tarfile.TarError, zlib.error)


def index_entries(cache: Path) -> dict[str, dict[str, Any]]:
    """key -> newest live index entry, over every bucket file."""
    entries: dict[str, dict[str, Any]] = {}
    for bucket in sorted((cache / "index-v5").glob("*/*/*")):
        try:
            lines = bucket.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            # Most lines are packuments and audit results; skip them unparsed.
            if not TARBALL_LINE.search(line):
                continue
            try:
                entry = json.loads(line.partition("\t")[2])
            except ValueError:
                continue
            if isinstance(entry, dict) and isinstance(entry.get("key"), str):
                entries[entry["key"]] = entry
    return {k: e for k, e in entries.items() if e.get("integrity")}


def content_path(cache: Path, integrity: str) -> Path | None:
    """Content file of an SRI string ("sha512-<b64>"; the first hash if several)."""
    algo, _, digest = integrity.split(maxsplit=1)[0].partition("-")
    try:
        hex_digest = base64.b64decode(digest, validate=True).hex()
    except binascii.Error:
        return None
    if not algo or not hex_digest:
        return None
    return cache / "content-v2" / algo / hex_digest[:2] / hex_digest[2:4] / hex_digest[4:]


def tarball_spec(url: str) -> tuple[str, str] | None:
    """(name, version) a tarball URL names; ("", "") for a git archive; None if no tarball."""
    match = TARBALL_URL.match(url)
    if match:
        name = unquote(match["name"])
        base = name.rpartition("/")[2] + "-"
        file = match["file"]
        return name, file.removeprefix(base) if file.startswith(base) else ""
    return ("", "") if url.startswith("https://codeload.github.com/") else None


def key_spec(key: str) -> tuple[str, str] | None:
    """(name, version) of a tarball index key ("" when only package.json knows), None if no tarball.

    pacote keys are "pacote:tarball:<name>@<version>", or a git/file spec.
    """
    if key.startswith(PACOTE):
        match = PACOTE_SPEC.match(key.removeprefix(PACOTE))
        return (match["name"], match["version"]) if match else ("", "")
    return tarball_spec(key.removeprefix(REQUEST_CACHE)) if key.startswith(REQUEST_CACHE) else None


def _members(path: Path) -> tuple[dict[str, Any] | None, dict[str, str]]:
    """(package.json, top-level LICENSE*/README* texts) of a tarball."""
    data: dict[str, Any] | None = None
    texts: dict[str, str] = {}
    with tarfile.open(path, mode="r|gz") as archive:
        for member in archive:
            parts = member.name.removeprefix("./").split("/")
            if len(parts) != 2 or not member.isfile():
                continue
            base = parts[1]
            wanted = base == "package.json" or LICENSE_NAME.match(base) or README_FILE.match(base)
            stream = archive.extractfile(member) if wanted else None
            if stream is None:
                continue
            if base != "package.json":
                texts[base] = stream.read(TEXT_LIMIT).decode(errors="replace")
                continue
            # Never truncated: a cut package.json would read as unreadable.
            parsed = json.loads(stream.read())
            data = parsed if isinstance(parsed, dict) else {}
            field = manifest_license(data)
            if field and not SEE_FILE.match(field):
                break
    return data, texts


def read_tarball(path: Path, name: str, version: str) -> Found | None:
    """The Found for one cached tarball (None for a nameless git archive)."""
    try:
        data, texts = _members(path)
    except READ_ERRORS as exc:
        return unreadable(name, version, WHERE, f"{type(exc).__name__}: {exc}") if name else None
    if data is None:
        return unreadable(name, version, WHERE, "tarball has no package.json") if name else None
    if not (data.get("name") or name):
        return None
    files = {base: (lambda text=text: text) for base, text in texts.items()}
    return found(data, files, name, version, WHERE)


class Tarball(NamedTuple):
    """One index key that points at a tarball present in the cache."""

    key: str
    name: str
    version: str
    path: Path
    integrity: str


def tarballs(cache: Path) -> Iterator[Tarball]:
    """Each cached tarball, by index key."""
    for key, entry in sorted(index_entries(cache).items()):
        spec = key_spec(key)
        path = content_path(cache, str(entry["integrity"]))
        if spec is not None and path is not None and path.is_file():
            yield Tarball(key, spec[0], spec[1], path, str(entry["integrity"]))


def _read_job(job: Tarball, store_memo: memo.Memo) -> Found | None:
    # The content is addressed by its integrity; name and version are the index key's.
    key = f"cacache|{job.integrity}|{job.name}|{job.version}"
    found = memoised(store_memo, key, lambda: read_tarball(job.path, job.name, job.version))
    progress.counter(SOURCE).advance()
    return found


def scan_cacache(
    skip: set[tuple[str, str]],
    cache: Path | None = None,
    store_memo: memo.Memo = memo.NO_MEMO,
    cached: list[Tarball] | None = None,
) -> list[Found]:
    """Every package tarball in `cache` (CACACHE, or the listing `cached`) not in `skip` (name, version)."""
    todo: list[Tarball] = []
    seen: set[tuple[str, str]] = set()
    for tarball in tarballs(cache or CACACHE) if cached is None else cached:
        spec = (tarball.name, tarball.version)
        if not (tarball.name and tarball.version and (spec in skip or spec in seen)):
            todo.append(tarball)
            seen.add(spec)
    progress.counter(SOURCE).add_total(len(todo))
    with ThreadPoolExecutor(READ_WORKERS) as pool:
        read = list(pool.map(partial(_read_job, store_memo=store_memo), todo))
    results: list[Found] = []
    for (_, name, version, _, _), item in zip(todo, read, strict=True):
        # As if read in order: a version an earlier tarball turned out to hold is skipped.
        if item is None or (name and version and (name, version) in skip):
            continue
        results.append(item)
        skip.add((item.name, item.cached.version))
    return results
