"""Read every package of the pnpm content-addressable store(s).

Layouts (all under ~/.local/share/pnpm/store/):
- v3: `files/<xx>/<hash>-index.json`; v10: `index/<xx>/<hash>-<name>@<ver>.json`;
  git-hosted packages of both: `<url-dir>/integrity.json`. Each is JSON with
  `name`, `version` and `files: {path: {integrity: "sha512-<b64>", mode}}`.
- v11: `index.db`, SQLite `package_index(key, data)` whose blobs are msgpack
  (scan_cache_npm_msgpack) with `files: {path: {digest: <hex>, mode}}`.
A file's bytes live in `files/<hex[:2]>/<hex[2:]>`, with "-exec" appended
when its mode is executable. The store is read-only to us: the database is
opened with `mode=ro` (a live -wal is read, never checkpointed). Packages are
read on a bounded thread pool, so their upstream-repository lookups (a git
fetch each) overlap.
"""

from __future__ import annotations

import base64
import binascii
import json
import sqlite3
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from foss_audit import progress
from foss_audit.scan_cache_npm_manifest import Files, Found, found, unreadable
from foss_audit.scan_cache_npm_msgpack import unpackb

STORE = Path.home() / ".local/share/pnpm/store"
TEXT_LIMIT = 256 * 1024
EXEC_BITS = 0o111
READ_WORKERS = 16
SOURCE = "npm-cache"


def content_path(store: Path, hex_digest: str, mode: int) -> Path:
    """Where the store keeps the bytes of one file."""
    suffix = "-exec" if mode & EXEC_BITS else ""
    return store / "files" / hex_digest[:2] / f"{hex_digest[2:]}{suffix}"


def entry_hex(entry: dict[str, Any]) -> str:
    """Hex sha512 of a `files` entry: v11 stores `digest`, older ones `integrity`."""
    if isinstance(entry.get("digest"), str):
        return str(entry["digest"])
    integrity = str(entry.get("integrity", ""))
    try:
        return base64.b64decode(integrity.partition("-")[2], validate=True).hex()
    except binascii.Error:
        return ""


def _reader(path: Path) -> Callable[[], str]:
    def read() -> str:
        try:
            return path.read_bytes()[:TEXT_LIMIT].decode(errors="replace")
        except OSError:
            return ""

    return read


def package(store: Path, files: dict[str, Any], name: str, version: str) -> Found | None:
    """The Found for one store index entry (None when it names no package)."""
    where = f"pnpm store {store.name}"
    paths = {
        rel: content_path(store, entry_hex(entry), int(entry.get("mode", 0)))
        for rel, entry in files.items()
        if "/" not in rel and isinstance(entry, dict)
    }
    manifest = paths.pop("package.json", None)
    try:
        data = json.loads(manifest.read_bytes()) if manifest else {}
    except (OSError, ValueError) as exc:
        return unreadable(name, version, where, str(exc)) if name else None
    if not isinstance(data, dict):
        data = {}
    if not (data.get("name") or name):
        return None
    readers: Files = {rel: _reader(p) for rel, p in paths.items()}
    result = found(data, readers, name, version, where)
    if manifest is None:
        result.cached.license_from += "; index lists no package.json"
    return result


def _json_entries(store: Path) -> Iterator[dict[str, Any]]:
    patterns = ("index/*/*.json", "files/*/*-index.json", "*/integrity.json")
    for pattern in patterns:
        for path in sorted(store.glob(pattern)):
            try:
                doc = json.loads(path.read_bytes())
            except OSError, ValueError:
                continue
            if isinstance(doc, dict) and isinstance(doc.get("files"), dict):
                yield doc


def _db_entries(store: Path) -> Iterator[dict[str, Any]]:
    db = store / "index.db"
    if not db.is_file():
        return
    conn = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT key, data FROM package_index").fetchall()
    finally:
        conn.close()
    for key, blob in rows:
        try:
            doc = unpackb(bytes(blob))
        except ValueError:
            continue
        if isinstance(doc, dict) and isinstance(doc.get("files"), dict):
            # The key is "<integrity>\t<name>@<version>" (or a git URL).
            manifest = doc.get("manifest")
            meta: dict[str, Any] = manifest if isinstance(manifest, dict) else {}
            spec = str(key).rpartition("\t")[2]
            at = spec.rfind("@")
            guess = spec[:at] if at > 0 and "://" not in spec else ""
            yield {"name": meta.get("name") or guess, "version": meta.get("version") or "", **doc}


def _read(job: tuple[Path, dict[str, Any]]) -> Found | None:
    store, doc = job
    read = package(store, doc["files"], str(doc.get("name") or ""), str(doc.get("version") or ""))
    progress.counter(SOURCE).advance()
    return read


def scan_pnpm_store(root: Path | None = None) -> list[Found]:
    """Every package version in every pnpm store version under `root` (STORE)."""
    jobs = [
        (store, doc)
        for store in sorted(p for p in (root or STORE).glob("v*") if p.is_dir())
        for doc in [*_json_entries(store), *_db_entries(store)]
    ]
    progress.counter(SOURCE).add_total(len(jobs))
    with ThreadPoolExecutor(READ_WORKERS) as pool:
        return [item for item in pool.map(_read, jobs) if item is not None]
