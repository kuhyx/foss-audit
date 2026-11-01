"""The CURRENT license of a package's upstream repository, on whatever forge hosts it.

A last-resort lookup for git-sourced packages whose cached checkout carries no
license file: the repository may have gained one since. The core path is
forge-agnostic (upstream_git: the system `git` fetches the default branch's
tree, then the root LICENSE*/COPYING* files are read), so GitHub, GitLab,
Gitea, Forgejo, Codeberg, Bitbucket, SourceHut and plain git servers all work
without a per-forge API. Last of all, a README that names its license counts.

A caller that knows the version's tag or commit passes it as `ref`: that tree
is read instead, and only when it cannot be fetched does the default branch
answer, labelled "(default branch, not <ref>)".

Answers are kept 30 days in ~/.cache/foss-audit/upstream-license.json, keyed by
the normalised URL (plus "@<ref>" for a ref). A repository the forge says is
gone (deleted or private) is an answer too: no license, "repository gone",
cached like any other. A ref that cannot be fetched but whose default branch can
is answered from the default branch and that answer is cached under the ref key
too (else every scan would retry the doomed fetch). A total failure (network
down, DNS, timeout) is returned as text and never cached: visible, retried next
scan.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

from foss_audit.scan_cache_pub_license import recognise
from foss_audit.upstream_git import RootFiles, UpstreamError, UpstreamGoneError, read_root_files
from foss_audit.upstream_readme import readme_license

CACHE_FILE = Path.home() / ".cache/foss-audit/upstream-license.json"
TTL_S = 30 * 24 * 3600
SCP_URL = re.compile(r"^(?:[\w.-]+@)?([\w.-]+):(?!//)/?(\S+)$")
# npm-style repository shorthands: "github:u/r", "gitlab:u/r#tag", bare "u/r" (GitHub).
SHORTHAND = re.compile(r"^(?:(github|gitlab|bitbucket):)?([\w.-]+/[\w.-]+?)(?:\.git)?(?:#\S*)?$")
SHORTHAND_HOSTS = {"github": "github.com", "gitlab": "gitlab.com", "bitbucket": "bitbucket.org"}
KEEP_PORT = frozenset({"http", "https"})
SCHEMES = frozenset({"http", "https", "ssh", "git", "file"})
# Hosts whose web links name a repository as /owner/repo; GitLab-likes nest groups.
FORGES = frozenset({"github.com", "bitbucket.org", "codeberg.org", "gitee.com", "git.sr.ht"})
NESTED_FORGES = frozenset({"gitlab.com", "salsa.debian.org", "invent.kde.org", "framagit.org"})
FORGE_HOST = re.compile(r"^(?:git|gitlab|gitea|forgejo)\.")
# A web-UI path segment after the repository (/-/blob/..., /tree/main, /src/branch/...).
WEB_SEGMENTS = frozenset({"-", "tree", "blob", "src", "commit", "commits", "releases", "issues", "wiki"})
SCM_GIT = re.compile(r"(?i)^scm:git:")
OWNER_REPO = 2
# Lookups run in worker threads of several processes; the cache file is read-modify-written.
STORE_LOCK = threading.Lock()


def _now() -> float:
    return time.time()


def normalise(url: str) -> str:
    """https://host/owner/repo for git@host:o/r, ssh://, git+https://, .git and npm
    shorthand ("github:u/r", "u/r") forms ("" if unusable)."""
    text = url.strip().removeprefix("git+")
    short = None if "://" in text else SHORTHAND.match(text)
    scp = None if "://" in text or short else SCP_URL.match(text)
    if short:
        text = f"https://{SHORTHAND_HOSTS[short[1] or 'github']}/{short[2]}"
    elif scp:
        text = f"https://{scp.group(1)}/{scp.group(2)}"
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:  # a non-numeric or out-of-range port
        return ""
    scheme = parts.scheme
    if scheme not in SCHEMES or (scheme != "file" and not parts.hostname):
        return ""
    path = parts.path.rstrip("/").removesuffix(".git").rstrip("/")
    if scheme == "file":
        return f"file://{path}"
    kept = f":{port}" if port and scheme in KEEP_PORT else ""
    return f"{'http' if scheme == 'http' else 'https'}://{parts.hostname}{kept}{path}"


def repository(link: str) -> str:
    """The repository behind a source link, normalised; "" unless it names one.

    A Maven `scm:git:` connection is trusted on any host (other `scm:` kinds
    are not git); a plain web link only on a recognisable forge, cut back to
    the repository itself (no /tree/main, /-/blob/... web-UI tail).
    """
    text = link.strip()
    trusted = bool(SCM_GIT.match(text))
    if text.lower().startswith("scm:") and not trusted:
        return ""
    key = normalise(SCM_GIT.sub("", text))
    if not key or trusted:
        return key
    parts = urlsplit(key)
    host = parts.hostname or ""
    if host not in FORGES | NESTED_FORGES and not FORGE_HOST.match(host):
        return ""
    segments = [seg for seg in parts.path.split("/") if seg]
    tail = next(
        (i for i, seg in enumerate(segments) if i >= OWNER_REPO and seg in WEB_SEGMENTS), len(segments)
    )
    keep = segments[: OWNER_REPO if host in FORGES else tail]
    return f"{parts.scheme}://{parts.netloc}/{'/'.join(keep)}" if len(keep) >= OWNER_REPO else ""


def _decide(files: RootFiles, key: str, ref: str) -> tuple[str, str]:
    """(license, where checked) from the root files of `ref` (HEAD when "")."""
    where = f"upstream {key} {ref or 'HEAD'}"
    ids: dict[str, str] = {}
    skipped = ""
    for name in sorted(files.licenses, key=str.lower):
        found = recognise(files.licenses[name])
        if found:
            ids.setdefault(found, name)
        else:
            skipped = f" (placeholder {name} skipped)"
    if ids:
        return " AND ".join(sorted(ids)), f"{where}: {', '.join(dict.fromkeys(ids.values()))} file"
    named = readme_license(files.readme)
    if named:
        return named, f"{where}: {files.readme_name} names the license (no license file)"
    return "", f"{where}: no license file{skipped}"


def _load() -> dict[str, dict[str, object]]:
    try:
        data = json.loads(CACHE_FILE.read_text())
    except OSError, ValueError:
        return {}
    return data if isinstance(data, dict) else {}


@contextlib.contextmanager
def _file_lock() -> Iterator[None]:
    """Exclusive across processes (the scanners run in one each); skipped when the dir is unwritable."""
    lock = CACHE_FILE.with_suffix(".lock")
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
        handle = lock.open("a")
    except OSError:
        yield
        return
    with handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def _store(key: str, license_id: str, checked: str) -> None:
    """Merge one answer into the cache file (atomic replace); a read-only cache dir is not an error."""
    with STORE_LOCK, _file_lock():
        data = _load()
        data[key] = {"license": license_id, "checked": checked, "fetched_at": _now()}
        tmp = CACHE_FILE.with_suffix(f".{os.getpid()}.tmp")
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(data, indent=1, sort_keys=True))
            tmp.replace(CACHE_FILE)
        except OSError:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)


def _fresh(entry: object) -> tuple[str, str] | None:
    if not isinstance(entry, dict):
        return None
    when, lic, checked = entry.get("fetched_at"), entry.get("license"), entry.get("checked")
    if isinstance(when, int | float) and isinstance(lic, str) and isinstance(checked, str):
        return (lic, checked) if 0 <= _now() - when < TTL_S else None
    return None


def _lookup(key: str, ref: str) -> tuple[str, str, bool]:
    """(license, where checked, answered): from the cache, else the network; only an answer is stored."""
    store_key = f"{key}@{ref}" if ref else key
    cached = _fresh(_load().get(store_key))
    if cached:
        return (*cached, True)
    try:
        found, checked = _decide(read_root_files(key, ref), key, ref)
    except UpstreamGoneError as exc:  # no tree at any ref: the default branch is gone too
        found, checked = "", f"upstream {key}: repository gone ({exc})"
    except UpstreamError as exc:
        return "", f"upstream {key}: fetch failed: {exc}", False
    _store(store_key, found, checked)
    return found, checked, True


def upstream_license(url: str, ref: str = "") -> tuple[str, str]:
    """(license, where checked) of the repository at `ref`, else its default
    branch (labelled as such when `ref` was asked for); license "" when none."""
    key = normalise(url)
    if not key:
        return "", f"upstream {url!r}: not a fetchable git URL"
    found, checked, answered = _lookup(key, ref)
    if answered or not ref:
        return found, checked
    # A missing tag, an unfetchable sha: the default branch answers, said so. That answer is
    # kept under the ref key too, or every rescan would retry the doomed ref fetch (up to 20 s).
    found, checked, answered = _lookup(key, "")
    checked += not_this_version(ref)
    if answered:
        _store(f"{key}@{ref}", found, checked)
    return found, checked


def not_this_version(version: object) -> str:
    """The note a license read off the default branch carries: it may not be this version's."""
    return f" (default branch, not {version if isinstance(version, str) and version else 'this version'})"


def with_upstream(license_id: str, where: str, url: str) -> tuple[str, str]:
    """Last fallback for a package whose own files gave no license.

    A licensed package is returned unchanged; otherwise the upstream repository
    is consulted and, still unlicensed, its check is appended to `where` so the
    item names every place that was looked.
    """
    if license_id or not url:
        return license_id, where
    found, checked = upstream_license(url)
    return (found, checked) if found else ("", f"{where}; {checked}")
