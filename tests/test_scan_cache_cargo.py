"""scan_cache_cargo: licenses read from each crate copy, deps, used_by (no network)."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from foss_audit import scan_cache_cargo as cargo
from foss_audit import upstream_license

MIT = "Permission is hereby granted, free of charge, to any person...\n"
APACHE = "Apache License\nVersion 2.0, January 2004\n"
INDEX = "index.crates.io-1949cf8c6b5b557f"


@pytest.fixture(autouse=True)
def upstream(monkeypatch: pytest.MonkeyPatch) -> dict[str, tuple[str, str]]:
    """Canned upstream answers by URL; a URL not listed fails the test (no network, ever)."""
    answers: dict[str, tuple[str, str]] = {}
    monkeypatch.setattr(upstream_license, "upstream_license", answers.__getitem__)
    return answers


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(cargo, "CARGO", tmp_path / ".cargo")
    monkeypatch.setattr(cargo, "SRC", tmp_path / "src")
    return tmp_path


def toml(name: str, version: str, extra: str = 'license = "MIT"', deps: str = "") -> str:
    return f'[package]\nname = "{name}"\nversion = "{version}"\n{extra}\n{deps}'


def make_crate(home: Path, stem: str, files: list[tuple[str, str]], index: str = INDEX) -> Path:
    """A .crate (gzip tar) whose members are written in the given order."""
    path = home / ".cargo/registry/cache" / index / f"{stem}.crate"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w:gz") as tf:
        top = tarfile.TarInfo(stem)
        top.type = tarfile.DIRTYPE
        tf.addfile(top)
        for rel, text in files:
            info = tarfile.TarInfo(rel if rel.startswith("other/") else f"{stem}/{rel}")
            data = text.encode()
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return path


def make_dir(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True)
    for rel, text in files.items():
        (root / rel).write_text(text)
    return root


def versions(home: Path) -> dict[str, list[tuple[str, str, str, tuple[str, ...]]]]:
    return {
        a.name: [(v.version, v.license, v.license_from, v.deps) for v in a.versions]
        for a in cargo.cached_artifacts()
    }


def test_declared_license_deps_and_url_from_crate(home: Path) -> None:
    deps = (
        '[dependencies]\nserde = "1"\nrn = { package = "real-name", version = "1" }\n'
        'opt = { version = "1", optional = true }\nkept = { version = "1", optional = false }\n'
        '[dev-dependencies]\ntest-only = "1"\n[build-dependencies]\ncc = "1"\n'
    )
    extra = 'license = "MIT OR Apache-2.0"\nrepository = "https://example.org/r"'
    make_crate(
        home,
        "foo-bar-1.2.3",
        [("other/Cargo.toml", "junk"), ("Cargo.toml", toml("foo-bar", "1.2.3", extra, deps))],
    )
    [art] = cargo.cached_artifacts()
    assert (art.name, art.url) == ("foo-bar", "https://example.org/r")
    assert [(v.version, v.license, v.license_from) for v in art.versions] == [
        ("1.2.3", "MIT OR Apache-2.0", "Cargo.toml license (.crate)")
    ]
    assert art.versions[0].deps == ("kept", "real-name", "serde")


def test_license_file_before_cargo_toml_is_read_on_second_pass(home: Path) -> None:
    files = [("COPYING", MIT), ("Cargo.toml", toml("a", "0.1.0", 'license-file = "COPYING"'))]
    make_crate(home, "a-0.1.0", files)
    assert versions(home)["a"] == [("0.1.0", "MIT", "license-file COPYING (.crate)", ())]


def test_workspace_license_falls_back_to_license_files(home: Path) -> None:
    extra = 'license.workspace = true\nhomepage = "https://h.example"'
    files = [("Cargo.toml", toml("b", "1.0.0", extra)), ("LICENSE-MIT", MIT), ("LICENSE-APACHE", APACHE)]
    make_crate(home, "b-1.0.0", files)
    assert versions(home)["b"] == [("1.0.0", "Apache-2.0 AND MIT", "LICENSE/COPYING files (.crate)", ())]
    assert cargo.cached_artifacts()[0].url == "https://h.example"


def test_no_license_anywhere_names_every_place_checked(home: Path) -> None:
    make_crate(home, "c-1.0.0", [("Cargo.toml", toml("c", "1.0.0", 'license-file = "missing.txt"'))])
    make_crate(home, "d-2.0.0", [("README.md", "hi")])
    found = versions(home)
    assert found["c"][0][1:3] == (
        "",
        "Cargo.toml license (.crate), license-file missing.txt, LICENSE*/COPYING* files in the crate root",
    )
    # No Cargo.toml at all: name/version from the stem, still says where it looked.
    assert found["d"][0][:2] == ("2.0.0", "")
    [c, d] = cargo.scan_cargo_cache()
    assert (c.verdict, d.verdict) == ("nonfree", "nonfree")
    assert "checked Cargo.toml license (.crate)" in c.reason
    assert c.url == "https://crates.io/crates/c"


def test_corrupt_crate_is_visible_not_fatal(home: Path) -> None:
    for stem in ("bad-crate-0.1.0", "weird"):
        path = home / ".cargo/registry/cache" / INDEX / f"{stem}.crate"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not a tarball")
    found = versions(home)
    assert found["bad-crate"][0][:2] == ("0.1.0", "")
    assert found["bad-crate"][0][2].startswith("unreadable bad-crate-0.1.0.crate: ReadError")
    assert found["weird"][0][0] == "weird"


def test_src_dir_wins_over_its_crate_and_duplicates_collapse(home: Path) -> None:
    src = home / ".cargo/registry/src" / INDEX
    make_dir(
        src / "e-2.0.0", {"Cargo.toml": toml("e", "2.0.0", 'license = "MIT"\nrepository = "https://new"')}
    )
    make_crate(home, "e-2.0.0", [("Cargo.toml", toml("e", "2.0.0", 'license = "GPL-3.0"'))])
    make_crate(
        home, "e-2.0.0", [("Cargo.toml", toml("e", "2.0.0", 'license = "GPL-3.0"'))], index="other-idx"
    )
    make_crate(
        home, "e-1.0.0", [("Cargo.toml", toml("e", "1.0.0", 'license = "MIT"\nrepository = "https://old"'))]
    )
    [art] = cargo.cached_artifacts()
    assert [(v.version, v.license, v.license_from) for v in art.versions] == [
        ("2.0.0", "MIT", "Cargo.toml license (src dir)"),
        ("1.0.0", "MIT", "Cargo.toml license (.crate)"),
    ]
    assert art.url == "https://new"


def test_src_dir_license_files_stay_inside_the_crate(home: Path) -> None:
    src = home / ".cargo/registry/src" / INDEX
    (src / "outside").parent.mkdir(parents=True)
    (src / "LICENSE").write_text(MIT)  # one level up: must not be read
    extra = 'license-file = "../LICENSE"'
    root = make_dir(src / "f-1.0.0", {"Cargo.toml": toml("f", "1.0.0", extra), "COPYING": APACHE})
    (root / "LICENSE.d").mkdir()
    make_dir(src / "g-1.0.0", {"README": "no manifest"})
    found = versions(home)
    assert found["f"] == [("1.0.0", "Apache-2.0", "LICENSE/COPYING files (src dir)", ())]
    assert found["g"][0][:2] == ("1.0.0", "")
    assert found["g"][0][2].startswith("unreadable ") and "FileNotFoundError" in found["g"][0][2]


def test_git_checkouts_skip_workspace_roots(home: Path) -> None:
    git = home / ".cargo/git/checkouts"
    make_dir(
        git / "trie-abc/a056b4c", {"Cargo.toml": toml("sequence_trie", "0.3.6", 'license = "MIT/Apache-2.0"')}
    )
    make_dir(git / "ws-def/1234567", {"Cargo.toml": '[workspace]\nmembers = ["x"]\n'})
    make_dir(git / "broken-0aa/89abcde", {"Cargo.toml": "[package\n"})
    found = versions(home)
    assert found["sequence_trie"] == [
        ("0.3.6", "MIT/Apache-2.0", "Cargo.toml license (git checkout trie-abc/a056b4c)", ())
    ]
    assert "TOMLDecodeError" in found["89abcde"][0][2]
    assert set(found) == {"sequence_trie", "89abcde"}


def test_cargo_lock_users(home: Path) -> None:
    make_dir(home / "src/proj/app", {"Cargo.lock": '[[package]]\nname = "h"\nversion = "1.0.0"\n'})
    make_dir(home / "src/bad", {"Cargo.lock": "[[package]\n"})
    make_crate(home, "h-1.0.0", [("Cargo.toml", toml("h", "1.0.0"))])
    assert cargo.lock_users() == {"h": {"~/src/proj"}}
    [item] = cargo.scan_cargo_cache()
    assert (item.source, item.verdict, item.requiredBy) == ("cargo-cache", "foss", ["~/src/proj"])


def test_empty_cargo_home(home: Path) -> None:
    assert cargo.scan_cargo_cache() == []


def test_unlicensed_git_checkout_asks_its_upstream(home: Path, upstream: dict[str, tuple[str, str]]) -> None:
    git = home / ".cargo/git/checkouts"
    sha = "92e94f8aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    make_dir(git / "from-db-aaa/1111111", {"Cargo.toml": toml("from_db", "1.0.0", "")})
    make_dir(git / "from-lock-bbb/92e94f8", {"Cargo.toml": toml("from_lock", "1.0.0", "")})
    make_dir(
        git / "declared-ccc/3333333",
        {"Cargo.toml": toml("declared", "1.0.0", 'homepage = "https://h.example/d"')},
    )
    make_dir(git / "nowhere-ddd/4444444", {"Cargo.toml": toml("nowhere", "1.0.0", "")})
    make_dir(git / "licensed-eee/5555555", {"Cargo.toml": toml("licensed", "1.0.0")})
    make_dir(
        home / ".cargo/git/db/from-db-aaa",
        {"config": '[remote "origin"]\n\turl = https://git.example/from_db.git\n'},
    )
    make_dir(home / ".cargo/git/db/declared-ccc", {"config": "[core]\n\tbare = true\n"})
    lock = f'[[package]]\nname = "from_lock"\nsource = "git+https://codeberg.org/o/from_lock?rev=x#{sha}"\n'
    make_dir(
        home / "src/app", {"Cargo.lock": lock + '[[package]]\nname = "x"\nsource = "registry+https://r"\n'}
    )
    upstream["https://git.example/from_db.git"] = (
        "MPL-2.0",
        "upstream https://git.example/from_db HEAD: LICENSE file",
    )
    upstream["https://codeberg.org/o/from_lock"] = (
        "",
        "upstream https://codeberg.org/o/from_lock HEAD: no license file",
    )
    upstream["https://h.example/d"] = ("Apache-2.0", "upstream https://h.example/d HEAD: LICENSE file")
    found = versions(home)
    assert found["from_db"][0][1:3] == ("MPL-2.0", "upstream https://git.example/from_db HEAD: LICENSE file")
    assert found["from_lock"][0][1] == ""
    assert found["from_lock"][0][2].endswith(
        "crate root; upstream https://codeberg.org/o/from_lock HEAD: no license file"
    )
    assert found["declared"][0][1] == "Apache-2.0"
    assert found["nowhere"][0][2].endswith(
        "LICENSE*/COPYING* files in the crate root"
    )  # no URL: nothing to ask
    assert found["licensed"][0][1:3] == ("MIT", "Cargo.toml license (git checkout licensed-eee/5555555)")
