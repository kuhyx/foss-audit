"""Read the root license files of a git repository's default branch or a ref, forge-agnostic.

Only the system `git` binary talks to the remote, so GitHub, GitLab (also
self-hosted), Gitea, Forgejo, Codeberg, Bitbucket, SourceHut and any plain git
server work the same. The tree of HEAD (or of a given tag/commit) is fetched at depth 1 with no blobs into
a throw-away bare repository, then only the root LICENSE*/COPYING*/UNLICENSE*
and README files are read.

The remote is untrusted: git only runs as a client (no checkout, so no hooks or
filters run), credential helpers, prompts and the user's own git config are
off, the transports are limited to https/http/file, and every call has a
timeout and a size cap. As no credentials are ever sent, a forge answering
"not found" or "authentication failed" means the repository is gone (deleted,
or private, which is the same to a reader): UpstreamGoneError, not a failure.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from foss_audit.own_license import LICENSE_FILE
from foss_audit.scan_cache_pub_license import UNLICENSE_FILE

GIT_TIMEOUT_S = 20
MAX_BLOB = 256 * 1024
LS_TREE_FIELDS = 3  # mode type sha
README_FILE = re.compile(r"(?i)^readme(\..*)?$")
# A tag, branch or commit sha taken from package data: never an option ("-..."),
# a refspec ("a:b", "+x") or a revision expression ("x^", "x~1", "x..y").
SAFE_REF = re.compile(r"^(?!.*\.\.)\w[\w./-]*$")
REGULAR_FILE_MODES = frozenset({"100644", "100755"})
GIT_ARGS = ("-c", "credential.helper=", "-c", "core.hooksPath=/dev/null", "-c", "protocol.version=2")
ENV = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "true",
    "SSH_ASKPASS": "true",
    "GIT_ALLOW_PROTOCOL": "https:http:file",
    "GIT_CONFIG_NOSYSTEM": "1",
    # ~/.gitconfig may name per-host credential helpers (credential.<url>.helper,
    # e.g. `gh auth git-credential`) that `credential.helper=` does not clear.
    "GIT_CONFIG_GLOBAL": os.devnull,
    "LC_ALL": "C",
}
# What GitHub, GitLab, Gitea/Forgejo and plain HTTP servers say about a missing
# repository to an anonymous client. 403 is left out: it is also a rate limit.
GONE = re.compile(
    r"(?i)repository not found|authentication failed for|repository '[^']*' not found"
    r"|requested url returned error: 40[14]\b"
)


class UpstreamError(Exception):
    """The remote could not be read; the message says why."""


class UpstreamGoneError(UpstreamError):
    """The remote says the repository does not exist; a definitive answer, not a failure."""


@dataclass
class RootFiles:
    """Text of the root files of the fetched tree (default branch or ref) that matter for licensing."""

    licenses: dict[str, str] = field(default_factory=dict)
    readme_name: str = ""
    readme: str = ""


def _git(repo: Path, *args: str) -> bytes:
    """Run one git command in `repo`; any failure becomes an UpstreamError."""
    cmd = ["git", *GIT_ARGS, "-C", str(repo), *args]
    env = {**os.environ, **ENV}
    try:
        done = subprocess.run(  # noqa: S603  # list args, no shell
            cmd, capture_output=True, timeout=GIT_TIMEOUT_S, check=False, env=env, stdin=subprocess.DEVNULL
        )
    except subprocess.TimeoutExpired:
        raise UpstreamError(f"timed out after {GIT_TIMEOUT_S} s") from None
    except OSError as exc:
        raise UpstreamError(f"cannot run git: {exc}") from exc
    if done.returncode:
        lines = done.stderr.decode(errors="replace").strip().splitlines()
        gone = next((line for line in lines if GONE.search(line)), "")
        if gone:
            raise UpstreamGoneError(gone[:200])
        raise UpstreamError(lines[-1][:200] if lines else f"git {args[0]} exited {done.returncode}")
    return done.stdout


def _entries(listing: bytes) -> list[tuple[str, str]]:
    """(name, sha) of each regular root file in `git ls-tree -z` output.

    Not `-l`: a size needs the blob, and in a blob-less fetch every blob is
    fetched on demand, one round trip each; for a big repository root that was
    5-20 s per package. Only the blobs `_blob` reads are fetched.
    """
    found: list[tuple[str, str]] = []
    for raw in listing.decode(errors="replace").split("\0"):
        meta, _, name = raw.partition("\t")
        fields = meta.split()
        if len(fields) == LS_TREE_FIELDS and fields[0] in REGULAR_FILE_MODES:
            found.append((name, fields[2]))
    return found


def _blob(repo: Path, sha: str) -> str | None:
    """A blob's text, or None when it is over MAX_BLOB."""
    if int(_git(repo, "cat-file", "-s", sha)) > MAX_BLOB:
        return None
    return _git(repo, "cat-file", "blob", sha).decode(errors="replace")


def read_root_files(url: str, ref: str = "") -> RootFiles:
    """License files and README of `url` at `ref` (default branch when ""); UpstreamError on failure."""
    if ref and not SAFE_REF.match(ref):
        raise UpstreamError(f"{ref!r} is not a usable git ref")
    with tempfile.TemporaryDirectory(prefix="foss-audit-upstream-") as tmp:
        repo = Path(tmp)
        _git(repo, "init", "--bare", "--quiet", ".")
        _git(repo, "remote", "add", "origin", url)
        target = ref or "HEAD"
        _git(
            repo,
            "fetch",
            "--quiet",
            "--depth",
            "1",
            "--filter=blob:none",
            "--end-of-options",
            "origin",
            target,
        )
        files = RootFiles()
        for name, sha in _entries(_git(repo, "ls-tree", "-z", "FETCH_HEAD")):
            is_license = bool(LICENSE_FILE.match(name) or UNLICENSE_FILE.match(name))
            if not is_license and (files.readme_name or not README_FILE.match(name)):
                continue
            text = _blob(repo, sha)
            if text is None:
                continue
            if is_license:
                files.licenses[name] = text
            else:
                files.readme_name, files.readme = name, text
        return files
