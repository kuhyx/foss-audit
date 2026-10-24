"""Maven removeCommand: drop the dependency from every ~/src project that reaches it, then the cache."""

from __future__ import annotations

import os
import subprocess
import tomllib
from pathlib import Path

import pytest

from foss_audit import scan_cache_maven_remove as remove
from foss_audit.model import Item
from foss_audit.scan_cache_maven_decl import declarations
from tests.maven_helpers import write
from tests.test_scan_cache_maven_decl import catalog_project, files

GRADLE = ".gradle/caches/modules-2/files-2.1"
ANALYTICS = "com.google.firebase:firebase-analytics"
MEASUREMENT = "com.google.android.gms:play-services-measurement"
BASEMENT = "com.google.android.gms:play-services-basement"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(remove, "HOME", tmp_path)
    return tmp_path


def item(name: str, *required: str) -> Item:
    return Item(name=name, source="maven-cache", verdict="nonfree", requiredBy=list(required))


def cache(home: Path, *names: str) -> dict[str, list[Path]]:
    """A Gradle cache dir per name, created so the command has something to delete."""
    dirs = {}
    for name in names:
        path = home / GRADLE / name.replace(":", "/")
        write(path / "1/abc/x.pom", b"")
        dirs[name] = [path]
    return dirs


def run(command: str, home: Path) -> None:
    """The command as the user would paste it; $EDITOR steps do nothing here."""
    env = {**os.environ, "HOME": str(home), "EDITOR": "true"}
    done = subprocess.run(["bash", "-c", command], env=env, capture_output=True, text=True, check=True)
    assert done.stderr == ""


def test_direct_line(home: Path) -> None:
    files(home / "src", {"app/build.gradle": "dependencies {\n    implementation 'org.x:lib:1.0'\n}\n"})
    lib = item("org.x:lib", "~/src/app")
    remove.add_removals([lib], declarations(home / "src"), {}, cache(home, "org.x:lib"))
    assert lib.removeCommand == (
        "sed -i -e '\\#^    implementation '\"'\"'org\\.x:lib:1\\.0'\"'\"'$#d' ~/src/app/build.gradle; "
        "rm -rf ~/.gradle/caches/modules-2/files-2.1/org.x/lib"
    )
    assert lib.removeVia == "~/src/app declares it"
    run(lib.removeCommand, home)
    assert (home / "src/app/build.gradle").read_text() == "dependencies {\n}\n"
    assert not (home / GRADLE / "org.x/lib").exists()


def test_catalog_entry_references_and_bundles(home: Path) -> None:
    src = home / "src"
    catalog_project(src)
    okhttp, ui = item("com.squareup.okhttp3:okhttp", "~/src/app"), item("androidx.compose.ui:ui", "~/src/app")
    dirs = cache(home, okhttp.name, ui.name)
    remove.add_removals([okhttp, ui], declarations(src), {}, dirs)
    assert okhttp.removeCommand is not None and ui.removeCommand is not None
    # Hand edits first, bottom-up, so their line numbers still hold; the seds match by content.
    assert ui.removeCommand.startswith(
        "${EDITOR:-vi} +9 ~/src/app/app/build.gradle.kts; "
        "${EDITOR:-vi} +16 ~/src/app/gradle/libs.versions.toml; "
    )
    run(okhttp.removeCommand, home)
    catalog = tomllib.loads((src / "app/gradle/libs.versions.toml").read_text())
    assert "okhttp-core" not in catalog["libraries"]
    assert catalog["bundles"]["okhttp"] == ["okhttp-logging"]
    run(ui.removeCommand, home)
    app = (src / "app/app/build.gradle.kts").read_text()
    assert "implementation(libs.compose.ui)\n" not in app
    assert "debugImplementation(libs.compose.ui.tooling)" in app
    assert "libs.compose.ui" not in (src / "app/gradle/build-logic/build.gradle.kts").read_text()
    catalog = tomllib.loads((src / "app/gradle/libs.versions.toml").read_text())
    assert set(catalog["libraries"]) == {"compose-ui-tooling", "okhttp_logging", "brotli"}
    assert not dirs[okhttp.name][0].exists() and not dirs[ui.name][0].exists()


def test_bundle_unbundle_every_position(home: Path) -> None:
    toml = '[libraries]\na = "g:a:1"\nb = "g:b:1"\nc = "g:c:1"\nsolo = "g:solo:1"\n'
    toml += '[bundles]\nabc = [\'a\', "b" , "c"]\none = ["solo"]\n'
    files(home / "src", {"p/gradle/libs.versions.toml": toml})
    items = [item(f"g:{n}", "~/src/p") for n in ("a", "b", "c", "solo")]
    remove.add_removals(items, declarations(home / "src"), {}, cache(home, *(i.name for i in items)))
    for it in items:
        run(str(it.removeCommand), home)
    catalog = tomllib.loads((home / "src/p/gradle/libs.versions.toml").read_text())
    assert catalog == {"libraries": {}, "bundles": {"abc": [], "one": []}}


def test_transitive_chain_through_the_pom_graph(home: Path) -> None:
    files(
        home / "src",
        {"app/build.gradle.kts": f'dependencies {{\n    implementation("{ANALYTICS}:22.0")\n}}\n'},
    )
    graph = {ANALYTICS: {MEASUREMENT}, MEASUREMENT: {BASEMENT, ANALYTICS}, BASEMENT: set()}
    # requiredBy is empty: no build file names it, yet a declared artifact pulls it in.
    basement = item(BASEMENT)
    remove.add_removals([basement], declarations(home / "src"), graph, cache(home, BASEMENT))
    assert basement.removeVia == f"~/src/app via {ANALYTICS} → {MEASUREMENT} → {BASEMENT}"
    assert basement.removeCommand == (
        "sed -i -e '\\#^    implementation(\"com\\.google\\.firebase:firebase-analytics:22\\.0\")$#d' "
        f"~/src/app/build.gradle.kts; rm -rf ~/{GRADLE}/com.google.android.gms/play-services-basement"
    )


def test_declared_and_transitive_in_one_project(home: Path) -> None:
    lines = [f'    implementation("{ANALYTICS}:22.0")', f'    implementation("{BASEMENT}:18.0")']
    lines += [f'    implementation("org.p:p{n}:1")' for n in range(6)]
    files(home / "src", {"app/build.gradle.kts": "\n".join(lines) + "\n"})
    graph = {ANALYTICS: {BASEMENT}} | {f"org.p:p{n}": {BASEMENT} for n in range(6)}
    basement = item(BASEMENT, "~/src/app")
    remove.add_removals([basement], declarations(home / "src"), graph, cache(home, BASEMENT))
    assert basement.removeVia == (
        f"~/src/app declares it and via {ANALYTICS} → {BASEMENT}, org.p:p0 → {BASEMENT}, "
        f"org.p:p1 → {BASEMENT}, org.p:p2 → {BASEMENT}, org.p:p3 → {BASEMENT} and 2 more"
    )
    run(str(basement.removeCommand), home)
    assert (home / "src/app/build.gradle.kts").read_text() == ""


def test_many_projects_one_cache_delete(home: Path) -> None:
    toml = '[libraries]\nandroidx-activity-compose = { module = "androidx.activity:activity-compose" }\n'
    ref = "dependencies {\n    implementation(libs.androidx.activity.compose)\n}\n"
    tree = {f"{p}/gradle/libs.versions.toml": toml for p in ("b1", "b2")}
    files(home / "src", tree | {f"{p}/app/build.gradle.kts": ref for p in ("b1", "b2")})
    activity = item("androidx.activity:activity-compose", "~/src/b1", "~/src/b2")
    remove.add_removals([activity], declarations(home / "src"), {}, cache(home, activity.name))
    assert activity.removeVia == "~/src/b1 declares it; ~/src/b2 declares it"
    command = str(activity.removeCommand)
    assert command.count("rm -rf") == 1 and command.endswith("androidx.activity/activity-compose")
    assert command.index("~/src/b1/") < command.index("~/src/b2/")
    run(command, home)
    for project in ("b1", "b2"):
        assert "activity" not in (home / f"src/{project}/app/build.gradle.kts").read_text()
        assert "activity" not in (home / f"src/{project}/gradle/libs.versions.toml").read_text()


def test_stale_deletes_only_its_cache_dirs(home: Path, tmp_path: Path) -> None:
    gradle, m2 = home / GRADLE / "org.stale/old", home / ".m2/repository/org/stale/old"
    elsewhere = tmp_path.parent / "other root/org.stale/old"
    stale = item("org.stale:old")
    remove.add_removals([stale], {}, {}, {stale.name: [gradle, m2, elsewhere]})
    assert stale.removeCommand == (
        f"rm -rf ~/{GRADLE}/org.stale/old ~/.m2/repository/org/stale/old '{elsewhere}'"
    )
    assert stale.removeVia == "stale: no ~/src project reaches it"


def test_quoted_project_path(home: Path) -> None:
    files(home / "src", {"my app/build.gradle": "    implementation 'org.x:lib:1.0'\n"})
    lib = item("org.x:lib", "~/src/my app")
    remove.add_removals([lib], declarations(home / "src"), {}, cache(home, "org.x:lib"))
    assert "~/'src/my app/build.gradle'; rm -rf" in str(lib.removeCommand)
    run(str(lib.removeCommand), home)
    assert (home / "src/my app/build.gradle").read_text() == ""
