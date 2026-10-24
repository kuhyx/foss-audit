"""cargo-cache remove commands: cargo remove in the declaring crate, else its parents, else rm."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from foss_audit import cache_remove
from foss_audit import scan_cache_cargo as cargo
from foss_audit.model import Item

INDEX = "index.crates.io-1949cf8c6b5b557f"
REG = f"~/.cargo/registry/cache/{INDEX}"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(cargo, "CARGO", tmp_path / ".cargo")
    monkeypatch.setattr(cargo, "SRC", tmp_path / "src")
    monkeypatch.setattr(cache_remove, "HOME", tmp_path)
    return tmp_path


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def crate(home: Path, name: str, version: str, deps: str = "") -> None:
    """A cached .crate whose Cargo.toml names `deps` (a [dependencies] body)."""
    stem = f"{name}-{version}"
    path = home / ".cargo/registry/cache" / INDEX / f"{stem}.crate"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (
        f'[package]\nname = "{name}"\nversion = "{version}"\nlicense = "MIT"\n[dependencies]\n{deps}'.encode()
    )
    with tarfile.open(path, "w:gz") as tf:
        info = tarfile.TarInfo(f"{stem}/Cargo.toml")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))


def lock(*packages: tuple[str, str | None, list[str]]) -> str:
    """A Cargo.lock: (name, source or None for a workspace member, dependencies)."""
    out = "version = 4\n"
    for name, source, deps in packages:
        out += f'\n[[package]]\nname = "{name}"\nversion = "1.0.0"\n'
        out += f'source = "{source}"\n' if source else ""
        out += "dependencies = [" + ", ".join(f'"{d}"' for d in deps) + "]\n"
    return out


REGISTRY = "registry+https://github.com/rust-lang/crates.io-index"


@pytest.fixture
def items(home: Path) -> dict[str, Item]:
    src = home / "src"
    write(
        src / "app/Cargo.toml",
        '[package]\nname = "app"\nversion = "0.1.0"\n[dependencies]\na = "1"\n'
        'ren = { package = "renamed", version = "1" }\nlocal = { path = "../local" }\n'
        '[dev-dependencies]\nd = "1"\n[target.\'cfg(unix)\'.build-dependencies]\nu = "1"\n',
    )
    write(
        src / "app/Cargo.lock",
        lock(
            ("app", None, ["a", "d", "renamed", "u", "local"]),
            ("a", REGISTRY, ["b 1.0.0"]),
            ("b", REGISTRY, ["c"]),
            ("c", REGISTRY, []),
            ("d", REGISTRY, []),
            ("renamed", REGISTRY, []),
            ("u", REGISTRY, []),
            ("local", None, ["c"]),
            ("unreached", REGISTRY, []),
        ),
    )
    write(src / "app/target/package/x/Cargo.toml", '[package]\nname = "x"\n[dependencies]\nzz = "1"\n')
    write(src / "local/Cargo.toml", '[package]\nname = "local"\nversion = "0.1.0"\n[dependencies]\nc = "1"\n')
    write(src / "ws/Cargo.toml", '[workspace]\nmembers = ["crates/m"]\n')
    write(src / "ws/crates/m/Cargo.toml", '[package]\nname = "m"\n[dev-dependencies]\na = "1"\n')
    write(src / "ws/Cargo.lock", lock(("m", None, ["a"]), ("a", REGISTRY, [])))
    write(src / "bad/Cargo.toml", "[package\n")
    crate(home, "a", "1.0.0", 'b = "1"\n')
    crate(home, "a", "1.1.0")
    # c's cached manifest names e, which no Cargo.lock lists: ~/src/local (no
    # lock) still reaches it; ~/src/app's lock says its c needs nothing.
    crate(home, "c", "1.0.0", 'e = "1"\n')
    for name in ("b", "d", "e", "renamed", "u", "unreached", "stale"):
        crate(home, name, "1.0.0")
    extracted = home / ".cargo/registry/src" / INDEX / "stale-1.0.0"
    write(extracted / "Cargo.toml", '[package]\nname = "stale"\nversion = "1.0.0"\nlicense = "MIT"\n')
    git = home / ".cargo/git/checkouts/gitdep-0123/abcdef0"
    write(git / "Cargo.toml", '[package]\nname = "gitdep"\nversion = "0.1.0"\nlicense = "MIT"\n')
    write(home / ".cargo/git/checkouts/ws-root/1111111/Cargo.toml", "[workspace]\n")
    return {i.name: i for i in cargo.scan_cargo_cache()}


def test_direct_dependency_in_every_declaring_crate(items: dict[str, Item]) -> None:
    a = items["a"]
    assert a.removeCommand == (
        "(cd ~/src/app && cargo remove a); (cd ~/src/ws/crates/m && cargo remove --dev a); "
        f"rm -rf {REG}/a-1.0.0.crate {REG}/a-1.1.0.crate"
    )
    assert a.removeVia == "~/src/app declares a; ~/src/ws/crates/m declares a"


def test_renamed_and_target_specific_dependencies_use_the_manifest_key(items: dict[str, Item]) -> None:
    assert (
        items["renamed"].removeCommand
        == f"(cd ~/src/app && cargo remove ren); rm -rf {REG}/renamed-1.0.0.crate"
    )
    assert items["u"].removeCommand == (
        f"(cd ~/src/app && cargo remove --build --target 'cfg(unix)' u); rm -rf {REG}/u-1.0.0.crate"
    )


def test_transitive_chain_removes_the_direct_parent(items: dict[str, Item]) -> None:
    b = items["b"]
    assert b.removeCommand == f"(cd ~/src/app && cargo remove a); rm -rf {REG}/b-1.0.0.crate"
    assert b.removeVia == "~/src/app via a → b"


def test_unlisted_but_reachable_is_transitive_not_stale(items: dict[str, Item]) -> None:
    e = items["e"]
    assert e.requiredBy == []
    assert e.removeCommand == f"(cd ~/src/local && cargo remove c); rm -rf {REG}/e-1.0.0.crate"
    assert e.removeVia == "~/src/local via c → e"


def test_several_projects_chain_then_delete_once(items: dict[str, Item]) -> None:
    c = items["c"]
    assert c.removeCommand == (
        f"(cd ~/src/app && cargo remove a); (cd ~/src/local && cargo remove c); rm -rf {REG}/c-1.0.0.crate"
    )
    assert c.removeVia == "~/src/app via a → b → c; ~/src/local declares c"


def test_lock_entry_nothing_reaches_is_relocked(items: dict[str, Item]) -> None:
    assert items["unreached"].removeCommand == (
        f"(cd ~/src/app && cargo update --workspace); rm -rf {REG}/unreached-1.0.0.crate"
    )


def test_stale_deletes_exact_cache_paths(items: dict[str, Item]) -> None:
    stale = items["stale"]
    assert stale.removeCommand == f"rm -rf {REG}/stale-1.0.0.crate ~/.cargo/registry/src/{INDEX}/stale-1.0.0"
    assert stale.removeVia.startswith("stale: no ~/src project reaches it")
    assert items["gitdep"].removeCommand == "rm -rf ~/.cargo/git/checkouts/gitdep-0123/abcdef0"


def test_every_item_has_a_command(items: dict[str, Item]) -> None:
    assert all(i.removeCommand for i in items.values())
