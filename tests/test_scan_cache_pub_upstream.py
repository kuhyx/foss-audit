"""scan_cache_pub: an unlicensed git package falls back to its upstream repository (stubbed, no network)."""

# ruff: noqa: F811  (pytest fixtures are imported, then named as parameters)
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from foss_audit import scan_cache_pub, upstream_license
from tests.test_scan_cache_pub import cache, pkg, upstream, write  # noqa: F401


def unlicensed_git_package(cache: Path, name: str, origin: str) -> None:
    mirror = cache / f"git/cache/{name}-abc"
    write(mirror / "config", f'[remote "origin"]\n\turl = {origin}\n')
    checkout = cache / f"git/{name}-0123456789abcdef0123456789abcdef01234567"
    write(checkout / ".git/config", f'[remote "origin"]\n\turl = {mirror}\n')
    pkg(checkout, name, "1.0.0", None)


def test_unlicensed_git_package_takes_the_upstream_license(
    cache: Path, upstream: dict[str, tuple[str, str]]
) -> None:
    unlicensed_git_package(cache, "yt_dlp_dart", "https://github.com/KRTirtho/yt_dlp_dart.git")
    upstream["https://github.com/KRTirtho/yt_dlp_dart"] = (
        "MIT",
        "upstream https://github.com/KRTirtho/yt_dlp_dart HEAD: LICENSE file",
    )
    (item,) = scan_cache_pub.scan_pub_cache()
    assert (item.verdict, item.license) == ("foss", "MIT")
    assert "license from upstream https://github.com/KRTirtho/yt_dlp_dart HEAD: LICENSE file" in item.note


def test_still_unlicensed_item_names_the_upstream_check_too(
    cache: Path, upstream: dict[str, tuple[str, str]]
) -> None:
    unlicensed_git_package(cache, "hetu_std", "https://github.com/hetu-community/hetu_std.git")
    upstream["https://github.com/hetu-community/hetu_std"] = (
        "",
        "upstream https://github.com/hetu-community/hetu_std HEAD: no license file",
    )
    (item,) = scan_cache_pub.scan_pub_cache()
    assert (item.verdict, item.license) == ("nonfree", "")
    assert "field); upstream https://github.com/hetu-community/hetu_std HEAD: no license file" in item.reason


def test_failed_upstream_fetch_is_visible_in_the_item(
    cache: Path, upstream: dict[str, tuple[str, str]]
) -> None:
    unlicensed_git_package(cache, "gone", "https://example.org/o/gone.git")
    upstream["https://example.org/o/gone"] = (
        "",
        "upstream https://example.org/o/gone: fetch failed: timed out",
    )
    (item,) = scan_cache_pub.scan_pub_cache()
    assert item.verdict == "nonfree"
    assert "fetch failed: timed out" in item.reason


def test_upstream_lookups_run_in_parallel(cache: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    names = ("one", "two")
    for name in names:
        unlicensed_git_package(cache, name, f"https://github.com/o/{name}.git")
    barrier = threading.Barrier(len(names), timeout=5)

    def lookup(url: str) -> tuple[str, str]:
        barrier.wait()  # a serial scan never gets both lookups in flight: it times out
        return "MIT", f"upstream {url} HEAD: LICENSE file"

    monkeypatch.setattr(upstream_license, "upstream_license", lookup)
    assert sorted((i.name, i.license) for i in scan_cache_pub.scan_pub_cache()) == [
        ("one", "MIT"),
        ("two", "MIT"),
    ]
