"""Docker images without an SPDX label fall back to the licence of their OCI source repository."""

from __future__ import annotations

import shutil

import pytest
from docker_helpers import FakeDocker, install, row

from foss_audit import scan_docker

LIC = scan_docker.LICENSE_LABEL
SRC = "org.opencontainers.image.source"
asked: list[str] = []


def fake_upstream(url: str, ref: str = "") -> tuple[str, str]:
    asked.append(url)
    return ("MIT", "upstream tree") if "licensed" in url else ("", "upstream: no license file")


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    asked.clear()
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(scan_docker, "upstream_license", fake_upstream)


def scan(monkeypatch: pytest.MonkeyPatch, labels: dict[str, dict[str, str] | None]) -> dict[str, object]:
    rows = [row(f"vendor/{k}", "latest", k) for k in labels]
    install(monkeypatch, FakeDocker(rows, labels))
    return {i.name: i for i in scan_docker.scan_docker()}


def test_source_label_licence_used_when_no_spdx_label(monkeypatch: pytest.MonkeyPatch) -> None:
    items = scan(monkeypatch, {"aaa": {SRC: "https://github.com/x/licensed.git"}})
    item = items["vendor/aaa"]
    assert (item.verdict, item.license) == ("foss", "MIT")  # type: ignore[attr-defined]
    assert asked == ["https://github.com/x/licensed"]


def test_spdx_label_wins_and_skips_the_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    items = scan(monkeypatch, {"aaa": {LIC: "Apache-2.0", SRC: "https://github.com/x/licensed"}})
    assert items["vendor/aaa"].license == "Apache-2.0"  # type: ignore[attr-defined]
    assert asked == []


def test_unlicensed_source_and_missing_source_stay_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    items = scan(monkeypatch, {"aaa": {SRC: "https://github.com/x/bare"}, "bbb": None})
    assert [(i.verdict, i.license) for i in items.values()] == [("nonfree", ""), ("nonfree", "")]  # type: ignore[attr-defined]
    assert asked == ["https://github.com/x/bare"]


def test_curated_image_skips_the_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    labels = {"aaa": {SRC: "https://github.com/x/licensed"}}
    install(monkeypatch, FakeDocker([row("gitlab/gitlab-ce", "latest", "aaa")], labels))
    (item,) = scan_docker.scan_docker()
    assert asked == []
    assert item.license == ""  # curated.json settles it later, apply()
