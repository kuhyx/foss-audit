"""Last resort: the source repository of a Maven artifact, on whatever forge hosts it.

Some artifacts publish a POM with no <licenses> anywhere up its parent chain
and a JAR with no license file (Flutter's engine jars, JitPack builds,
Gradle plugins). Their source repository still carries one. It is found from
the artifact's own data: the POM's <scm> connection or a <scm>/<url> link on
a recognisable forge, Flutter's io.flutter:<engine artifact>:1.0.0-<flutter
commit>, or the io.github./com.github.<owner>[.<repo>]:<artifact> namespace
convention (JitPack's too). The Flutter engine commit and a JitPack version
(the tag or commit it was built from) name the exact tree to read; any other
source is read at its default branch, and the `license_from` says it is not
necessarily this version's.

The lookups (a git fetch each) run in parallel: resolve_all first only
collects them, runs them on a bounded pool, then resolves again.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from foss_audit import progress, upstream_license
from foss_audit.scan_cache_maven_pom import Gav
from foss_audit.upstream_license import SCM_GIT, repository

GITHUB_GROUP = re.compile(r"^(?:com|io)\.github\.([\w\-]+)(?:\.([\w.\-]+))?$")
FLUTTER_ENGINE = re.compile(r"^1\.0\.0-([0-9a-f]{40})$")
JITPACK_GROUP = "com.github."
UPSTREAM_WORKERS = 16
# (repository URL, git ref or "" for the default branch)
RepoRef = tuple[str, str]


def source_repo(gav: Gav, source_urls: tuple[str, ...]) -> RepoRef:
    """(git URL of `gav`'s source repository, the ref this version was built
    from or ""); ("", "") when none is named.

    An scm:git: connection beats a web link, wherever it sits in the chain.
    """
    group, artifact, version = gav
    engine = FLUTTER_ENGINE.match(version) if group == "io.flutter" else None
    if engine:
        return "https://github.com/flutter/flutter", engine.group(1)
    ordered = sorted(source_urls, key=lambda url: not SCM_GIT.match(url.strip()))
    named = next((repo for repo in map(repository, ordered) if repo), "")
    if named:
        return named, ""
    owner = GITHUB_GROUP.match(group)
    if owner is None:
        return "", ""
    # A -SNAPSHOT is a moving branch tip, not this version's tree: no ref.
    pinned = group.startswith(JITPACK_GROUP) and not version.endswith("-SNAPSHOT")
    ref = version if pinned else ""
    return f"https://github.com/{owner.group(1)}/{owner.group(2) or artifact}", ref


def _lookup(key: RepoRef) -> tuple[str, str]:
    answer = upstream_license.upstream_license(*key)
    progress.counter("maven-cache").advance()
    return answer


@dataclass
class Upstream:
    """The scan's source-repository answers, one lookup per (repo, ref)."""

    answers: dict[RepoRef, tuple[str, str]] = field(default_factory=dict)
    # While collecting, an unanswered lookup is queued instead of run.
    collecting: bool = False
    queued: set[RepoRef] = field(default_factory=set)

    def license(self, gav: Gav, sources: tuple[str, ...]) -> tuple[str, str]:
        """(license, where) from the source repository; ("", "") when none is
        named or its lookup is only queued."""
        key = source_repo(gav, sources)
        if not key[0]:
            return "", ""
        if key not in self.answers:
            if self.collecting:
                self.queued.add(key)
                return "", ""
            self.answers[key] = upstream_license.upstream_license(*key)
        license_text, checked = self.answers[key]
        # A ref's answer labels itself when it fell back to the default branch.
        note = upstream_license.not_this_version(gav[2]) if license_text and not key[1] else ""
        return license_text, f"source repo {checked}{note}"

    def run_queued(self) -> bool:
        """Answer every queued lookup in parallel; False when none was queued."""
        keys = sorted(self.queued - self.answers.keys())
        self.queued.clear()
        progress.counter("maven-cache").add_total(len(keys))
        with ThreadPoolExecutor(max_workers=UPSTREAM_WORKERS) as pool:
            self.answers.update(zip(keys, pool.map(_lookup, keys), strict=True))
        return bool(keys)
