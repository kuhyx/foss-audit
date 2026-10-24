"""npm-cache scanner: npm _cacache tarballs, lockfiles, merge and the end-to-end scan.

Every store is built as a fixture under tmp_path; nothing touches the network
or the real caches.
"""

# ruff: noqa: F811  (the autouse no_network fixture is imported)
from __future__ import annotations

import json
from pathlib import Path

import pytest

from foss_audit import (
    scan_cache_npm,
    scan_cache_npm_cacache,
    scan_cache_npm_pnpm,
)
from foss_audit.cache_common import CachedVersion
from foss_audit.scan_cache_npm import (
    lock_users,
    merge,
    package_lock_names,
    pnpm_lock_names,
    scan_npm_cache,
)
from foss_audit.scan_cache_npm_cacache import (
    content_path as cache_content_path,
)
from foss_audit.scan_cache_npm_cacache import (
    index_entries,
    key_spec,
    read_tarball,
    scan_cacache,
    tarball_spec,
)
from foss_audit.scan_cache_npm_manifest import (
    Found,
)
from tests.npm_helpers import MIT, REG, cache_entry, json_files, no_network, pkg_json, tgz, write_json  # noqa: F401

# --- npm _cacache -----------------------------------------------------------


def test_tarball_and_key_specs() -> None:
    assert tarball_spec("https://registry.npmjs.org/a/-/a-1.0.0.tgz") == ("a", "1.0.0")
    assert tarball_spec("https://registry.npmjs.org/@s%2fb/-/b-2.0.0.tgz") == ("@s/b", "2.0.0")
    assert tarball_spec("https://registry.npmjs.org/@s/b/-/@s/b-2.0.0.tgz") == ("@s/b", "2.0.0")
    assert tarball_spec("https://registry.npmjs.org/a/-/other-1.tgz") == ("a", "")
    assert tarball_spec("https://codeload.github.com/u/r/tar.gz/abc") == ("", "")
    assert tarball_spec("https://registry.npmjs.org/a") is None
    assert key_spec("pacote:tarball:@s/x@1.2.3") == ("@s/x", "1.2.3")
    assert key_spec("pacote:tarball:github:u/r#abc") == ("", "")
    assert key_spec(REG + "a/-/a-1.tgz") == ("a", "1")
    assert key_spec("security-advisory:a:xyz") is None


def test_content_path_rejects_bad_integrity(tmp_path: Path) -> None:
    assert cache_content_path(tmp_path, "sha512-!!") is None
    assert cache_content_path(tmp_path, "-AAE=") is None
    assert cache_content_path(tmp_path, "sha512-") is None
    assert cache_content_path(tmp_path, "sha1-AAECAw== sha512-x") == tmp_path / "content-v2/sha1/00/01/0203"


def test_index_keeps_newest_live_tarball_lines(tmp_path: Path) -> None:
    cache_entry(tmp_path, REG + "a/-/a-1.tgz", b"old")
    cache_entry(tmp_path, REG + "a/-/a-1.tgz", b"new")
    cache_entry(tmp_path, REG + "gone/-/gone-1.tgz", b"x")
    cache_entry(tmp_path, REG + "gone/-/gone-1.tgz", None)
    cache_entry(tmp_path, REG + "packument", b"{}")
    cache_entry(tmp_path, "pacote:tarball:l@1", None, raw='[{"key":"pacote:tarball:l@1"}]')
    cache_entry(tmp_path, "pacote:tarball:j@1", None, raw='{"key":"pacote:tarball:j@1"')
    cache_entry(tmp_path, "pacote:tarball:k@1", None, raw='{"x":{"key":"pacote:tarball:k@1"}}')
    (tmp_path / "index-v5/zz/zz/dir").mkdir(parents=True)
    entries = index_entries(tmp_path)
    assert list(entries) == [REG + "a/-/a-1.tgz"]
    path = cache_content_path(tmp_path, entries[REG + "a/-/a-1.tgz"]["integrity"])
    assert path is not None
    assert path.read_bytes() == b"new"


def test_read_tarball(tmp_path: Path) -> None:
    def tarball(name: str, members: list[tuple[str, bytes | None]]) -> Path:
        path = tmp_path / name
        path.write_bytes(tgz(members))
        return path

    licensed = tarball(
        "a",
        [
            ("package", None),
            ("package/lib", None),
            ("package/README.md", b"## License: ISC"),
            ("package/lib/package.json", b"{}"),
            ("package/index.js", b""),
            ("package/package.json", pkg_json(name="a", version="1", license="MIT", dependencies={"b": "1"})),
            ("package/LICENSE", b"never read"),
        ],
    )
    item = read_tarball(licensed, "", "")
    assert item is not None
    assert (item.name, item.cached.license, item.cached.deps) == ("a", "MIT", ("b",))
    # package.json first, then the file its pointer names.
    pointer = tarball(
        "b",
        [("./package/package.json", pkg_json(license="SEE LICENSE IN LICENSE")), ("./package/LICENSE", b"")],
    )
    item = read_tarball(pointer, "b", "2")
    assert item is not None
    assert (item.name, item.cached.version) == ("b", "2")
    assert item.cached.license.startswith("SEE LICENSE IN LICENSE")
    listed = tarball("c", [("package/package.json", b"[1]"), ("package/LICENSE", MIT.encode())])
    item = read_tarball(listed, "c", "3")
    assert item is not None
    assert item.cached.license == "MIT"
    assert read_tarball(listed, "", "") is None


def test_read_tarball_failures_are_visible(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt"
    corrupt.write_bytes(b"not gzip")
    item = read_tarball(corrupt, "x", "1")
    assert item is not None
    assert item.cached.license == ""
    assert "package.json unreadable (ReadError" in item.cached.license_from
    assert read_tarball(corrupt, "", "") is None
    empty = tmp_path / "empty"
    empty.write_bytes(tgz([("package/index.js", b"")]))
    item = read_tarball(empty, "y", "1")
    assert item is not None
    assert "tarball has no package.json" in item.cached.license_from
    assert read_tarball(empty, "", "") is None


def test_scan_cacache_skips_known_versions(tmp_path: Path) -> None:
    cache_entry(tmp_path, REG + "a/-/a-1.tgz", tgz([("package/package.json", pkg_json(license="MIT"))]))
    cache_entry(tmp_path, REG + "b/-/b-1.tgz", tgz([("package/package.json", pkg_json(license="ISC"))]))
    git = tgz([("repo-abc/package.json", pkg_json(name="g", version="1.0.0", license="MIT"))])
    cache_entry(tmp_path, "pacote:tarball:github:u/g#abc", git)
    cache_entry(tmp_path, "pacote:tarball:file:/x", tgz([("package/package.json", b"{}")]))
    missing = json.dumps({"key": REG + "m/-/m-1.tgz", "integrity": "sha512-AAE="}, separators=(",", ":"))
    cache_entry(tmp_path, REG + "m/-/m-1.tgz", None, raw=missing)
    cache_entry(tmp_path, REG + "codeload", b"{}")
    bad = json.dumps({"key": REG + "n/-/n-1.tgz", "integrity": "sha512-!!"}, separators=(",", ":"))
    cache_entry(tmp_path, REG + "n/-/n-1.tgz", None, raw=bad)
    got = scan_cacache({("a", "1")}, tmp_path)
    assert {(f.name, f.cached.version, f.cached.license) for f in got} == {
        ("b", "1", "ISC"),
        ("g", "1.0.0", "MIT"),
    }


# --- lockfiles, merge, end to end -------------------------------------------

PNPM_LOCK = """lockfileVersion: '9.0'

importers:

  .:
    dependencies:
      left-pad:
        specifier: 1.0.0

packages:

  '@scope/pkg@1.0.0':
    resolution: {integrity: sha512-x}

  /old-style@2.0.0:
    resolution: {integrity: sha512-y}

snapshots:

  react-dom@18.2.0(react@18.2.0):
    dependencies:
      react: 18.2.0
"""


def test_pnpm_lock_names() -> None:
    assert pnpm_lock_names(PNPM_LOCK) == {"@scope/pkg", "old-style", "react-dom"}
    # A prettier-formatted lock quotes keys with double quotes.
    assert pnpm_lock_names('packages:\n  "@s/q@1.0.0":\n    resolution: {}\n') == {"@s/q"}


def test_package_lock_names() -> None:
    v3 = {"packages": {"": {}, "node_modules/a": {}, "node_modules/a/node_modules/@s/b": {}}}
    assert package_lock_names(json.dumps(v3)) == {"a", "@s/b"}
    v1 = {"dependencies": {"x": {"dependencies": {"y": {}, "z": "bad"}}, "w": "1"}}
    assert package_lock_names(json.dumps(v1)) == {"x", "y", "z", "w"}
    assert package_lock_names(json.dumps({"packages": [], "dependencies": []})) == set()
    assert package_lock_names("{") == set()
    assert package_lock_names("[]") == set()


def test_lock_users(tmp_path: Path) -> None:
    write_json(tmp_path / "web/package-lock.json", {"packages": {"node_modules/a": {}}})
    (tmp_path / "app/sub").mkdir(parents=True)
    (tmp_path / "app/sub/pnpm-lock.yaml").write_text(PNPM_LOCK)
    paths = [tmp_path / "web/package-lock.json", tmp_path / "app/sub/pnpm-lock.yaml", tmp_path / "gone.json"]
    users = lock_users(paths, tmp_path)
    assert users["a"] == {"~/src/web"}
    assert users["react-dom"] == {"~/src/app"}


def test_merge_prefers_a_licensed_reading() -> None:
    def seen(version: str, lic: str) -> Found:
        return Found("p", "u", CachedVersion(version, lic, "x"))

    arts = merge([seen("1", ""), seen("1", "MIT"), seen("1", ""), seen("2", "ISC"), seen("2", "MIT")])
    assert [(v.version, v.license) for v in arts[0].versions] == [("1", "MIT"), ("2", "ISC")]


def test_scan_npm_cache_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = tmp_path / "store"
    v10 = store / "v10"
    shared = json_files(v10, {"package.json": pkg_json(name="free", version="1.0.0", license="MIT")})
    write_json(v10 / "index/aa/h-free@1.0.0.json", {"name": "free", "version": "1.0.0", "files": shared})
    cache = tmp_path / "cache"
    # Same version again in npm's cache (read once), plus a non-free dependency.
    cache_entry(cache, REG + "free/-/free-1.0.0.tgz", b"never opened")
    lib = pkg_json(name="lib", version="2.0.0", license="MIT", dependencies={"closed": "1"})
    cache_entry(cache, REG + "lib/-/lib-2.0.0.tgz", tgz([("package/package.json", lib)]))
    closed = tgz([("package/package.json", pkg_json(name="closed", version="1.0.0"))])
    cache_entry(cache, REG + "closed/-/closed-1.0.0.tgz", closed)
    src = tmp_path / "src"
    write_json(src / "proj/package-lock.json", {"packages": {"node_modules/lib": {}}})
    monkeypatch.setattr(scan_cache_npm_pnpm, "STORE", store)
    monkeypatch.setattr(scan_cache_npm_cacache, "CACACHE", cache)
    monkeypatch.setattr(scan_cache_npm, "SRC", src)
    items = {i.name: i for i in scan_npm_cache()}
    assert {n: i.verdict for n, i in items.items()} == {
        "closed": "nonfree",
        "free": "foss",
        "lib": "foss-partial",
    }
    assert items["lib"].requiredBy == ["~/src/proj"]
    assert items["lib"].source == "npm-cache"
    assert items["closed"].reason.startswith("no license")
    assert "npm _cacache tarball" in items["closed"].reason
    assert items["free"].url == "https://www.npmjs.com/package/free"
