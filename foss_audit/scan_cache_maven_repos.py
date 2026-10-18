"""Which repository each cached artifact was downloaded from.

Gradle records the URL of every file it fetched in
metadata-*/resource-at-url.bin. Read as bytes (never executed), the URLs of
an artifact's own files name its repository, so a missing POM is fetched
from where the JAR came from instead of guessing. Artifacts Gradle has no
record of (and ~/.m2, which records only a repository id) fall back to the
well-known repositories, likeliest first.
"""

from __future__ import annotations

import re
from pathlib import Path

CENTRAL = "https://repo1.maven.org/maven2"
GOOGLE = "https://dl.google.com/dl/android/maven2"
PLUGIN_PORTAL = "https://plugins.gradle.org/m2"
FLUTTER = "https://storage.googleapis.com/download.flutter.io"
DEFAULT_REPOS = (CENTRAL, GOOGLE, PLUGIN_PORTAL, FLUTTER)
GOOGLE_GROUP = re.compile(
    r"^(androidx\.|com\.android(\.|$)|com\.google\.android\.|com\.google\.firebase|com\.google\.mlkit"
    r"|com\.google\.gms|com\.google\.ar|com\.google\.testing\.platform|com\.google\.devtools\.ksp"
    r"|com\.google\.prefab|com\.google\.jetpack|android\.arch\.|com\.crashlytics)"
)
URL = re.compile(rb"https?://[\x21-\x7e]+")
MAX_INDEX = 64 << 20


def _split(url: str, known: set[tuple[str, str]]) -> tuple[tuple[str, str], str] | None:
    """((group, artifact), base) for <base>/<group path>/<artifact>/<version>/<file>.

    Where the base ends is ambiguous from the URL alone; the split whose
    group:artifact is in the cache settles it.
    """
    parts = url.split("/")
    for cut in range(3, len(parts) - 3):
        group, artifact, version, name = ".".join(parts[cut:-3]), parts[-3], parts[-2], parts[-1]
        if (group, artifact) in known and name.startswith(f"{artifact}-{version}"):
            return (group, artifact), "/".join(parts[:cut])
    return None


def recorded_repos(metadata_root: Path, known: set[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """(group, artifact) -> the repository base URL Gradle fetched it from."""
    repos: dict[tuple[str, str], str] = {}
    for index in sorted(metadata_root.glob("metadata-*/resource-at-url.bin")):
        if index.stat().st_size > MAX_INDEX:
            continue
        for match in URL.finditer(index.read_bytes()):
            found = _split(match.group().decode(), known)
            if found is not None:
                repos[found[0]] = found[1]
    return repos


def repo_order(group: str, recorded: str | None) -> tuple[str, ...]:
    """Repositories to try for `group`: the recorded one, then the likeliest."""
    likely = (GOOGLE, CENTRAL) if GOOGLE_GROUP.match(group) else (CENTRAL, GOOGLE)
    order = ([recorded] if recorded else []) + [*likely, *DEFAULT_REPOS]
    # Gradle's default URL for Central is repo.maven.apache.org; same content.
    return tuple(
        dict.fromkeys(CENTRAL if base == "https://repo.maven.apache.org/maven2" else base for base in order)
    )
