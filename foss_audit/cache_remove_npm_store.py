"""Exact npm-cache entries of one package: npm's _cacache and the pnpm stores.

- _cacache: `npm cache clean --cache ~/.npm <key>` per tarball key (npm 11
  deletes that index entry and its content, and stops at the first key it
  cannot find, so every key gets its own call). Several keys of one tarball
  (`make-fetch-happen:request-cache:<url>` and `pacote:tarball:<spec>`) share
  the content: the first is cleaned, the others' index buckets
  (`index-v5/<sha256(key)>`, one key each) are deleted, or they would dangle.
- pnpm v3/v10 stores: the package's index JSON, or the `<url-dir>/` of a
  git-hosted package; v11: its exact `package_index` rows, deleted with
  sqlite3, plus `links/<name>` (the global virtual store). pnpm has no
  per-package store command (`pnpm store prune` is store-wide); content blobs
  are shared between packages, so they are left for prune. pnpm refetches a
  package whose index entry is gone.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import sqlite3
from functools import partial
from pathlib import Path
from typing import Any

from foss_audit import memo
from foss_audit.cache_remove import joined, rm, shell_path
from foss_audit.scan_cache_npm_cacache import Tarball, read_tarball, tarballs
from foss_audit.scan_cache_npm_memo import memoised
from foss_audit.scan_cache_npm_msgpack import unpackb


def bucket(cache: Path, key: str) -> Path:
    """The index bucket file cacache keeps `key` in."""
    h = hashlib.sha256(key.encode()).hexdigest()
    return cache / "index-v5" / h[:2] / h[2:4] / h[4:]


def _json_name(path: Path) -> str:
    try:
        doc = json.loads(path.read_bytes())
    except OSError, ValueError:
        return ""
    return str(doc.get("name") or "") if isinstance(doc, dict) else ""


def _remembered_name(readings: memo.Memo, path: Path) -> str:
    key = f"name|{memo.stat_key(path)}"
    hit = readings.get(key)
    if hit is None:
        hit = _json_name(path)
        readings.put(key, hit)
    return str(hit)


def _row_name(key: str, blob: bytes) -> str:
    """Package name of a v11 index row: from "<integrity>\\t<name>@<ver>", else its manifest."""
    spec = key.partition("\t")[2]
    at = spec.rfind("@")
    if at > 0 and "://" not in spec:
        return spec[:at]
    try:
        doc: Any = unpackb(blob)
    except ValueError:
        return ""
    manifest = doc.get("manifest") if isinstance(doc, dict) else None
    return str(manifest.get("name") or "") if isinstance(manifest, dict) else ""


def _literal(key: str) -> str:
    """A SQL literal for a key that holds tabs (written as char(9))."""
    return " || char(9) || ".join("'" + part.replace("'", "''") + "'" for part in key.split("\t"))


class NpmCache:
    """Every cache entry per package name, built once per scan."""

    def __init__(
        self,
        cacache: Path,
        store: Path,
        readings: memo.Memo = memo.NO_MEMO,
        tarballs_: list[Tarball] | None = None,
    ) -> None:
        self.clean: dict[str, list[str]] = {}
        self.paths: dict[str, list[Path]] = {}
        self.rows: dict[str, dict[Path, list[str]]] = {}
        self._readings = readings
        self._cacache(cacache, list(tarballs(cacache)) if tarballs_ is None else tarballs_)
        for version in sorted(p for p in store.glob("v*") if p.is_dir()):
            self._store(version)

    def _cacache(self, cache: Path, cached: list[Tarball]) -> None:
        shared: dict[tuple[str, str], list[str]] = {}
        for tarball in cached:
            name = tarball.name
            if not name:  # a git archive: the name is in its package.json (read once, memoized)
                key = f"cacache|{tarball.integrity}||"
                found = memoised(self._readings, key, partial(read_tarball, tarball.path, "", ""))
                name = found.name if found else ""
            if name:
                shared.setdefault((name, tarball.integrity), []).append(tarball.key)
        where = shell_path(cache.parent)
        for (name, _), (first, *rest) in shared.items():
            self.clean.setdefault(name, []).append(f"npm cache clean --cache {where} {shlex.quote(first)}")
            self.paths.setdefault(name, []).extend(bucket(cache, key) for key in rest)

    def _add(self, name: str, path: Path) -> None:
        if name:
            self.paths.setdefault(name, []).append(path)

    def _store(self, store: Path) -> None:
        for pattern in ("index/*/*.json", "files/*/*-index.json"):
            for path in sorted(store.glob(pattern)):
                self._add(_remembered_name(self._readings, path), path)
        for path in sorted(store.glob("*/integrity.json")):
            self._add(_remembered_name(self._readings, path), path.parent)
        for scope in sorted((store / "links").glob("*")):
            names = sorted(scope.glob("*")) if scope.name.startswith("@") else [scope]
            for folder in names:
                self._add(str(folder.relative_to(store / "links")), folder)
        db = store / "index.db"
        if db.is_file():
            conn = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
            try:
                rows = conn.execute("SELECT key, data FROM package_index ORDER BY key").fetchall()
            finally:
                conn.close()
            for key, blob in rows:
                name = _row_name(str(key), bytes(blob))
                if name:
                    self.rows.setdefault(name, {}).setdefault(db, []).append(str(key))

    def step(self, name: str) -> tuple[str, str]:
        """Every command deleting `name`'s cache entries."""
        sql = [
            f"sqlite3 {shell_path(db)} "
            + shlex.quote(f"DELETE FROM package_index WHERE key IN ({', '.join(map(_literal, keys))})")
            for db, keys in self.rows.get(name, {}).items()
        ]
        return joined([*self.clean.get(name, []), *sql, rm(self.paths.get(name, []))]), ""
