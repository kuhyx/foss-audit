"""Scan local Docker images: one Item per repository, tags merged into the version.

Licenses come from the image's `org.opencontainers.image.licenses` label (an
SPDX expression). Images without it fall back to OFFICIAL (Docker Hub official
images) and then to `unknown()`, which data/curated.json settles by name.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field

from foss_audit.licenses import classify_spdx
from foss_audit.model import Item
from foss_audit.scan_misc import unknown

TIMEOUT = 20
LICENSE_LABEL = "org.opencontainers.image.licenses"
URL_LABELS = ("org.opencontainers.image.source", "org.opencontainers.image.url")
# Labels some images fill with a placeholder instead of a license.
NO_ASSERTION = frozenset({"", "NOASSERTION", "NONE"})
# Own tooling: `local` tag (built here), `-mcp` repositories, and kuhy's namespaces.
OWN_TAG = "local"
OWN_SUFFIX = "-mcp"
OWN_NAMESPACES = ("kuhyx/", "ghcr.io/kuhyx/")

# Docker Hub official images are bare names ("node", "redis"), just like kuhy's
# own un-namespaced builds ("wintrchess-app"). A bare name is kept only when it
# is listed here or an OCI source/url label points outside kuhyx; everything
# else bare is treated as his own and skipped. The value is the fallback SPDX
# license for official images that ship no license label. Redis 8 is
# RSALv2 / SSPLv1 / AGPLv3 at the user's choice, so the free option is recorded.
# mongo is "" on purpose: SSPL is settled by data/curated.json.
OFFICIAL: dict[str, str] = {
    "alpine": "MIT AND GPL-2.0-only",
    "archlinux": "GPL-3.0-or-later",
    "busybox": "GPL-2.0-only",
    "caddy": "Apache-2.0",
    "flink": "Apache-2.0",
    "golang": "BSD-3-Clause",
    "httpd": "Apache-2.0",
    "memcached": "BSD-3-Clause",
    "mongo": "",
    "nginx": "BSD-2-Clause",
    "node": "MIT",
    "postgres": "PostgreSQL",
    "python": "PSF-2.0",
    "redis": "AGPL-3.0-only",
}


@dataclass
class Repo:
    """All local tags/images of one repository."""

    name: str
    tags: set[str] = field(default_factory=set)
    ids: list[str] = field(default_factory=list)


@dataclass
class Container:
    """A container (running or stopped); `docker rmi` refuses while one uses the image."""

    id: str
    name: str
    image: str
    running: bool


def run_docker(args: list[str], *, partial: bool = False) -> str | None:
    """stdout of `docker <args>`, or None when docker is missing/unreachable.

    `partial` keeps the stdout of a non-zero exit: `image inspect` exits 1 when
    any one image fails but still prints the others.
    """
    docker = shutil.which("docker")
    if not docker:
        return None
    try:
        proc = subprocess.run([docker, *args], capture_output=True, text=True, check=False, timeout=TIMEOUT)
    except subprocess.TimeoutExpired, OSError:
        return None
    return proc.stdout if partial or proc.returncode == 0 else None


def is_own(repo: str, tag: str) -> bool:
    """kuhy's own builds, never audited here."""
    return tag == OWN_TAG or repo.endswith(OWN_SUFFIX) or repo.startswith(OWN_NAMESPACES)


def group_repos(listing: str) -> dict[str, Repo]:
    """Parse `docker images --format '{{json .}}'` into repositories, minus own and dangling."""
    repos: dict[str, Repo] = {}
    for line in listing.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        name, tag = row["Repository"], row["Tag"]
        if name == "<none>" or is_own(name, tag):
            continue
        repo = repos.setdefault(name, Repo(name))
        if tag != "<none>":
            repo.tags.add(tag)
        if row["ID"] not in repo.ids:
            repo.ids.append(row["ID"])
    return repos


def inspect_labels(ids: list[str]) -> dict[str, dict[str, str]]:
    """Labels per full image id, from ONE batched `docker image inspect`."""
    # `index` tolerates images whose Config has no Labels key at all.
    fmt = '{{.Id}} {{json (index .Config "Labels")}}'
    out = run_docker(["image", "inspect", "--format", fmt, *ids], partial=True)
    labels: dict[str, dict[str, str]] = {}
    for line in (out or "").splitlines():
        image_id, _, raw = line.partition(" ")
        labels[image_id.removeprefix("sha256:")] = json.loads(raw) or {}
    return labels


def list_containers() -> list[Container]:
    """Every container with its full image id, from ONE batched `docker container inspect`."""
    ids = (run_docker(["ps", "-aq"]) or "").split()
    if not ids:
        return []
    fmt = "{{.Id}} {{.Image}} {{.Name}} {{.State.Running}}"
    out = run_docker(["container", "inspect", "--format", fmt, *ids], partial=True)
    containers = []
    for line in (out or "").splitlines():
        cid, image, name, running = line.split()
        containers.append(
            Container(cid[:12], name.lstrip("/"), image.removeprefix("sha256:"), running == "true")
        )
    return containers


def users_note(users: list[Container]) -> str:
    """Which containers block `docker rmi`; running ones are flagged so a live service is not killed."""
    if not users:
        return ""
    names = ", ".join(f"{c.name} (RUNNING)" if c.running else c.name for c in users)
    return f"used by container{'s' if len(users) > 1 else ''} {names}"


def repo_labels(repo: Repo, labels: dict[str, dict[str, str]]) -> dict[str, str]:
    """Merge the labels of a repository's images; the newest image (listed first) wins."""
    merged: dict[str, str] = {}
    for short_id in repo.ids:
        for full_id, found in labels.items():
            if full_id.startswith(short_id):
                for key, value in found.items():
                    merged.setdefault(key, value)
    return merged


def label_url(labels: dict[str, str]) -> str | None:
    """The upstream link: the OCI source label, else the url label."""
    for key in URL_LABELS:
        if labels.get(key):
            return labels[key].removesuffix(".git")
    return None


def is_foreign_bare(labels: dict[str, str]) -> bool:
    """A bare name whose source/url label points outside kuhyx is someone else's image."""
    links = [labels[k] for k in URL_LABELS if labels.get(k)]
    return bool(links) and not any("kuhyx" in link.lower() for link in links)


def make_item(repo: Repo, labels: dict[str, str], containers: list[Container]) -> Item:
    """One Item; license from the label, else the official-image table, else unknown."""
    tags = sorted(repo.tags)
    version = ", ".join(tags) or None
    url = label_url(labels)
    remove = "docker rmi " + " ".join(f"{repo.name}:{t}" for t in tags) if tags else f"docker rmi {repo.name}"
    # Containers go first or `docker rmi` refuses; -f stops running ones, volumes are kept (no -v).
    users = [c for c in containers if any(c.image.startswith(i) for i in repo.ids)]
    if users:
        remove = "docker rm -f " + " ".join(c.id for c in users) + " && " + remove
    note = users_note(users)
    lic = labels.get(LICENSE_LABEL, "")
    if lic.upper() in NO_ASSERTION:
        lic = OFFICIAL.get(repo.name, "")
    if not lic:
        return unknown(repo.name, "docker", version=version, url=url, removeCommand=remove, note=note)
    verdict, reason = classify_spdx(repo.name, lic)
    return Item(
        name=repo.name,
        source="docker",
        verdict=verdict,
        version=version,
        license=lic,
        reason=reason,
        url=url,
        removeCommand=remove,
        note=note,
    )


def scan_docker() -> list[Item]:
    """Local Docker images, or [] without docker / a reachable daemon."""
    listing = run_docker(["images", "--format", "{{json .}}"])
    if not listing:
        return []
    repos = group_repos(listing)
    ids = sorted({i for repo in repos.values() for i in repo.ids})
    labels = inspect_labels(ids) if ids else {}
    containers = list_containers()
    items = []
    for name in sorted(repos):
        found = repo_labels(repos[name], labels)
        if "/" not in name and name not in OFFICIAL and not is_foreign_bare(found):
            continue
        items.append(make_item(repos[name], found, containers))
    return items
