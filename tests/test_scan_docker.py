"""Docker image scanner: grouping, skipping own images, label licenses, curated fallbacks."""

from __future__ import annotations

import shutil
import subprocess

import pytest
from docker_helpers import FakeDocker, install, row

from foss_audit import scan_docker
from foss_audit.curated import Curated, apply

LIC = scan_docker.LICENSE_LABEL
SRC = "org.opencontainers.image.source"
URL = "org.opencontainers.image.url"


@pytest.fixture
def docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/docker")


def test_no_docker_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: None)
    assert scan_docker.scan_docker() == []


def test_daemon_unreachable_or_slow(docker: None, monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, FakeDocker([row("a/b", "1", "aaa")], {}, images_rc=1))
    assert scan_docker.scan_docker() == []

    def hang(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(subprocess, "run", hang)
    assert scan_docker.scan_docker() == []

    def gone(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", gone)
    assert scan_docker.scan_docker() == []


def test_only_own_or_dangling_images_means_no_inspect(docker: None, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = install(
        monkeypatch,
        FakeDocker(
            [row("x/y", "local", "aaa"), row("<none>", "<none>", "bbb"), row("yay-mcp", "1", "ccc")], {}
        ),
    )
    assert scan_docker.scan_docker() == []
    assert fake.inspect_calls == []


def test_groups_tags_batches_inspect_and_skips_own(docker: None, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        row("confluentinc/cp-kafka", "latest", "aaa"),
        row("confluentinc/cp-kafka", "7.3.2", "bbb"),
        row("adguard/adguardhome", "latest", "ccc"),
        row("adguard/adguardhome", "stable", "ccc"),
        row("ghcr.io/kuhyx/thing", "1", "ddd"),
        row("kuhyx/thing", "1", "ddd"),
        row("syncthing-kuhy", "local", "eee"),
        row("wintrchess-app", "latest", "fff"),
        row("flink-playground-taskmanager", "latest", "ggg"),
        row("redis", "8-alpine", "hhh"),
        row("somebody/tagless", "<none>", "iii"),
        row("someapp", "2", "jjj"),
        row("mine", "1", "kkk"),
    ]
    labels: dict[str, dict[str, str] | None] = {
        "aaa": None,
        "bbb": {},
        "ccc": {
            LIC: "GPL-3.0",
            SRC: "https://github.com/AdguardTeam/AdGuardHome.git",
            URL: "https://adguard.com",
        },
        "fff": {},
        "ggg": {SRC: "https://github.com/kuhyx/flink-playground"},
        "hhh": {},
        "iii": {URL: "https://example.org"},
        "jjj": {SRC: "https://github.com/other/someapp", LIC: "NOASSERTION"},
        "kkk": {SRC: "https://github.com/kuhyx/mine", URL: "https://github.com/kuhyx/mine"},
    }
    fake = install(monkeypatch, FakeDocker(rows, labels))
    items = {i.name: i for i in scan_docker.scan_docker()}
    assert len(fake.inspect_calls) == 1
    assert set(items) == {
        "adguard/adguardhome",
        "confluentinc/cp-kafka",
        "redis",
        "somebody/tagless",
        "someapp",
    }
    kafka = items["confluentinc/cp-kafka"]
    assert (kafka.source, kafka.id) == ("docker", "docker:confluentinc/cp-kafka")
    assert kafka.version == "7.3.2, latest"
    assert kafka.removeCommand == "docker rmi confluentinc/cp-kafka:7.3.2 confluentinc/cp-kafka:latest"
    assert (kafka.verdict, kafka.license) == ("nonfree", "")  # no label: curated.json decides
    ag = items["adguard/adguardhome"]
    assert ag.version == "latest, stable"
    assert (ag.verdict, ag.license, ag.url) == (
        "foss",
        "GPL-3.0",
        "https://github.com/AdguardTeam/AdGuardHome",
    )
    assert (items["redis"].verdict, items["redis"].license) == ("foss", "AGPL-3.0-only")
    tagless = items["somebody/tagless"]
    assert (tagless.version, tagless.removeCommand, tagless.url) == (
        None,
        "docker rmi somebody/tagless",
        "https://example.org",
    )
    assert items["someapp"].license == ""  # NOASSERTION is not a license


def test_label_licenses_are_classified(docker: None, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [row("a/free", "1", "aaa"), row("b/odd", "1", "bbb"), row("c/lower", "1", "ccc")]
    labels: dict[str, dict[str, str] | None] = {
        "aaa": {LIC: "MIT"},
        "bbb": {LIC: "Weird-1.0"},
        "ccc": {LIC: "noassertion"},
    }
    install(monkeypatch, FakeDocker(rows, labels))
    items = {i.name: i for i in scan_docker.scan_docker()}
    assert items["a/free"].verdict == "foss"
    assert (items["b/odd"].verdict, items["b/odd"].reason) == ("nonfree", "unrecognised license: Weird-1.0")
    assert items["c/lower"].license == ""


def test_newest_image_label_wins_and_partial_inspect_is_kept(
    docker: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [row("a/x", "new", "aaa"), row("a/x", "old", "bbb"), row("a/y", "1", "ccc")]
    labels: dict[str, dict[str, str] | None] = {"aaa": {LIC: "MIT"}, "bbb": {LIC: "GPL-2.0"}}
    install(monkeypatch, FakeDocker(rows, labels, inspect_rc=1))  # "ccc" failed to inspect
    items = {i.name: i for i in scan_docker.scan_docker()}
    assert items["a/x"].license == "MIT"
    assert items["a/y"].license == ""


def test_inspect_failure_entirely_leaves_labels_empty(docker: None, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [row("a/x", "1", "aaa"), row("node", "1", "bbb")]
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/docker")

    def run(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if cmd[1] == "images":
            return subprocess.CompletedProcess(cmd, 0, "\n".join(rows), "")
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(subprocess, "run", run)
    items = {i.name: i for i in scan_docker.scan_docker()}
    assert items["a/x"].license == ""
    assert items["node"].license == "MIT"  # official-image fallback needs no labels


def test_curated_verdicts_and_alternatives(docker: None, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        row("mongo", "latest", "aaa"),
        row("joplin/server", "latest", "bbb"),
        row("ghcr.io/open-webui/open-webui", "main", "ccc"),
        row("confluentinc/cp-kafka", "latest", "ddd"),
    ]
    labels: dict[str, dict[str, str] | None] = {
        "aaa": {},
        "bbb": {SRC: "https://github.com/laurent22/joplin.git"},
        "ccc": {LIC: "NOASSERTION", SRC: "https://github.com/open-webui/open-webui"},
        "ddd": {},
    }
    install(monkeypatch, FakeDocker(rows, labels))
    items = {i.name: i for i in apply(scan_docker.scan_docker(), Curated.load())}
    mongo = items["mongo"]
    assert (mongo.verdict, mongo.license) == ("nonfree", "SSPL-1.0")
    assert mongo.alternative is not None
    assert "FerretDB" in mongo.alternative.names[0]
    assert items["joplin/server"].verdict == "nonfree"
    assert items["joplin/server"].alternative is not None
    assert items["ghcr.io/open-webui/open-webui"].verdict == "nonfree"
    assert items["ghcr.io/open-webui/open-webui"].alternative is not None
    kafka = items["confluentinc/cp-kafka"]
    assert (kafka.verdict, kafka.license, kafka.alternative) == ("foss", "Apache-2.0", None)
