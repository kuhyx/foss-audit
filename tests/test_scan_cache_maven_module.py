"""Gradle .module metadata in the removal graph: what Gradle actually resolves for KMP artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from foss_audit import scan_cache_maven_remove as remove
from foss_audit.cache_common import CachedArtifact, CachedVersion
from foss_audit.model import Item
from foss_audit.scan_cache_maven_decl import declarations
from foss_audit.scan_cache_maven_graph import dependency_graph
from foss_audit.scan_cache_maven_pom import Gav
from foss_audit.scan_cache_maven_resolve import VersionFiles
from tests.maven_helpers import dep, gradle_file, pom, write

OKHTTP3 = "com.squareup.okhttp3"
LOGGING = (OKHTTP3, "logging-interceptor", "5.5.0")
OKHTTP = (OKHTTP3, "okhttp", "5.5.0")


def module_json(gav: Gav, *variants: object) -> bytes:
    """A Gradle .module file: its component and `variants` as given."""
    component = {"group": gav[0], "module": gav[1], "version": gav[2]}
    return json.dumps({"formatVersion": "1.1", "component": component, "variants": list(variants)}).encode()


def okhttp_cache(root: Path) -> dict[Gav, VersionFiles]:
    """logging-interceptor's POM names okhttp-jvm, but Gradle reads its .module, which
    names the okhttp root, whose variants are available at okhttp-jvm / okhttp-android."""
    jvm_dep = f"<dependencies>{dep(OKHTTP3, 'okhttp-jvm')}</dependencies>"
    logging_module = module_json(
        LOGGING,
        {"name": "apiElements", "dependencies": [{"group": OKHTTP3, "module": "okhttp"}]},
        {"name": "runtimeElements", "dependencyConstraints": [{"group": "org.c", "module": "constraint"}]},
    )
    okhttp_module = module_json(
        OKHTTP,
        {"name": "jvmApiElements-published", "available-at": {"group": OKHTTP3, "module": "okhttp-jvm"}},
        {"name": "androidApi-published", "available-at": {"group": OKHTTP3, "module": "okhttp-android"}},
        "not a variant",
        {"name": "odd", "dependencies": ["not a dependency"], "available-at": "nowhere"},
    )
    brotli, zstd = (OKHTTP3, "okhttp-brotli", "5.5.0"), (OKHTTP3, "okhttp-zstd", "5.5.0")
    return {
        LOGGING: VersionFiles(
            poms=[gradle_file(root, LOGGING, "l.pom", pom(LOGGING, body=jvm_dep))],
            modules=[gradle_file(root, LOGGING, "l.module", logging_module)],
        ),
        OKHTTP: VersionFiles(
            poms=[gradle_file(root, OKHTTP, "o.pom", pom(OKHTTP))],
            modules=[gradle_file(root, OKHTTP, "o.module", okhttp_module)],
        ),
        brotli: VersionFiles(modules=[gradle_file(root, brotli, "b.module", b"{not json")]),
        zstd: VersionFiles(modules=[gradle_file(root, zstd, "z.module", b'["a list"]')]),
    }


def test_module_dependencies_and_available_at(tmp_path: Path) -> None:
    # The POM's deps arrive through the resolved CachedVersion, as in a scan.
    pom_deps = CachedVersion("5.5.0", "", "", (f"{OKHTTP3}:okhttp-jvm",))
    graph = dependency_graph(
        [CachedArtifact(f"{OKHTTP3}:logging-interceptor", [pom_deps])], okhttp_cache(tmp_path)
    )
    assert graph[f"{OKHTTP3}:logging-interceptor"] == {f"{OKHTTP3}:okhttp", f"{OKHTTP3}:okhttp-jvm"}
    assert graph[f"{OKHTTP3}:okhttp"] == {f"{OKHTTP3}:okhttp-jvm", f"{OKHTTP3}:okhttp-android"}
    # Unreadable metadata and constraints add no edge.
    assert graph.get(f"{OKHTTP3}:okhttp-brotli", set()) == set()
    assert "org.c:constraint" not in graph[f"{OKHTTP3}:logging-interceptor"]


def test_okhttp_removal_reaches_logging_interceptor_users(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(remove, "HOME", tmp_path)
    toml = '[libraries]\nokhttp-logging = "com.squareup.okhttp3:logging-interceptor:5.5.0"\n'
    write(tmp_path / "src/app/gradle/libs.versions.toml", toml.encode())
    graph = dependency_graph([], okhttp_cache(tmp_path / "cache"))
    items = [
        Item(name=f"{OKHTTP3}:{a}", source="maven-cache", verdict="foss")
        for a in ("okhttp", "okhttp-android")
    ]
    remove.add_removals(
        items, declarations(tmp_path / "src"), graph, {i.name: [tmp_path / "x"] for i in items}
    )
    assert items[0].removeVia == f"~/src/app via {OKHTTP3}:logging-interceptor → {OKHTTP3}:okhttp"
    assert items[1].removeVia == (
        f"~/src/app via {OKHTTP3}:logging-interceptor → {OKHTTP3}:okhttp → {OKHTTP3}:okhttp-android"
    )
    assert str(items[0].removeCommand).startswith("sed -i -e '\\#^okhttp-logging = ")
