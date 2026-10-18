"""Shared fixture-free fakes for the Docker scanner tests."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest


def row(repo: str, tag: str, image_id: str) -> str:
    return json.dumps({"Repository": repo, "Tag": tag, "ID": image_id})


class FakeDocker:
    """Answers `docker images`, ONE batched `docker image inspect` and the container listing.

    `containers` maps a container id to (name, short image id, running).
    """

    def __init__(
        self,
        rows: list[str],
        labels: dict[str, dict[str, str] | None],
        images_rc: int = 0,
        inspect_rc: int = 0,
        containers: dict[str, tuple[str, str, bool]] | None = None,
    ) -> None:
        self.rows, self.labels = rows, labels
        self.images_rc, self.inspect_rc = images_rc, inspect_rc
        self.containers = containers or {}
        self.inspect_calls: list[list[str]] = []

    def __call__(self, cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        assert kw["timeout"] > 0
        if cmd[1] == "images":
            return subprocess.CompletedProcess(cmd, self.images_rc, "\n".join(self.rows) + "\n\n", "")
        if cmd[1] == "ps":
            return subprocess.CompletedProcess(cmd, 0, "".join(f"{c}\n" for c in self.containers), "")
        if cmd[1] == "container":
            lines = [
                f"{cid}{'0' * 52} sha256:{image}{'0' * 52} /{name} {str(running).lower()}"
                for cid, (name, image, running) in self.containers.items()
                if cid in cmd
            ]
            return subprocess.CompletedProcess(cmd, 0, "\n".join(lines) + "\n", "")
        self.inspect_calls.append(cmd)
        lines = [
            f"sha256:{short}{'0' * 52} {json.dumps(self.labels[short])}"
            for short in cmd[cmd.index("--format") + 2 :]
            if short in self.labels
        ]
        return subprocess.CompletedProcess(cmd, self.inspect_rc, "\n".join(lines), "")


def install(monkeypatch: pytest.MonkeyPatch, fake: FakeDocker) -> FakeDocker:
    monkeypatch.setattr(subprocess, "run", fake)
    return fake
