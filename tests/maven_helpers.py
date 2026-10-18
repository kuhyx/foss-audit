"""Fixture builders for the Maven/Gradle cache scanner tests: POMs, jars, caches."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from foss_audit import cache_common

APACHE_TEXT = (
    "                                 Apache License\n                           Version 2.0, January 2004\n"
)
NS = ' xmlns="http://maven.apache.org/POM/4.0.0"'


def pom(
    gav: tuple[str, str, str] = ("g", "a", "1"),
    licenses: tuple[tuple[str, str], ...] = (),
    *,
    parent: tuple[str, str, str] | None = None,
    body: str = "",
    header: str = "",
) -> bytes:
    """A POM: (name, url) licenses, an optional <parent>, raw extra XML."""
    group, artifact, version = gav
    lic = "".join(f"<license><name>{n}</name><url>{u}</url></license>" for n, u in licenses)
    par = (
        f"<parent><groupId>{parent[0]}</groupId><artifactId>{parent[1]}</artifactId>"
        f"<version>{parent[2]}</version></parent>"
        if parent
        else ""
    )
    lics = f"<licenses>{lic}</licenses>" if licenses else ""
    return (
        f'<?xml version="1.0"?>{header}<project{NS}>{par}<groupId>{group}</groupId>'
        f"<artifactId>{artifact}</artifactId><version>{version}</version>{lics}{body}</project>"
    ).encode()


def dep(group: str, artifact: str, version: str = "1", extra: str = "") -> str:
    """One <dependency> element."""
    coord = f"<groupId>{group}</groupId><artifactId>{artifact}</artifactId><version>{version}</version>"
    return f"<dependency>{coord}{extra}</dependency>"


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    """An in-memory zip holding `entries`."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buf.getvalue()


def write(path: Path, data: bytes) -> Path:
    """`data` at `path`, parents created."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def gradle_file(root: Path, gav: tuple[str, str, str], name: str, data: bytes) -> Path:
    """files-2.1/<group>/<artifact>/<version>/<sha1>/<name>."""
    return write(root / gav[0] / gav[1] / gav[2] / "0123abcd" / name, data)


def m2_file(root: Path, gav: tuple[str, str, str], suffix: str, data: bytes) -> Path:
    """repository/<group path>/<artifact>/<version>/<artifact>-<version><suffix>."""
    group, artifact, version = gav
    return write(root.joinpath(*group.split("."), artifact, version, f"{artifact}-{version}{suffix}"), data)


def offline(monkeypatch: pytest.MonkeyPatch, pages: dict[str, bytes] | None = None) -> list[str]:
    """Replace the network: `pages` answer, every other URL raises; returns the URLs asked."""
    asked: list[str] = []
    answers = pages or {}

    def fake(url: str, cache_dir: Path = cache_common.HTTP_CACHE) -> bytes:
        asked.append(url)
        if url in answers:
            return answers[url]
        raise OSError(f"offline {url}")

    monkeypatch.setattr(cache_common, "fetch_cached", fake)
    return asked
