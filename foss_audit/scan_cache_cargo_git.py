"""Upstream repository URL of a cargo git checkout (~/.cargo/git/checkouts/<db>/<rev>/).

Where it comes from, in order of trust:
1. the bare database's own config, ~/.cargo/git/db/<db>/config, when it records
   an origin url;
2. a `source = "git+<url>#<sha>"` line of a ~/src Cargo.lock whose sha starts
   with the checkout's <rev> directory name (cargo names it by a short sha);
3. the crate's own `repository` / `homepage` field.

Everything is read-only text; Cargo.locks are only scanned the first time an
unlicensed checkout needs them.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from foss_audit.cache_common import project_files

ORIGIN_URL = re.compile(r"^\s*url\s*=\s*(\S+)", re.MULTILINE)
LOCK_GIT = re.compile(r'source = "git\+([^"#?]+)[^"#]*#([0-9a-f]{7,40})"')


class GitUrls:
    """Resolves checkouts to upstream URLs; the Cargo.lock index is built on first use."""

    def __init__(self, cargo: Path, src: Path) -> None:
        self.cargo, self.src = cargo, src
        self._locked: list[tuple[str, str]] | None = None

    def _locks(self) -> list[tuple[str, str]]:
        if self._locked is None:
            self._locked = []
            for lock in project_files(["Cargo.lock"], self.src):
                self._locked += [
                    (sha, url) for url, sha in LOCK_GIT.findall(lock.read_text(errors="replace"))
                ]
        return self._locked

    def find(self, db: str, rev: str, package: dict[str, Any]) -> str:
        """Upstream URL of checkout <db>/<rev>, "" when nothing names one."""
        config = self.cargo / "git/db" / db / "config"
        found = ORIGIN_URL.search(config.read_text(errors="replace")) if config.is_file() else None
        if found:
            return found.group(1)
        locked = next((url for sha, url in self._locks() if sha.startswith(rev)), "")
        declared = next((v for k in ("repository", "homepage") if isinstance(v := package.get(k), str)), "")
        return locked or declared
