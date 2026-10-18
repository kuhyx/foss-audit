"""Docker remove commands: containers using an image are removed before `docker rmi`."""

from __future__ import annotations

import shutil
import subprocess
from typing import Any

import pytest
from docker_helpers import FakeDocker, install, row

from foss_audit import scan_docker
from foss_audit.curated import Curated, apply

LIC = scan_docker.LICENSE_LABEL


@pytest.fixture
def docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/docker")


def test_containers_using_an_image_are_removed_first(docker: None, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        row("mongo", "latest", "aaa"),
        row("ghcr.io/open-webui/open-webui", "main", "bbb"),
        row("a/free", "1", "ccc"),
    ]
    labels: dict[str, dict[str, str] | None] = {"aaa": {}, "bbb": {}, "ccc": {LIC: "MIT"}}
    containers = {
        "27f074247814": ("mongo-db", "aaa", False),
        "b1ca1bf90fb3": ("open-webui", "bbb", True),
        "c2c2c2c2c2c2": ("webui-old", "bbb", False),
    }
    install(monkeypatch, FakeDocker(rows, labels, containers=containers))
    items = {i.name: i for i in apply(scan_docker.scan_docker(), Curated.load())}
    mongo = items["mongo"]
    assert mongo.removeCommand == "docker rm -f 27f074247814 && docker rmi mongo:latest"
    assert mongo.to_json()["reason"].endswith("; used by container mongo-db")
    webui = items["ghcr.io/open-webui/open-webui"]
    assert webui.removeCommand == (
        "docker rm -f b1ca1bf90fb3 c2c2c2c2c2c2 && docker rmi ghcr.io/open-webui/open-webui:main"
    )
    assert webui.to_json()["reason"].endswith("; used by containers open-webui (RUNNING), webui-old")
    free = items["a/free"]
    assert (free.removeCommand, free.note) == ("docker rmi a/free:1", "")


def test_container_inspect_failure_keeps_plain_rmi(docker: None, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeDocker(
        [row("a/free", "1", "ccc")], {"ccc": {LIC: "MIT"}}, containers={"dead": ("x", "ccc", True)}
    )

    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        if cmd[1] == "container":
            return subprocess.CompletedProcess(cmd, 1, "", "boom")
        return fake(cmd, **kw)

    monkeypatch.setattr(subprocess, "run", run)
    (item,) = scan_docker.scan_docker()
    assert item.removeCommand == "docker rmi a/free:1"
