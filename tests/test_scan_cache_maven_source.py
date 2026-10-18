"""Where a Maven artifact came from: Gradle's URL index and its source repository."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from foss_audit import scan_cache_maven_repos as repos
from foss_audit import upstream_license
from foss_audit.scan_cache_maven_resolve import Store, VersionFiles, resolve, resolve_all
from foss_audit.scan_cache_maven_source import source_repo
from tests.maven_helpers import pom, write

GOOGLE = "https://dl.google.com/dl/android/maven2"
KNOWN = {("com.android", "signflinger"), ("org.x", "lib")}


def index(tmp_path: Path, data: bytes) -> Path:
    write(tmp_path / "metadata-2.107/resource-at-url.bin", data)
    return tmp_path


def test_recorded_repos_from_gradle_url_index(tmp_path: Path) -> None:
    data = (
        b"\x00files-2.1/com.android/signflinger/8.1/ab/signflinger-8.1.pom\x00\x01\xde"
        + f"{GOOGLE}/com/android/signflinger/8.1/signflinger-8.1.jar".encode()
        + b"\x01\x00https://jitpack.io/org/x/lib/v2/lib-v2.pom\x01"
        + b"https://example.com/unrelated/thing/1/other-1.jar\x00https://x\x00"
    )
    assert repos.recorded_repos(index(tmp_path, data), KNOWN) == {
        ("com.android", "signflinger"): GOOGLE,
        ("org.x", "lib"): "https://jitpack.io",
    }


def test_oversized_index_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(repos, "MAX_INDEX", 4)
    assert repos.recorded_repos(index(tmp_path, b"https://jitpack.io/org/x/lib/1/lib-1.pom"), KNOWN) == {}


def test_repo_order() -> None:
    assert repos.repo_order("androidx.core", None) == (
        GOOGLE,
        repos.CENTRAL,
        repos.PLUGIN_PORTAL,
        repos.FLUTTER,
    )
    assert repos.repo_order("org.x", "https://repo.maven.apache.org/maven2") == (
        repos.CENTRAL,
        GOOGLE,
        repos.PLUGIN_PORTAL,
        repos.FLUTTER,
    )
    assert repos.repo_order("org.x", "https://jitpack.io")[0] == "https://jitpack.io"


GH = "https://github.com"


SHA = "a" * 40


@pytest.mark.parametrize(
    ("gav", "sources", "url", "ref"),
    [
        (("io.flutter", "x86_64_debug", "1.0.0-" + SHA), (), f"{GH}/flutter/flutter", SHA),
        (("io.flutter", "flutter_embedding", "2.0"), (), "", ""),
        (
            ("org.x", "lib", "1"),
            ("http://x.org", "scm:git:git@github.com:own/repo.git"),
            f"{GH}/own/repo",
            "",
        ),
        # The scm connection beats an earlier web link; any forge, not just GitHub.
        (
            ("org.x", "lib", "1"),
            ("https://github.com/own/site", "scm:git:https://git.example.org/own/repo.git"),
            "https://git.example.org/own/repo",
            "",
        ),
        (("org.x", "lib", "1"), ("https://gitlab.com/g/r/-/tree/main",), "https://gitlab.com/g/r", ""),
        (("org.x", "lib", "1"), ("scm:svn:https://svn.x.org/r",), "", ""),
        # JitPack's com.github.<owner> convention: the version is the tag/commit it was built from.
        (("com.github.own", "repo", "v1"), (), f"{GH}/own/repo", "v1"),
        (("com.github.own.repo", "module", "abc123"), (), f"{GH}/own/repo", "abc123"),
        (("com.github.own", "repo", "main-SNAPSHOT"), (), f"{GH}/own/repo", ""),
        (("com.github.own", "repo", "v1"), ("https://github.com/own/real",), f"{GH}/own/real", ""),
        (("io.github.own", "repo", "1.0"), (), f"{GH}/own/repo", ""),
        (("org.x", "lib", "1"), ("https://example.org",), "", ""),
    ],
)
def test_source_repo(gav: tuple[str, str, str], sources: tuple[str, ...], url: str, ref: str) -> None:
    assert source_repo(gav, sources) == (url, ref)


# --- the source-repository lookup inside resolve ------------------------------------------


def serve(
    monkeypatch: pytest.MonkeyPatch, answers: dict[tuple[str, str], tuple[str, str]]
) -> list[tuple[str, str]]:
    """Serve upstream_license(repo, ref) from `answers`; returns the (repo, ref) pairs asked."""
    asked: list[tuple[str, str]] = []

    def lookup(repo: str, ref: str = "") -> tuple[str, str]:
        asked.append((repo, ref))
        return answers[repo, ref]

    monkeypatch.setattr(upstream_license, "upstream_license", lookup)
    return asked


def engine(version: str) -> tuple[str, str, str]:
    return ("io.flutter", "x86_64_debug", f"1.0.0-{version}")


def test_flutter_engine_reads_its_commit_unlabelled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flutter = f"{GH}/flutter/flutter"
    hit, miss = engine(SHA), engine("b" * 40)
    files = {gav: VersionFiles(poms=[write(tmp_path / f"{gav[2]}.pom", pom(gav))]) for gav in (hit, miss)}
    asked = serve(
        monkeypatch,
        {
            (flutter, SHA): ("BSD-3-Clause", f"upstream {flutter} {SHA}: LICENSE file"),
            (flutter, "b" * 40): (
                "MIT",
                f"upstream {flutter} HEAD: LICENSE file (default branch, not {'b' * 40})",
            ),
        },
    )
    store = Store(files)
    found = resolve(store, hit)
    assert (found.license, found.license_from.split("; ")[-1]) == (
        "BSD-3-Clause",
        f"source repo upstream {flutter} {SHA}: LICENSE file",
    )
    assert resolve(store, miss).license_from.endswith(
        f"source repo upstream {flutter} HEAD: LICENSE file (default branch, not {'b' * 40})"
    )
    assert resolve(store, hit) == found  # once per (repo, ref) per scan
    assert asked == [(flutter, SHA), (flutter, "b" * 40)]


def test_resolve_all_runs_lookups_in_parallel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gavs = [("com.github.own", "one", "v1"), ("com.github.own", "two", "v2")]
    files = {gav: VersionFiles(poms=[write(tmp_path / f"{gav[1]}.pom", pom(gav))]) for gav in gavs}
    barrier = threading.Barrier(len(gavs), timeout=5)

    def lookup(repo: str, ref: str = "") -> tuple[str, str]:
        barrier.wait()  # both lookups must be in flight at once, or this times out
        return "MIT", f"upstream {repo} {ref}: LICENSE file"

    monkeypatch.setattr(upstream_license, "upstream_license", lookup)
    results = resolve_all(Store(files), gavs)
    assert [results[gav].license for gav in gavs] == ["MIT", "MIT"]
    assert results[gavs[1]].license_from.endswith(f"source repo upstream {GH}/own/two v2: LICENSE file")


def test_resolve_all_without_lookups(tmp_path: Path) -> None:
    gav = ("org.x", "lib", "1")
    files = {gav: VersionFiles(poms=[write(tmp_path / "lib.pom", pom(gav, (("MIT", ""),)))])}
    assert resolve_all(Store(files), [gav])[gav].license == "MIT"
