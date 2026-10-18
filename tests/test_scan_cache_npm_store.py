"""npm-cache scanner: the msgpack reader and pnpm stores (v3/v10/v11), built under tmp_path."""

# ruff: noqa: F811  (the autouse no_network fixture is imported)
from __future__ import annotations

import sqlite3
import struct
from pathlib import Path
from typing import Any

import pytest

from foss_audit.scan_cache_npm_msgpack import unpackb
from foss_audit.scan_cache_npm_pnpm import content_path, entry_hex, package, scan_pnpm_store
from tests.npm_helpers import MIT, json_files, no_network, pkg_json, put, write_json  # noqa: F401

# --- msgpack ---------------------------------------------------------------


def mp(value: Any) -> bytes:
    """Minimal msgpack encoder for fixtures (no records; ints kept out of 0x40-0x7f)."""
    if value is None or isinstance(value, bool):
        return {None: b"\xc0", True: b"\xc3", False: b"\xc2"}[value]
    if isinstance(value, int):
        return bytes([value & 0xFF]) if -32 <= value < 0x40 else b"\xcd" + struct.pack(">H", value)
    if isinstance(value, float):
        return b"\xcb" + struct.pack(">d", value)
    if isinstance(value, bytes | str):
        return mp_raw(value)
    if isinstance(value, list):
        return bytes([0x90 | len(value)]) + b"".join(mp(v) for v in value)
    return bytes([0x80 | len(value)]) + b"".join(mp(k) + mp(v) for k, v in value.items())


def mp_raw(value: bytes | str) -> bytes:
    if isinstance(value, bytes):
        return b"\xc4" + bytes([len(value)]) + value
    raw = value.encode()
    return (bytes([0xA0 | len(raw)]) if len(raw) < 32 else b"\xd9" + bytes([len(raw)])) + raw


def test_msgpack_plain_values_round_trip() -> None:
    value = {"a": [1, -3, None, True, False, 1.5, b"\x01", "x" * 40], "n": 420}
    assert unpackb(mp(value)) == value


def test_msgpack_wide_types() -> None:
    data = (
        b"\x9a"
        + b"\xca"
        + struct.pack(">f", 0.5)
        + b"\xcc\xff\xce\x00\x01\x00\x00\xcf"
        + struct.pack(">Q", 2**40)
        + b"\xd0\xfe\xd1\xff\x00\xd2"
        + struct.pack(">i", -70000)
        + b"\xd3"
        + struct.pack(">q", -(2**40))
        + b"\xda\x00\x02hi\xdc\x00\x01\x01"
    )
    assert unpackb(data) == [0.5, 255, 65536, 2**40, -2, -256, -70000, -(2**40), "hi", [1]]
    assert unpackb(b"\xdd\x00\x00\x00\x01\x05") == [5]
    assert unpackb(b"\xdf\x00\x00\x00\x01\xa1k\x06") == {"k": 6}
    assert unpackb(b"\xdb\x00\x00\x00\x01z") == "z"
    assert unpackb(b"\xc5\x00\x01\x07") == b"\x07"
    assert unpackb(b"\xc6\x00\x00\x00\x01\x08") == b"\x08"
    assert unpackb(b"\xde\x00\x01\xa1k\x02") == {"k": 2}


def test_msgpack_records_define_then_reuse() -> None:
    # d4 72 40: record 0x40 with keys [a, b]; then 0x40 again reuses them.
    blob = b"\x92\xd4\x72\x40\x92\xa1a\xa1b\x01\x02\x40\x03\x04"
    assert unpackb(blob) == [{"a": 1, "b": 2}, {"a": 3, "b": 4}]


def test_msgpack_undefined_record_byte_is_an_int() -> None:
    assert unpackb(b"\x45") == 0x45


@pytest.mark.parametrize(
    ("blob", "message"),
    [(b"\xd4\x01\x00", "extension 0x01"), (b"\xc1", "type 0xc1"), (b"\xa3ab", "truncated")],
)
def test_msgpack_rejects_what_it_does_not_know(blob: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        unpackb(blob)


# --- pnpm store -------------------------------------------------------------


def test_content_path_and_entry_hex(tmp_path: Path) -> None:
    assert content_path(tmp_path, "abcd", 0o755) == tmp_path / "files/ab/cd-exec"
    assert content_path(tmp_path, "abcd", 0o644) == tmp_path / "files/ab/cd"
    assert entry_hex({"digest": "ff"}) == "ff"
    assert entry_hex({"integrity": "sha512-AAE="}) == "0001"
    assert entry_hex({"integrity": "sha512-!!"}) == ""


def test_package_edge_cases(tmp_path: Path) -> None:
    store = tmp_path / "v10"
    # No package.json listed: name from the index, and the gap is named.
    nameless = package(store, json_files(store, {"LICENSE": MIT.encode()}), "a", "1")
    assert nameless is not None
    assert nameless.cached.license == "MIT"
    assert nameless.cached.license_from.endswith("; index lists no package.json")
    assert package(store, {}, "", "") is None
    # Broken package.json: visible, or dropped when nothing names the package.
    broken = json_files(store, {"package.json": b"{"})
    bad = package(store, broken, "b", "2")
    assert bad is not None
    assert "package.json unreadable" in bad.cached.license_from
    assert package(store, broken, "", "") is None
    listed = json_files(store, {"package.json": b"[1]", "lib/x.js": b"", "README": b"## License: ISC"})
    listed["odd"] = "not a dict"
    item = package(store, listed, "c", "3")
    assert item is not None
    assert (item.name, item.cached.license) == ("c", "ISC")
    # A file the index lists but the store lost reads as empty.
    lost = {"package.json": json_files(store, {"package.json": pkg_json(name="d")})["package.json"]}
    lost["LICENSE"] = {"digest": "00" * 64, "mode": 420}
    gone = package(store, lost, "", "")
    assert gone is not None
    assert gone.cached.license == ""


def test_json_layouts(tmp_path: Path) -> None:
    v10 = tmp_path / "v10"
    v10_files = json_files(v10, {"package.json": pkg_json(name="a", version="1.0.0", license="MIT")})
    write_json(v10 / "index/ab/hash-a@1.0.0.json", {"name": "a", "version": "1.0.0", "files": v10_files})
    git = json_files(v10, {"package.json": pkg_json(name="g", version="0.1.0"), "LICENSE": MIT.encode()})
    write_json(v10 / "https+++codeload.github.com+x/integrity.json", {"files": git})
    write_json(v10 / "index/cd/no-files.json", {"name": "z"})
    (v10 / "index/cd/broken.json").write_text("{")
    (v10 / "index/cd/dir.json").mkdir()
    v3 = tmp_path / "v3"
    v3_files = json_files(v3, {"package.json": pkg_json(name="b", version="2.0.0", license="ISC")})
    write_json(v3 / "files/00/hash-index.json", {"name": "b", "version": "2.0.0", "files": v3_files})
    write_json(v3 / "files/00/nameless-index.json", {"files": {}})
    (tmp_path / "v0").write_text("")
    got = {(f.name, f.cached.version, f.cached.license) for f in scan_pnpm_store(tmp_path)}
    assert got == {("a", "1.0.0", "MIT"), ("g", "0.1.0", "MIT"), ("b", "2.0.0", "ISC")}


def make_db(store: Path, rows: list[tuple[str, bytes]]) -> None:
    store.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(store / "index.db")
    conn.execute("CREATE TABLE package_index (key TEXT PRIMARY KEY, data BLOB NOT NULL) WITHOUT ROWID")
    conn.executemany("INSERT INTO package_index VALUES (?, ?)", rows)
    conn.commit()
    conn.close()


def test_v11_database(tmp_path: Path) -> None:
    v11 = tmp_path / "v11"
    pj = put(v11, pkg_json(name="lodash.merge", version="4.6.2", license="MIT")).hex()
    exe = put(v11, b"#!/bin/sh", 0o755).hex()
    lic = put(v11, MIT.encode()).hex()
    good = {
        "algo": "sha512",
        "files": {
            "package.json": {"digest": pj, "mode": 420, "size": 1, "checkedAt": 1.5},
            "cli.js": {"digest": exe, "mode": 493},
        },
        "manifest": {"name": "lodash.merge", "version": "4.6.2"},
    }
    # Manifest-less row: the name comes from the "<integrity>\t<name>@<ver>" key.
    keyed = {"files": {"LICENSE": {"digest": lic, "mode": 420}}, "manifest": "odd"}
    git = {"files": {"LICENSE": {"digest": lic, "mode": 420}}}
    rows = [
        ("sha512-a\tlodash.merge@4.6.2", mp(good)),
        ("sha512-b\t@s/keyed@1.0.0", mp(keyed)),
        ("sha512-c\thttps://codeload.github.com/x/y@z", mp(git)),
        ("sha512-d\tnoat", mp(git)),
        ("sha512-e\tbad@1", b"\xc1"),
        ("sha512-f\tlist@1", mp([1])),
        ("sha512-g\tnofiles@1", mp({"files": []})),
    ]
    make_db(v11, rows)
    (v11 / "index.db-wal").write_bytes(b"")
    got = {(f.name, f.cached.version, f.cached.license) for f in scan_pnpm_store(tmp_path)}
    assert got == {("lodash.merge", "4.6.2", "MIT"), ("@s/keyed", "", "MIT")}
    assert not (v11 / "index.db-journal").exists()
