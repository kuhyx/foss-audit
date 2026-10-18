"""Shared pip-cache test fixtures: archives, metadata, records, and no network."""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from foss_audit import cache_common
from foss_audit.scan_cache_pip_meta import (
    Record,
)

MIT_TEXT = "MIT License\n\nPermission is hereby granted, free of charge, to any person"


def no_files(_header: object) -> list[tuple[str, str]]:
    return []


def meta(name: str = "Demo_Pkg", version: str = "1.0", *headers: str) -> str:
    lines = ["Metadata-Version: 2.4", f"Name: {name}", f"Version: {version}", *headers]
    return "\n".join(lines) + "\n\nLong description, License: ignored.\n"


def wheel(files: dict[str, str]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return out.getvalue()


def sdist(files: dict[str, str]) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as archive:
        for name, text in files.items():
            info = tarfile.TarInfo(name)
            if name.endswith("/"):
                info.type = tarfile.DIRTYPE
                archive.addfile(info)
                continue
            data = text.encode()
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return out.getvalue()


def rec(name: str = "demo", version: str = "1.0", lic: str = "", **kw: object) -> Record:
    fields: dict[str, object] = {"license_from": "METADATA in x", "deps": (), "url": None, **kw}
    return Record(name, version, lic, **fields)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    """Map of url -> response; anything else raises like a failed fetch."""
    responses: dict[str, bytes] = {}

    def fetch(url: str, cache_dir: Path | None = None) -> bytes:
        if url in responses:
            return responses[url]
        raise OSError("HTTP Error 404: Not Found")

    monkeypatch.setattr(cache_common, "fetch_cached", fetch)
    return responses


def legacy(body: bytes, kind: bytes = b"\xc5") -> bytes:
    width = {b"\xc4": 1, b"\xc5": 2, b"\xc6": 4}.get(kind, 2)
    return (
        b"cc=4,\x82\xa8response\x81\xa4body" + kind + len(body).to_bytes(width, "big") + body + b"\xa7headers"
    )


def dist_info(root: Path, name: str, text: str) -> Path:
    folder = root / f"{name}-1.0.dist-info"
    folder.mkdir(parents=True)
    (folder / "METADATA").write_text(text)
    return folder / "METADATA"
