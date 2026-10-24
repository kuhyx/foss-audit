"""License lookup order per cached Maven version, network rounds included."""

from __future__ import annotations

from pathlib import Path

import pytest

from foss_audit import scan_cache_maven_resolve as res
from foss_audit import upstream_license
from foss_audit.scan_cache_maven_repos import CENTRAL, FLUTTER, GOOGLE, PLUGIN_PORTAL
from foss_audit.scan_cache_maven_resolve import Store, VersionFiles, fetch_all, resolve, resolve_all
from tests.maven_helpers import APACHE_TEXT, dep, offline, pom, write, zip_bytes

GAV = ("org.x", "lib", "1")
PARENT = ("org.x", "parent", "2")


def url(base: str, gav: tuple[str, str, str]) -> str:
    group, artifact, version = gav
    return f"{base}/{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}.pom"


def local(tmp_path: Path, gav: tuple[str, str, str], data: bytes, **kw: object) -> VersionFiles:
    return VersionFiles(poms=[write(tmp_path / f"{gav[1]}-{gav[2]}.pom", data)], **kw)  # type: ignore[arg-type]


def test_own_pom_license(tmp_path: Path) -> None:
    body = f"<dependencies>{dep('org.y', 'dep')}</dependencies>"
    store = Store({GAV: local(tmp_path, GAV, pom(GAV, (("MIT", ""),), body=body))})
    found = resolve(store, GAV)
    assert (found.license, found.license_from, found.deps) == ("MIT", "pom", ("org.y:dep",))


def test_nearest_parent_declares(tmp_path: Path) -> None:
    grand = ("org.x", "grand", "3")
    files = {
        GAV: local(tmp_path, GAV, pom(GAV, parent=PARENT)),
        PARENT: local(tmp_path, PARENT, pom(PARENT, parent=grand)),
        grand: local(tmp_path, grand, pom(grand, (("Apache-2.0", ""),))),
    }
    found = resolve(Store(files), GAV)
    assert (found.license, found.license_from) == ("Apache-2.0", "pom parent org.x:grand:3")


def test_missing_parent_is_fetched_from_recorded_repo_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jitpack = "https://jitpack.io"
    files = {GAV: local(tmp_path, GAV, pom(GAV, parent=PARENT))}
    asked = offline(monkeypatch, {url(jitpack, PARENT): pom(PARENT, (("BSD-3-Clause", ""),))})
    found = resolve_all(Store(files, repos={PARENT[:2]: jitpack}), [GAV])[GAV]
    assert found.license == "BSD-3-Clause"
    assert found.license_from == f"pom parent org.x:parent:2 from {url(jitpack, PARENT)}"
    assert asked == [url(jitpack, PARENT)]


def test_every_failed_fetch_is_in_the_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    offline(monkeypatch)
    found = resolve_all(Store({GAV: VersionFiles(modules=[Path("x.module")])}), [GAV])[GAV]
    assert found.license == ""
    tried = "; ".join(
        f"{url(b, GAV)}: offline {url(b, GAV)}" for b in (CENTRAL, GOOGLE, PLUGIN_PORTAL, FLUTTER)
    )
    assert found.license_from == (
        f"pom (license fetch failed: {tried}); gradle .module (no license field); no jar/aar cached"
    )


def test_fetched_pom_that_is_not_xml(tmp_path: Path) -> None:
    store = Store({GAV: local(tmp_path, GAV, b"<broken")})
    store.fetched = {url(b, GAV): b"<html>" for b in (CENTRAL, GOOGLE, PLUGIN_PORTAL, FLUTTER)}
    found = resolve(store, GAV)
    assert found.license_from.startswith(f"pom (license fetch failed: {url(CENTRAL, GAV)}: not a POM;")
    assert found.wants == ()
    store.fetched = {}
    assert resolve(store, GAV).license_from.startswith("pom (unreadable)")


def test_jar_license_before_any_fetch(tmp_path: Path) -> None:
    jar = write(tmp_path / "lib-1.jar", zip_bytes({"META-INF/LICENSE": APACHE_TEXT.encode()}))
    store = Store({GAV: VersionFiles(archives=[jar])})
    assert resolve(store, GAV) == res.Found("Apache-2.0", "META-INF/LICENSE in lib-1.jar", (), ())
    assert resolve(store, GAV).license == "Apache-2.0"  # second lookup is the memoised one


def test_license_comment_atop_a_parent_only_pom(tmp_path: Path) -> None:
    data = pom(GAV, header=f"<!-- {APACHE_TEXT} -->", body="<packaging>pom</packaging>")
    found = resolve(Store({GAV: local(tmp_path, GAV, data)}), GAV)
    assert (found.license, found.license_from) == (
        "Apache-2.0",
        "pom (no <licenses>); no jar/aar cached; license comment atop the pom",
    )


def test_plugin_marker_follows_the_plugin(tmp_path: Path) -> None:
    marker = ("o.id", "o.id.gradle.plugin", "1")
    plugin = ("o", "plugin", "1")
    marker_pom = pom(marker, body=f"<dependencies>{dep(*plugin)}</dependencies>")
    store = Store(
        {
            marker: local(tmp_path, marker, marker_pom),
            plugin: local(tmp_path, plugin, pom(plugin, (("MIT", ""),))),
        }
    )
    found = resolve(store, marker)
    assert (found.license, found.license_from) == ("MIT", "plugin marker -> o:plugin:1: pom")


def test_marker_loop_stops(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    marker = ("o", "o.gradle.plugin", "1")
    monkeypatch.setattr(res, "MAX_MARKER_HOPS", 0)
    data = pom(marker, body=f"<dependencies>{dep(*marker)}</dependencies>")
    assert resolve(Store({marker: local(tmp_path, marker, data)}), marker).license == ""


def test_unnamed_license_url_is_read(tmp_path: Path) -> None:
    lic = "https://x.org/license"
    store = Store({GAV: local(tmp_path, GAV, pom(GAV, (("", lic),)))})
    assert resolve(store, GAV).wants == ((lic,),)
    store.fetched[lic] = APACHE_TEXT.encode()
    found = resolve(store, GAV)
    assert (found.license, found.license_from) == ("Apache-2.0", f"pom license url {lic}")


def upstream(monkeypatch: pytest.MonkeyPatch, answers: dict[str, tuple[str, str]]) -> list[str]:
    """Serve upstream_license from `answers` (else offline); returns the URLs asked."""
    asked: list[str] = []

    def lookup(repo: str, ref: str = "") -> tuple[str, str]:
        assert not ref
        asked.append(repo)
        return answers.get(repo, ("", f"upstream {repo}: fetch failed: offline"))

    monkeypatch.setattr(upstream_license, "upstream_license", lookup)
    return asked


def test_unidentified_license_url_falls_back_to_source_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lic = "https://x.org/license"
    repo = "https://github.com/own/repo"
    scm = f"<scm><url>{repo}</url></scm>"
    store = Store({GAV: local(tmp_path, GAV, pom(GAV, (("", lic), ("", "https://y")), body=scm))})
    store.fetched[lic] = b"<html>a page</html>"
    store.failed["https://y"] = "HTTP Error 403"
    asked = upstream(monkeypatch, {repo: ("BSD-3-Clause", f"upstream {repo} HEAD: LICENSE file")})
    found = resolve(store, GAV)
    assert found.license == "BSD-3-Clause"
    where = f"source repo upstream {repo} HEAD: LICENSE file (default branch, not 1)"
    assert found.license_from == f"pom license url unidentified; {where}"
    assert asked == [repo]
    assert resolve(store, GAV) == found  # the store keeps the answer: asked once per scan
    assert asked == [repo]
    store.upstream.answers.clear()
    upstream(monkeypatch, {repo: ("", f"upstream {repo} HEAD: no license file")})
    assert resolve(store, GAV) == res.Found(f"{lic} / https://y", "pom", (), ())


def test_named_recognised_license_is_not_followed(tmp_path: Path) -> None:
    store = Store(
        {GAV: local(tmp_path, GAV, pom(GAV, (("", "https://www.apache.org/licenses/LICENSE-2.0"),)))}
    )
    assert resolve(store, GAV).wants == ()


def test_source_repo_last(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gav = ("com.github.own", "repo", "v1")
    parent = ("com.github.own", "repo-parent", "1")
    other = ("org.other", "p", "1")
    files = {
        gav: local(tmp_path, gav, pom(gav, parent=parent)),
        parent: local(
            tmp_path,
            parent,
            pom(parent, parent=other, body="<scm><url>https://github.com/own/real</url></scm>"),
        ),
        other: local(tmp_path, other, pom(other, body="<url>https://github.com/other/p</url>")),
    }
    store = Store(files)
    real = "https://github.com/own/real"
    asked = upstream(monkeypatch, {})
    assert resolve(store, gav).license_from.endswith(f"source repo upstream {real}: fetch failed: offline")
    assert asked == [real]
    store.upstream.answers.clear()
    upstream(monkeypatch, {real: ("", f"upstream {real} HEAD: no license file")})
    assert resolve(store, gav).license_from.endswith(f"source repo upstream {real} HEAD: no license file")
    store.upstream.answers.clear()
    upstream(monkeypatch, {real: ("MIT", f"upstream {real} HEAD: LICENSE file")})
    assert resolve(store, gav) == res.Found(
        "MIT", f"source repo upstream {real} HEAD: LICENSE file (default branch, not v1)", (), ()
    )


def test_fetch_tries_candidates_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = offline(monkeypatch, {"https://b": b"ok"})
    store = Store({})
    fetch_all(store, [("https://a", "https://b", "https://c")])
    assert asked == ["https://a", "https://b"]
    assert store.fetched == {"https://b": b"ok"}
    assert store.failed == {"https://a": "offline https://a"}


def test_fetch_error_without_message(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(url: str) -> bytes:
        raise ValueError

    monkeypatch.setattr(res.cache_common, "fetch_cached", fail)
    store = Store({})
    fetch_all(store, [("https://a",)])
    assert store.failed == {"https://a": "ValueError"}


def test_rounds_are_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(res, "MAX_ROUNDS", 1)
    offline(monkeypatch, {url(CENTRAL, PARENT): pom(PARENT, parent=("org.x", "grand", "3"))})
    found = resolve_all(Store({GAV: local(tmp_path, GAV, pom(GAV, parent=PARENT))}), [GAV])[GAV]
    assert found.wants  # still wanting the grandparent when the rounds ran out
