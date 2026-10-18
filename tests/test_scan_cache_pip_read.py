"""pip/uv cache readers: wheels, sdists, legacy HTTP entries, dist-info dirs, editables."""

# ruff: noqa: F811  (the autouse no_network fixture is imported)
from __future__ import annotations

import gzip
import io
from pathlib import Path

from foss_audit.scan_cache_pip_read import (
    editable_sources,
    from_editable,
    read_body,
    read_dist_dir,
    read_legacy,
    records_from,
)
from tests.pip_helpers import MIT_TEXT, dist_info, legacy, meta, no_network, rec, sdist, wheel  # noqa: F401

# --- cache readers -------------------------------------------------------------


def test_wheel_license_from_dist_info_files() -> None:
    files = {
        "demo/__init__.py": "",
        "demo-1.0.dist-info/METADATA": meta("demo", "1.0", "License-File: NOTICE"),
        "demo-1.0.dist-info/NOTICE": "",
        "demo-1.0.dist-info/licenses/sub/COPYING": MIT_TEXT,
        "demo-1.0.dist-info/RECORD": "",
    }
    [record] = records_from(io.BytesIO(wheel(files)), "pip http-v2") or []
    assert (record.license, record.license_from) == (
        "MIT",
        "license file demo-1.0.dist-info/licenses/sub/COPYING in pip http-v2",
    )


def test_zip_sdist_and_zip_without_metadata() -> None:
    files = {"demo-1.0/PKG-INFO": meta("demo", "1.0", "License: BSD"), "demo-1.0/x/": ""}
    [record] = records_from(io.BytesIO(wheel(files)), "z") or []
    assert record.license == "BSD"
    assert records_from(io.BytesIO(wheel({"readme.txt": "hi"})), "z") == []
    assert records_from(io.BytesIO(wheel({"demo-1.0.dist-info/METADATA": "Version: 1\n\n"})), "z") == []


def test_corrupt_and_foreign_bodies() -> None:
    assert records_from(io.BytesIO(b"PK\x03\x04garbage"), "x") is None
    assert records_from(io.BytesIO(b"<!DOCTYPE html>"), "x") == []
    assert records_from(io.BytesIO(gzip.compress(b' {"files": []}')), "x") == []
    assert records_from(io.BytesIO(gzip.compress(b"not a tar at all" * 40)), "x") is None


def test_metadata_body() -> None:
    [record] = (
        records_from(io.BytesIO(meta("demo", "3", "License-Expression: Apache-2.0").encode()), "m") or []
    )
    assert (record.version, record.license) == ("3", "Apache-2.0")


def test_sdist_stops_once_license_known() -> None:
    files = {
        "demo-1.0/": "",
        "demo-1.0/src/LICENSE": "nested is ignored",
        "demo-1.0/PKG-INFO": meta("demo", "1.0", "License: MIT"),
        "demo-1.0/LICENSE": "never read",
    }
    [record] = records_from(io.BytesIO(sdist(files)), "s") or []
    assert (record.license, record.license_from) == ("MIT", "License field in s")


def test_sdist_license_file_before_and_after_pkg_info() -> None:
    after = {"demo-1.0/PKG-INFO": meta(), "demo-1.0/README": "", "./demo-1.0/LICENSE.txt": MIT_TEXT}
    [record] = records_from(io.BytesIO(sdist(after)), "s") or []
    assert record.license_from == "license file ./demo-1.0/LICENSE.txt in s"
    before = {"demo-1.0/COPYING": MIT_TEXT, "demo-1.0/PKG-INFO": meta()}
    [record] = records_from(io.BytesIO(sdist(before)), "s") or []
    assert record.license == "MIT"
    assert records_from(io.BytesIO(sdist({"demo-1.0/setup.py": ""})), "s") == []


def test_read_body_and_missing_file(tmp_path: Path) -> None:
    body = tmp_path / "x.body"
    body.write_bytes(meta().encode())
    assert [r.name for r in read_body(body, "o") or []] == ["demo-pkg"]
    assert read_body(tmp_path / "missing", "o") is None


def test_legacy_http_entry(tmp_path: Path) -> None:
    entry = tmp_path / "entry"
    entry.write_bytes(legacy(wheel({"demo-1.0.dist-info/METADATA": meta("demo", "1.0", "License: MIT")})))
    assert [r.license for r in read_legacy(entry, "pip http") or []] == ["MIT"]
    entry.write_bytes(legacy(meta().encode(), b"\xc4"))
    assert len(read_legacy(entry, "pip http") or []) == 1
    for blob in (b"cc=4,\x80", b"cc=4,\xa4body", legacy(b"x", b"\xd9")):
        entry.write_bytes(blob)
        assert read_legacy(entry, "pip http") == []
    assert read_legacy(tmp_path / "missing", "pip http") is None


def test_dist_dir_license_files(tmp_path: Path) -> None:
    path = dist_info(tmp_path, "demo", meta())
    (path.parent / "licenses").mkdir()
    (path.parent / "licenses" / "LICENSE").write_text(MIT_TEXT)
    (path.parent / "RECORD").write_text("")
    [record] = read_dist_dir(path, "uv archive-v0") or []
    assert record.license_from == "license file LICENSE in uv archive-v0"
    assert read_dist_dir(tmp_path / "nope" / "METADATA", "uv") is None
    nameless = dist_info(tmp_path / "b", "x", "Version: 1\n\n")
    assert read_dist_dir(nameless, "uv") == []


def test_editable_install_reads_its_source_license(tmp_path: Path) -> None:
    src = tmp_path / "checkout" / "pkg"
    src.mkdir(parents=True)
    (src / "LICENSE").write_text(MIT_TEXT)
    root = tmp_path / "archive"
    path = dist_info(root, "demo_pkg", meta())
    mapping = {"demo_pkg": str(src / "demo_pkg")}
    (root / "__editable___demo_pkg_1_0_finder.py").write_text(f"MAPPING = {mapping!r}\nx = a / b\n")
    (root / "other.pth").write_text(f"{tmp_path}\n")
    [record] = read_dist_dir(path, "uv archive-v0") or []
    assert (record.license, record.local) == ("MIT", True)
    assert record.license_from == f"LICENSE of editable source {src}"


def test_editable_source_without_license_is_named(tmp_path: Path) -> None:
    good, bad = tmp_path / "good", tmp_path / "bad"
    good.mkdir()
    bad.mkdir()
    (bad / "pyproject.toml").write_text("not = [toml")
    (good / ".git").mkdir()  # a git root whose README names no license
    (tmp_path / "_demo.pth").write_text(f"{bad}\n{good}\n/\n")
    record = from_editable(rec(), tmp_path)
    assert record.local
    assert record.license_from == f"METADATA in x; no license in editable source {bad}, {good}"
    assert editable_sources(tmp_path, "other") == []
    assert from_editable(rec(), tmp_path / "none") == rec()


def test_editable_source_falls_back_to_its_git_root_readme(tmp_path: Path) -> None:
    clone = tmp_path / "unreal-mcp"
    src = clone / "Python"
    src.mkdir(parents=True)
    (clone / ".git").mkdir()
    (clone / "README.md").write_text("# x\n\n## License\nMIT\n\n## Questions\n")
    (tmp_path / "_demo.pth").write_text(f"{src}\n")
    record = from_editable(rec(), tmp_path)
    assert (record.license, record.local) == ("MIT", True)
    assert record.license_from == f"README.md of {clone} names the license (no license file)"


def test_a_wheel_or_archive_of_metadata_only_is_a_meta_package(tmp_path: Path) -> None:
    only = wheel({"m-1.dist-info/METADATA": meta("m", "1"), "m-1.dist-info/RECORD": ""})
    code = wheel({"m-1.dist-info/METADATA": meta("m", "1"), "m/__init__.py": ""})
    [bare] = records_from(io.BytesIO(only), "pip http-v2") or []
    [full] = records_from(io.BytesIO(code), "pip http-v2") or []
    assert (bare.meta, full.meta) == (True, False)
    [unpacked] = read_dist_dir(dist_info(tmp_path / "a", "m", meta("m", "1")), "uv archive-v0") or []
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "m").mkdir()
    [with_code] = read_dist_dir(dist_info(tmp_path / "b", "m", meta("m", "1")), "uv archive-v0") or []
    assert (unpacked.meta, with_code.meta) == (True, False)
