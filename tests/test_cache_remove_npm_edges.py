"""npm-cache remove commands: old lockfile formats and cache entries that name no package."""

# ruff: noqa: F811  (the autouse no_network fixture is imported)
from __future__ import annotations

from pathlib import Path

from foss_audit.cache_remove_npm import manifests, package_lock, pnpm_lock
from foss_audit.cache_remove_npm_store import NpmCache
from tests.npm_helpers import REG, cache_entry, no_network, tgz, write_json  # noqa: F401
from tests.test_scan_cache_npm_store import make_db, mp


def test_single_project_pnpm_lock_v6_and_v5_keys() -> None:
    text = (
        "lockfileVersion: '6.0'\ndependencies:\n  foo:\n    specifier: 1.0.0\n    version: 1.0.0\n"
        "devDependencies:\n  bar: 2.0.0\npackages:\n  /baz/1.0.0:\n    dependencies:\n      qux: 1.0.0\n"
        "not a mapping line\n"
    )
    importers, graph, local = pnpm_lock(text)
    assert importers == {".": {"foo": "pnpm", "bar": "pnpm"}}
    assert graph == {}
    assert local == set()


def test_explicit_yaml_keys_of_long_snapshots() -> None:
    long_key = (
        "  ? '@angular/material@18.0.1("
        + "x" * 1100
        + ")'\n  : dependencies:\n      '@material/theme': 15.0.0\n"
    )
    _importers, graph, _local = pnpm_lock(f"snapshots:\n\n{long_key}\n  other@1.0.0: {{}}\n")
    assert graph == {"@angular/material": {"@material/theme"}, "other": set()}


def test_double_quoted_keys() -> None:
    text = 'importers:\n  packages/b:\n    dependencies:\n      "@n/c":\n        version: 1.0.0\n'
    text += 'snapshots:\n  "@n/c@1.0.0":\n    dependencies:\n      "@n/d": 1.0.0\n'
    importers, graph, _local = pnpm_lock(text)
    assert (importers, graph) == ({"packages/b": {"@n/c": "pnpm"}}, {"@n/c": {"@n/d"}})


def test_v1_lock_without_a_package_json(tmp_path: Path) -> None:
    doc = {"lockfileVersion": 1, "dependencies": {"a": "not a table", "b": {"requires": {"c": "1"}}}}
    importers, graph, _local = package_lock(doc, tmp_path)
    assert importers == {"": {}}
    assert graph == {"b": {"c"}}


def test_unparsable_lockfiles_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "p").mkdir()
    (tmp_path / "p/package-lock.json").write_text("{")
    assert manifests(tmp_path) == []


def test_entries_that_name_no_package_are_skipped(tmp_path: Path) -> None:
    cache = tmp_path / "_cacache"
    cache_entry(cache, REG + "gone/-/gone-1.0.0.tgz", b"x")
    for path in [p for p in (cache / "content-v2").rglob("*") if p.is_file()]:
        path.unlink()
    nameless = tgz([("package/README.md", b"no package.json")])
    cache_entry(cache, "make-fetch-happen:request-cache:https://codeload.github.com/a/b/tar.gz/1", nameless)
    store = tmp_path / "store/v10"
    write_json(store / "index/aa/h-x@1.json", ["not", "a", "doc"])
    (store / "index/aa/bad@1.json").write_text("{")
    make_db(store, [("https://codeload.github.com/x\tbuilt", b"\xc1"), ("sha512-z\tnoat", mp({"files": {}}))])
    npm = NpmCache(cache, tmp_path / "store")
    assert (npm.clean, npm.paths, npm.rows) == ({}, {}, {})
    assert npm.step("anything") == ("", "")
