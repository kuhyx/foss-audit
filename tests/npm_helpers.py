"""Shared npm-cache test fixtures: offline remote lookups, lazy file maps, store builders."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import tarfile
from pathlib import Path
from typing import Any

import pytest

from foss_audit import (
    cache_common,
    upstream_license,
)
from foss_audit.scan_cache_npm_cacache import (
    content_path as cache_content_path,
)
from foss_audit.scan_cache_npm_pnpm import content_path

MIT = "MIT License\n\nPermission is hereby granted, free of charge, to any person...\n"
PROPRIETARY = "(c) Acme Corp.\n\nAll rights reserved.\nNo use without a contract.\n"
PUBLIC_DOMAIN = '/*\nAuthor: G\nYear: 2013\n\nThis code is released into the "public domain".\n*/\n'
OFFLINE = "upstream x: fetch failed: offline"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Every remote lookup fails unless a test serves it; calls are recorded."""
    served: dict[str, Any] = {"urls": {}, "upstream": ("", OFFLINE), "asked": []}

    def fetch(url: str) -> bytes:
        served["asked"].append(url)
        if url in served["urls"]:
            return bytes(served["urls"][url])
        raise OSError("offline")

    def lookup(url: str) -> tuple[str, str]:
        served["asked"].append(url)
        return tuple(served["upstream"])  # type: ignore[return-value]

    monkeypatch.setattr(cache_common, "fetch_cached", fetch)
    monkeypatch.setattr(upstream_license, "upstream_license", lookup)
    return served


def files(**texts: str) -> dict[str, Any]:
    """A lazy file map like the stores hand over."""
    return {name.replace("_", "."): (lambda t=text: t) for name, text in texts.items()}


def put(store: Path, data: bytes, mode: int = 0o644) -> bytes:
    digest = hashlib.sha512(data).digest()
    path = content_path(store, digest.hex(), mode)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return digest


def json_files(store: Path, contents: dict[str, bytes]) -> dict[str, Any]:
    return {
        rel: {"integrity": "sha512-" + base64.b64encode(put(store, data)).decode(), "mode": 420}
        for rel, data in contents.items()
    }


def pkg_json(**fields: Any) -> bytes:
    return json.dumps(fields).encode()


def write_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc))


def tgz(members: list[tuple[str, bytes | None]]) -> bytes:
    """A gzipped tarball; a None body makes a directory member."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, body in members:
            info = tarfile.TarInfo(name)
            if body is None:
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
                continue
            info.size = len(body)
            tar.addfile(info, io.BytesIO(body))
    return buf.getvalue()


def cache_entry(cache: Path, key: str, data: bytes | None, raw: str | None = None) -> None:
    """Append an index line for `key` (and its content unless `data` is None)."""
    integrity = None
    if data is not None:
        digest = hashlib.sha512(data).digest()
        integrity = "sha512-" + base64.b64encode(digest).decode()
        path = cache_content_path(cache, integrity)
        assert path is not None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    entry = raw or json.dumps({"key": key, "integrity": integrity, "size": 1}, separators=(",", ":"))
    bucket_id = hashlib.sha256(key.encode()).hexdigest()
    bucket = cache / "index-v5" / bucket_id[:2] / bucket_id[2:4] / bucket_id[4:]
    bucket.parent.mkdir(parents=True, exist_ok=True)
    with bucket.open("a") as out:
        out.write(f"{hashlib.sha1(entry.encode()).hexdigest()}\t{entry}\n")  # noqa: S324


REG = "make-fetch-happen:request-cache:https://registry.npmjs.org/"
