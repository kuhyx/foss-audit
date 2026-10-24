"""Toolchain families (rustup, pyenv, nvm, fvm, Go) and global dotnet/dart/gem tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from foss_audit import scan_toolchain, scan_toolchain_tools
from foss_audit.scan_toolchain_tools import natural_key

MIT_TEXT = "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
BSD_TEXT = "Redistribution and use in source and binary forms, with or without modification\n"
JUNK_TEXT = "Do whatever you like, no strings\n"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(scan_toolchain, "HOME", tmp_path)
    return tmp_path


def write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def by_name(items: list) -> dict:  # type: ignore[type-arg]
    return {i.name: i for i in items}


def test_nothing_installed_means_nothing(home: Path) -> None:
    assert scan_toolchain.scan_toolchains() == []


def test_natural_sort() -> None:
    assert sorted(["3.10.1", "3.9.2"], key=natural_key) == ["3.9.2", "3.10.1"]
    assert sorted(["v22.13", "v22.2"], key=natural_key) == ["v22.2", "v22.13"]


def test_rustup_one_item_all_versions(home: Path) -> None:
    root = home / ".rustup/toolchains"
    write(root / "1.77.2-x86_64-unknown-linux-gnu/share/doc/rust/LICENSE-MIT", MIT_TEXT)
    write(root / "1.9.0-x86_64-unknown-linux-gnu/bin/rustc")
    (root / "stable-aarch64-apple-darwin").mkdir()
    (root / "stray-file").write_text("not a toolchain")
    [item] = scan_toolchain.scan_rust()
    assert item.name == "rust (rustup)"
    assert item.source == "toolchain"
    assert item.version == "1.9.0, 1.77.2, stable"
    assert item.license == "MIT OR Apache-2.0"
    assert item.verdict == "foss"
    toolchains = "1.9.0-x86_64-unknown-linux-gnu 1.77.2-x86_64-unknown-linux-gnu stable-aarch64-apple-darwin"
    assert item.removeCommand == f"rustup toolchain uninstall {toolchains}"


def test_rust_license_file_can_downgrade(home: Path) -> None:
    write(home / ".rustup/toolchains/1.0-x86_64-linux/share/doc/rust/licenses/MIT.txt", JUNK_TEXT)
    [item] = scan_toolchain.scan_rust()
    assert item.verdict == "nonfree"
    assert "unrecognised license" in item.reason


def test_pyenv_skips_virtualenvs(home: Path) -> None:
    root = home / ".pyenv/versions"
    write(root / "3.12.8/bin/python")
    write(root / "3.12.8/lib/python3.12/LICENSE.txt", "PSF license, Python Software Foundation\n")
    write(root / "3.9.1/bin/python3.9")
    write(root / "venv-a/bin/python")
    write(root / "venv-a/pyvenv.cfg", "home = /usr/bin\n")
    write(root / "empty/share/x")
    real = root / "pypy"
    write(real / "bin/python")
    (root / "linked").symlink_to(real)
    # "pypy" is a real dir, so it counts; only the symlink is dropped
    [item] = scan_toolchain.scan_pyenv()
    assert item.name == "python (pyenv)"
    assert item.version == "3.9.1, 3.12.8, pypy"
    assert item.license == "PSF-2.0"
    assert item.verdict == "foss"


def test_pyenv_only_venvs_gives_nothing(home: Path) -> None:
    write(home / ".pyenv/versions/core/bin/python")
    write(home / ".pyenv/versions/core/pyvenv.cfg")
    assert scan_toolchain.scan_pyenv() == []


def test_nvm_and_fvm(home: Path) -> None:
    write(home / ".nvm/versions/node/v22.13.1/LICENSE", MIT_TEXT)
    write(home / ".nvm/versions/node/v22.2.0/bin/node")
    write(home / "sdk/fvm/versions/3.47.7/LICENSE", BSD_TEXT)
    items = by_name(scan_toolchain.scan_nvm() + scan_toolchain.scan_fvm())
    assert items["node (nvm)"].version == "v22.2.0, v22.13.1"
    assert items["node (nvm)"].license == "MIT"
    assert items["flutter (fvm)"].version == "3.47.7"
    assert items["flutter (fvm)"].license == "BSD-3-Clause"
    assert {i.verdict for i in items.values()} == {"foss"}


def test_go_needs_the_go_binary(home: Path) -> None:
    write(home / "sdk/go/bin/age")
    assert scan_toolchain.scan_go() == []


def test_go_sdk_version_from_marker(home: Path) -> None:
    write(home / "sdk/go/bin/go")
    write(home / "sdk/go/VERSION", "go1.25.1\ntime 2026-01-01T00:00:00Z\n")
    write(home / "sdk/go/LICENSE", BSD_TEXT)
    [item] = scan_toolchain.scan_go()
    assert (item.name, item.version, item.license, item.verdict) == ("go", "1.25.1", "BSD-3-Clause", "foss")


def test_go_sdk_without_marker(home: Path) -> None:
    write(home / "sdk/go/bin/go")
    [item] = scan_toolchain.scan_go()
    assert item.version is None
    assert item.verdict == "foss"


def test_dotnet_tools(home: Path) -> None:
    tools = home / ".dotnet/tools"
    store = tools / ".store"
    for name in ("withfile", "withspec", "bare", "orphan"):
        write(tools / name)
    write(store / "withfile/1.0/LICENSE", MIT_TEXT)
    write(store / "withfile/1.0/withfile/1.0/x.nuspec", "<license type='expression'>GPL</license>")
    write(
        store / "withspec/2.0/withspec/2.0/withspec.nuspec", '<license type="expression">Apache-2.0</license>'
    )
    write(store / "bare/3.0/bare/3.0/bare.nuspec", "<package/>")
    write(store / "bare/3.0/bare/3.0/LICENSE.md", MIT_TEXT)
    write(store / "bare/10.0/bare/10.0/bare.nuspec", "<package/>")
    (tools / "dir-not-a-shim").mkdir()
    items = by_name(scan_toolchain_tools.scan_dotnet_tools(home))
    assert (items["withfile"].license, items["withfile"].verdict) == ("MIT", "foss")
    assert items["withfile"].removeCommand == "dotnet tool uninstall -g withfile"
    assert (items["withspec"].license, items["withspec"].version) == ("Apache-2.0", "2.0")
    # newest version (10.0) ships no license, 3.0 is not consulted
    assert items["bare"].version == "10.0"
    assert items["bare"].verdict == "nonfree"
    assert items["orphan"].version is None
    assert items["orphan"].verdict == "nonfree"
    assert "dir-not-a-shim" not in items


def test_dotnet_absent(home: Path) -> None:
    assert scan_toolchain_tools.scan_dotnet_tools(home) == []


def pub_stub(pkg: str, version: str | None, exe: str) -> str:
    version_line = f"# Version: {version}\n" if version else ""
    return f"#!/usr/bin/env sh\n# Package: {pkg}\n{version_line}# Executable: {exe}\n"


def test_pub_global(home: Path) -> None:
    cache = home / ".pub-cache"
    write(cache / "bin/cov", pub_stub("coverage", "1.15.1", "cov"))
    write(cache / "bin/cov2", pub_stub("coverage", "1.15.1", "cov2"))
    write(cache / "bin/gitpkg", pub_stub("gitpkg", "0.1.0", "gitpkg"))
    write(cache / "bin/nover", pub_stub("nover", None, "nover"))
    write(cache / "bin/plain", "#!/bin/sh\n")
    (cache / "bin/subdir").mkdir()
    write(cache / "hosted/pub.dev/coverage-1.15.1/LICENSE", BSD_TEXT)
    items = by_name(scan_toolchain_tools.scan_pub_global(home))
    assert set(items) == {"coverage", "gitpkg", "nover", "plain"}
    assert (items["coverage"].license, items["coverage"].verdict) == ("BSD", "foss")
    assert items["coverage"].removeCommand == "dart pub global deactivate coverage"
    assert items["gitpkg"].verdict == "nonfree"
    assert items["nover"].version is None
    assert items["plain"].version is None


def test_pub_absent(home: Path) -> None:
    assert scan_toolchain_tools.scan_pub_global(home) == []


def gemspec(licenses: str) -> str:
    return f"Gem::Specification.new do |s|\n  s.licenses = [{licenses}]\nend\n"


def test_gems(home: Path) -> None:
    ruby = home / ".local/share/gem/ruby/3.4.0"
    stub = "load Gem.activate_bin_path('{}', '{}', version)\n"
    write(ruby / "bin/ruby-lsp", stub.format("ruby-lsp", "ruby-lsp"))
    write(ruby / "bin/ruby-lsp-check", stub.format("ruby-lsp", "ruby-lsp-check"))
    write(ruby / "bin/rbs", stub.format("rbs", "rbs"))
    write(ruby / "bin/oddball", "#!/bin/sh\n")
    write(ruby / "specifications/ruby-lsp-0.26.1.gemspec", gemspec('"MIT".freeze'))
    write(ruby / "specifications/ruby-lsp-0.26.10.gemspec", gemspec('"MIT".freeze'))
    write(ruby / "specifications/rbs-3.9.5.gemspec", gemspec('"BSD-2-Clause".freeze, "Ruby".freeze'))
    (ruby / "bin/subdir").mkdir()
    legacy = home / ".gem/ruby/3.3.0"
    write(legacy / "bin/old", stub.format("old", "old"))
    write(legacy / "specifications/old-1.0.gemspec", "Gem::Specification.new do |s|\nend\n")
    items = by_name(scan_toolchain_tools.scan_gems(home))
    assert set(items) == {"ruby-lsp", "rbs", "oddball", "old"}
    assert items["ruby-lsp"].version == "0.26.1, 0.26.10"
    assert items["ruby-lsp"].license == "MIT"
    assert items["rbs"].license == "BSD-2-Clause OR Ruby"
    assert items["rbs"].verdict == "foss"
    assert items["rbs"].removeCommand == "gem uninstall rbs"
    assert items["oddball"].verdict == "nonfree"
    assert items["oddball"].version is None
    assert items["old"].verdict == "nonfree"
    assert "~/.gem" in items["old"].reason
    assert "~/.local/share/gem" in items["rbs"].reason


def test_gems_absent(home: Path) -> None:
    assert scan_toolchain_tools.scan_gems(home) == []


def test_scan_toolchains_combines_everything(home: Path) -> None:
    write(home / ".nvm/versions/node/v24.0.0/LICENSE", MIT_TEXT)
    write(home / "sdk/go/bin/go")
    write(home / ".dotnet/tools/tool")
    write(home / ".pub-cache/bin/p", pub_stub("p", "1", "p"))
    write(home / ".gem/ruby/3.4.0/bin/g", "load Gem.activate_bin_path('g', 'g', v)\n")
    assert [i.name for i in scan_toolchain.scan_toolchains()] == [
        "node (nvm)",
        "go",
        "tool",
        "p",
        "g",
    ]
