"""scan_cache_pub_parse: pubspec.yaml and pubspec.lock reading without a YAML parser."""

from __future__ import annotations

from foss_audit.scan_cache_pub_parse import lock_packages, parse_pubspec

PUBSPEC = """\
name: "foo_bar"   # the package
version: 1.2.3
homepage: https://example.org/foo
repository: 'https://github.com/x/foo_bar'
environment:
  sdk: ^3.0.0
dependencies:
  flutter:
    sdk: flutter
  http: ^1.0.0
  meta: any # comment
  flutter_web_plugins: {sdk: flutter}

  path:
    version: ^1.0.0
dev_dependencies:
  test: any
"""


# --- pubspec / lock parsing -------------------------------------------------


def test_parse_pubspec_reads_top_level_and_runtime_deps() -> None:
    spec = parse_pubspec(PUBSPEC)
    assert (spec.name, spec.version) == ("foo_bar", "1.2.3")
    assert spec.url == "https://github.com/x/foo_bar"
    assert spec.deps == ("http", "meta", "path")


def test_parse_pubspec_four_space_dependency_block() -> None:
    spec = parse_pubspec(
        "name: a\ndependencies:\n    # c\n    async: ^2.5.0\n    flutter:\n        sdk: flutter\n"
    )
    assert spec.deps == ("async",)


def test_parse_pubspec_homepage_when_no_repository_and_missing_fields() -> None:
    assert parse_pubspec("name: a\nhomepage: https://h\n").url == "https://h"
    empty = parse_pubspec("# nothing\n")
    assert (empty.name, empty.version, empty.url, empty.deps) == ("", "", "", ())


def test_lock_packages_only_two_space_keys_under_packages() -> None:
    lock = (
        "packages:\n  http:\n    description:\n      name: http\n      url: x\n"
        "  meta:\n    source: hosted\nsdks:\n  dart: '>=3.0.0'\n"
    )
    assert lock_packages(lock) == ["http", "meta"]
