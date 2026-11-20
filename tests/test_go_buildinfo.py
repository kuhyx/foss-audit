"""Go binaries are traced to the kuhyx checkout their build info names."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import make_repo
from go_elf_helpers import MAGIC, buildinfo, elf

from foss_audit import go_buildinfo, scan_misc, scan_unowned

SECTION = ".go.buildinfo"


def test_main_path_of_a_go_binary(tmp_path: Path) -> None:
    binary = elf(
        tmp_path / "diskmap", {".text": b"\x90" * 40, SECTION: buildinfo("github.com/kuhyx/diskmap")}
    )
    assert go_buildinfo.main_path(binary) == "github.com/kuhyx/diskmap"


@pytest.mark.parametrize(
    "sections",
    [
        {".text": b"\x90" * 8},  # no build info section
        {SECTION: b"not a go blob"},  # section without the magic
        {SECTION: MAGIC + b"\x08\x02" + b"\x00" * 16 + b"\x03go1\x00"},  # no modinfo (go run, no module)
    ],
)
def test_no_main_path(tmp_path: Path, sections: dict[str, bytes]) -> None:
    binary = elf(tmp_path / "bin", sections)
    assert go_buildinfo.main_path(binary) == ""
    assert go_buildinfo.go_checkout(binary) is None


def test_built_from_files_names_no_module(tmp_path: Path) -> None:
    binary = elf(tmp_path / "bin", {SECTION: buildinfo("command-line-arguments")})
    assert go_buildinfo.go_checkout(binary) is None


def test_unreadable_elfs_give_nothing(tmp_path: Path) -> None:
    short = tmp_path / "short"
    short.write_bytes(b"\x7fELF" + b"\0" * 12)
    big_endian = tmp_path / "be"
    big_endian.write_bytes(b"\x7fELF\x02\x02\x01" + b"\0" * 57)
    bad_index = elf(tmp_path / "bad", {SECTION: buildinfo("github.com/kuhyx/x")}, shstrndx=99)
    text = tmp_path / "script"
    text.write_text("#!/bin/sh\n")
    assert [go_buildinfo.main_path(p) for p in (short, big_endian, bad_index, text, tmp_path / "gone")] == [
        ""
    ] * 5


def test_huge_section_table_is_not_read(tmp_path: Path) -> None:
    binary = elf(tmp_path / "huge", {SECTION: buildinfo("github.com/kuhyx/x")})
    data = bytearray(binary.read_bytes())
    data[0x3C:0x3E] = (0xFFFF).to_bytes(2, "little")
    binary.write_bytes(bytes(data))
    assert go_buildinfo.main_path(binary) == ""


def diskmap(tmp_path: Path, module: str = "github.com/kuhyx/diskmap", name: str = "bin/diskmap") -> Path:
    return elf(tmp_path / name, {SECTION: buildinfo(module)})


def test_local_bin_go_binary_takes_its_checkout_license(tmp_path: Path) -> None:
    make_repo(tmp_path / "src/diskmap", remote="https://github.com/kuhyx/diskmap.git")
    binary = diskmap(tmp_path)
    item = scan_misc.classify_local_bin(binary, {})
    assert item is not None
    assert (item.id, item.verdict, item.license, item.own) == ("local-bin:diskmap", "foss", "MIT", True)
    assert "github.com/kuhyx/diskmap" in item.reason


def test_unowned_go_binary_takes_its_checkout_license(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_repo(tmp_path / "src/diskmap", remote="https://github.com/kuhyx/diskmap.git")
    binary = diskmap(tmp_path, name="usr/local/bin/diskmap")
    monkeypatch.setattr(scan_unowned, "owned_by_pacman", lambda _paths: set())
    item = scan_unowned.classify(binary, (binary.parent,))
    assert item is not None
    assert (item.id, item.verdict, item.license, item.own) == ("unowned:diskmap", "foss", "MIT", True)


@pytest.mark.parametrize("module", ["github.com/someone/diskmap", "github.com/kuhyx/other"])
def test_foreign_or_unchecked_out_module_stays_unlicensed(tmp_path: Path, module: str) -> None:
    make_repo(tmp_path / "src/diskmap", remote="https://github.com/kuhyx/diskmap.git")
    item = scan_misc.classify_local_bin(diskmap(tmp_path, module), {})
    assert item is not None
    assert (item.verdict, item.license, item.own) == ("nonfree", "", False)


def test_symlinked_go_binary_keeps_its_link_in_the_reason(tmp_path: Path) -> None:
    make_repo(tmp_path / "src/diskmap", remote="https://github.com/kuhyx/diskmap.git")
    real = diskmap(tmp_path, name="share/diskmap")
    link = tmp_path / "bin/diskmap"
    link.parent.mkdir()
    link.symlink_to(real)
    item = scan_misc.classify_local_bin(link, {})
    assert item is not None
    assert (item.verdict, item.license) == ("foss", "MIT")
    assert item.reason.startswith(f"-> {real}, built from Go module")
