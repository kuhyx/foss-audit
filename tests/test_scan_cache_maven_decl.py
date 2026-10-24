"""Where a ~/src project declares each Maven artifact: build files, version catalogs, pom.xml."""

from __future__ import annotations

from pathlib import Path

from foss_audit import scan_cache_maven_decl as decl
from foss_audit.scan_cache_maven_catalog import read_catalog
from foss_audit.scan_cache_maven_decl import Decl
from tests.maven_helpers import write


def files(src: Path, tree: dict[str, str]) -> None:
    for rel, text in tree.items():
        write(src / rel, text.encode())


def at(decls: dict[str, list[Decl]], name: str) -> list[tuple[str, int, str]]:
    """(file relative to its project, line, edit) of every declaration of `name`."""
    return sorted((str(d.path).split("/src/", 1)[1], d.line, d.edit) for d in decls[name])


GROOVY = """dependencies {
    implementation 'org.x:lib:1.0'
    compile group: 'org.z',
        name: 'zed', version: '1'
    implementation('org.x:blocky:1') {
        transitive = false
    }
    implementation 'org.x:a:1', 'org.x:b:1'
    implementation("org.x:open:1",
}
"""


def test_build_file_lines(tmp_path: Path) -> None:
    src = tmp_path / "src"
    files(src, {"app/build.gradle": GROOVY, "app/node_modules/x/build.gradle": GROOVY})
    decls = decl.declarations(src)
    path = src / "app/build.gradle"
    assert decls["org.x:lib"] == [Decl("~/src/app", path, 2, "    implementation 'org.x:lib:1.0'", "delete")]
    # Spread over two lines, opens a block, or shares its line: only a human can cut it.
    assert at(decls, "org.z:zed") == [("app/build.gradle", 3, "hand")]
    assert at(decls, "org.x:blocky") == [("app/build.gradle", 5, "hand")]
    assert at(decls, "org.x:a") == at(decls, "org.x:b") == [("app/build.gradle", 8, "hand")]
    assert at(decls, "org.x:open") == [("app/build.gradle", 9, "hand")]


SETTINGS = """dependencyResolutionManagement {
    versionCatalogs {
        create("sylibs") {
            from(files("gradle/sy.versions.toml"))
        }
    }
}
"""
LIBS = """[versions]
ui = "1.0"
[libraries]
compose-ui = { module = "androidx.compose.ui:ui", version.ref = "ui" }
compose-ui-tooling = { group = "androidx.compose.ui", name = "ui-tooling", version.ref = "ui" }
okhttp-core = "com.squareup.okhttp3:okhttp:5.0"
okhttp_logging = "com.squareup.okhttp3:logging-interceptor:5.0"
brotli = "com.squareup.okhttp3:okhttp-brotli:5.0"
[plugins]
google-services = { id = "com.google.gms.google-services", version = "4.5.0" }
kotlin-jvm = "org.jetbrains.kotlin.jvm:2.4.0"
[bundles]
okhttp = ["okhttp-core", "okhttp-logging"]
multi = [
    "brotli",
    "okhttp-core", "compose-ui",
]
"""
APP = """pluginManager.apply {
    apply(libs.plugins.google.services.get().pluginId)
}
dependencies {
    implementation(libs.compose.ui)
    debugImplementation(libs.compose.ui.tooling)
    implementation(libs.bundles.okhttp)
    implementation(sylibs.sqlcipher)
    val v = libs.compose.ui.get().version
    implementation(libs.versions.ui)
    implementation(libs.unknown.alias)
}
"""
SQLCIPHER = "net.zetetic:sqlcipher-android:4.19.1"
BUILD_LOGIC = "dependencies {\n    compileOnly(libs.compose.ui)\n}\n"
BUILD_LOGIC_SETTINGS = 'versionCatalogs {\n    create("libs") { from(files("../libs.versions.toml")) }\n}\n'


def catalog_project(src: Path) -> None:
    files(
        src,
        {
            "app/settings.gradle.kts": SETTINGS,
            "app/gradle/libs.versions.toml": LIBS,
            "app/gradle/sy.versions.toml": f"[libraries]\nsqlcipher = {SQLCIPHER!r}\n",
            "app/gradle/broken.versions.toml": 'x = "org.broken:lib:1"\n[[[\n',
            "app/build.gradle.kts": "plugins {\n    alias(libs.plugins.google.services) apply false\n}\n",
            "app/app/build.gradle.kts": APP,
            "app/gradle/build-logic/settings.gradle.kts": BUILD_LOGIC_SETTINGS,
            "app/gradle/build-logic/build.gradle.kts": BUILD_LOGIC,
            # A build with no settings file of its own sees its own default catalog only.
            "lone/build.gradle": "dependencies {\n    implementation libs.compose.ui\n}\n",
        },
    )


def test_catalog_entries_and_references(tmp_path: Path) -> None:
    src = tmp_path / "src"
    catalog_project(src)
    decls = decl.declarations(src)
    assert at(decls, "androidx.compose.ui:ui") == [
        ("app/app/build.gradle.kts", 5, "delete"),
        # An assignment is not a dependency line: deleting it breaks the build.
        ("app/app/build.gradle.kts", 9, "hand"),
        ("app/gradle/build-logic/build.gradle.kts", 2, "delete"),
        ("app/gradle/libs.versions.toml", 4, "delete"),
        ("app/gradle/libs.versions.toml", 16, "hand"),
    ]
    # libs.compose.ui.tooling is not a reference to compose-ui.
    assert at(decls, "androidx.compose.ui:ui-tooling") == [
        ("app/app/build.gradle.kts", 6, "delete"),
        ("app/gradle/libs.versions.toml", 5, "delete"),
    ]
    okhttp = sorted(decls["com.squareup.okhttp3:okhttp"], key=lambda d: d.line)
    assert [(d.line, d.edit, d.alias) for d in okhttp] == [
        (6, "delete", ""),
        (13, "unbundle", "okhttp-core"),
        (16, "hand", ""),
    ]
    assert okhttp[1].text == 'okhttp = ["okhttp-core", "okhttp-logging"]'
    # okhttp_logging is listed as okhttp-logging: the separators are one.
    assert [d.edit for d in decls["com.squareup.okhttp3:logging-interceptor"]] == ["delete", "unbundle"]
    # On a line of its own in a multi-line bundle the member line goes whole.
    assert at(decls, "com.squareup.okhttp3:okhttp-brotli") == [
        ("app/gradle/libs.versions.toml", 8, "delete"),
        ("app/gradle/libs.versions.toml", 15, "delete"),
    ]
    marker = "com.google.gms.google-services:com.google.gms.google-services.gradle.plugin"
    assert at(decls, marker) == [
        ("app/app/build.gradle.kts", 2, "delete"),
        ("app/build.gradle.kts", 2, "delete"),
        ("app/gradle/libs.versions.toml", 10, "delete"),
    ]
    assert at(decls, "org.jetbrains.kotlin.jvm:org.jetbrains.kotlin.jvm.gradle.plugin") == [
        ("app/gradle/libs.versions.toml", 11, "delete")
    ]
    assert at(decls, "net.zetetic:sqlcipher-android") == [
        ("app/app/build.gradle.kts", 8, "delete"),
        ("app/gradle/sy.versions.toml", 2, "delete"),
    ]
    # An unparsable catalog is read like any build file.
    assert at(decls, "org.broken:lib") == [("app/gradle/broken.versions.toml", 1, "hand")]
    assert "~/src/lone" not in {d.project for d in decls["androidx.compose.ui:ui"]}


POM = """<project>
  <dependencies>
    <dependency>
      <groupId>org.apache.kafka</groupId>
      <artifactId>kafka-clients</artifactId>
    </dependency>
    <dependency><groupId>${x}</groupId><artifactId>skip</artifactId></dependency>
  </dependencies>
  <build><plugins><plugin>
      <artifactId>maven-shade-plugin</artifactId>
  </plugin></plugins></build>
</project>
"""


def test_pom_xml(tmp_path: Path) -> None:
    src = tmp_path / "src"
    files(src, {"uni/course/proj/consumer/pom.xml": POM})
    decls = decl.declarations(src)
    assert at(decls, "org.apache.kafka:kafka-clients") == [("uni/course/proj/consumer/pom.xml", 3, "hand")]
    assert at(decls, "org.apache.maven.plugins:maven-shade-plugin") == [
        ("uni/course/proj/consumer/pom.xml", 9, "hand")
    ]
    assert not any(name.endswith(":skip") for name in decls)
    assert decls["org.apache.kafka:kafka-clients"][0].project == "~/src/uni"


ODD = """[libraries]
# comment
plain = "notacoord"
weird = 3
nomodule = { version = "1" }

[libraries.legacy]
module = "org.legacy:lib"
version = "1"
[plugins]
noid = { version = "1" }
num = 4
[bundles]
notalist = "plain"
ghosts = ["missing", "legacy"]
"""


def test_odd_catalog_values(tmp_path: Path) -> None:
    cat = read_catalog(write(tmp_path / "libs.versions.toml", ODD.encode()))
    assert cat is not None
    assert (cat.libraries, cat.plugins) == ({"legacy": "org.legacy:lib"}, {})
    # A sub-table entry spans lines: a human cuts it.
    assert cat.edits == [
        ("org.legacy:lib", 7, "[libraries.legacy]", "hand", ""),
        ("org.legacy:lib", 15, 'ghosts = ["missing", "legacy"]', "unbundle", "legacy"),
    ]
