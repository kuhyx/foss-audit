"""npm-cache remove commands: pnpm remove / npm uninstall where declared, else parents, else exact entries."""

# ruff: noqa: F811  (the autouse no_network fixture is imported)
from __future__ import annotations

from pathlib import Path

import pytest

from foss_audit import cache_remove, scan_cache_npm, scan_cache_npm_cacache, scan_cache_npm_pnpm
from foss_audit.cache_remove_npm import pnpm_lock
from foss_audit.model import Item
from tests.npm_helpers import REG, cache_entry, json_files, no_network, pkg_json, tgz, write_json  # noqa: F401
from tests.npm_remove_fixtures import PACKAGE_LOCK, PNPM_LOCK, V1_LOCK, Q, bucket, tarball
from tests.test_scan_cache_npm_store import make_db, mp


@pytest.fixture
def items(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Item]:
    src, store, cache = tmp_path / "src", tmp_path / ".local/share/pnpm/store", tmp_path / ".npm/_cacache"
    monkeypatch.setattr(scan_cache_npm, "SRC", src)
    monkeypatch.setattr(scan_cache_npm_pnpm, "STORE", store)
    monkeypatch.setattr(scan_cache_npm_cacache, "CACACHE", cache)
    monkeypatch.setattr(cache_remove, "HOME", tmp_path)
    (src / "web/packages/ui").mkdir(parents=True)
    (src / "web/pnpm-lock.yaml").write_text(PNPM_LOCK)
    write_json(src / "old/package-lock.json", PACKAGE_LOCK)
    write_json(src / "v1/package-lock.json", V1_LOCK)
    write_json(src / "v1/package.json", {"dependencies": {"left-pad": "1"}})
    write_json(src / "broken/package-lock.json", ["not", "a", "lock"])
    v10 = store / "v10"
    for name in ("react", "scheduler", "vitest", "@vitest/runner"):
        files = json_files(v10, {"package.json": pkg_json(name=name, version="1.0.0", license="MIT")})
        write_json(
            v10 / f"index/aa/h-{name.replace('/', '+')}@1.0.0.json",
            {"name": name, "version": "1.0.0", "files": files},
        )
    # p-limit is no snapshot key, so its cached package.json says what it pulls in.
    files = json_files(
        v10,
        {
            "package.json": pkg_json(
                name="p-limit", version="5.0.0", license="MIT", dependencies={"yocto-queue": "1"}
            )
        },
    )
    write_json(v10 / "files/bb/hash-index.json", {"name": "p-limit", "version": "5.0.0", "files": files})
    files = json_files(v10, {"package.json": pkg_json(name="yocto-queue", version="1.0.0", license="MIT")})
    write_json(
        v10 / "https+++codeload.github.com+x+tar.gz+1/integrity.json",
        {"name": "yocto-queue", "version": "1.0.0", "files": files},
    )
    v11 = store / "v11"
    lodash = json_files(v11, {"package.json": pkg_json(name="lodash", version="4.17.21", license="MIT")})
    gitdep = json_files(v11, {"package.json": pkg_json(name="gitdep", version="0.1.0", license="MIT")})
    exe = json_files(
        v11, {"package.json": pkg_json(name="@pnpm/exe.linux-x64", version="12.15.0", license="MIT")}
    )
    make_db(
        v11,
        [
            ("sha512-l\tlodash@4.17.21", mp({"files": lodash})),
            ("sha512-e\t@pnpm/exe.linux-x64@12.15.0", mp({"files": exe})),
            (
                "https://codeload.github.com/k/gitdep/tar.gz/abc\tbuilt",
                mp({"manifest": {"name": "gitdep"}, "files": gitdep}),
            ),
            (
                "https://codeload.github.com/k/gitdep/tar.gz/abc\tnot-built",
                mp({"manifest": {"name": "gitdep"}, "files": gitdep}),
            ),
        ],
    )
    (v11 / "links/@pnpm/exe.linux-x64/12.15.0/hash").mkdir(parents=True)
    for name, deps in (
        ("express", {"body-parser": "1"}),
        ("body-parser", {"debug": "2"}),
        ("debug", {}),
        ("jest", {}),
        ("chalk", {}),
        ("leftover", {}),
        ("unreached", {}),
    ):
        cache_entry(cache, f"{REG}{name}/-/{name}-1.0.0.tgz", tarball(name, deps))
    cache_entry(cache, "pacote:tarball:leftover@1.0.0", tarball("leftover"))
    cache_entry(
        cache, "make-fetch-happen:request-cache:https://codeload.github.com/k/g/tar.gz/abc", tarball("gitpkg")
    )
    return {i.name: i for i in scan_cache_npm.scan_npm_cache()}


def test_pnpm_lock_reads_importers_and_snapshots() -> None:
    importers, graph, local = pnpm_lock(PNPM_LOCK)
    assert importers == {
        ".": {"pnpm": "pm", "react": "pnpm", "@scope/ui": "pnpm", "vitest": "pnpm"},
        "packages/ui": {"lodash": "pnpm"},
    }
    assert graph["vitest"] == {"@vitest/runner"}
    assert graph["pnpm"] == {"@pnpm/exe.linux-x64"}
    assert local == {"@scope/ui"}


def test_pnpm_direct_in_its_workspace_member(items: dict[str, Item]) -> None:
    lodash = items["lodash"]
    assert lodash.removeCommand == (
        "(cd ~/src/web/packages/ui && pnpm remove lodash); sqlite3 ~/.local/share/pnpm/store/v11/index.db "
        f"'DELETE FROM package_index WHERE key IN ({Q}sha512-l{Q} || char(9) || {Q}lodash@4.17.21{Q})'"
    )
    assert lodash.removeVia == "~/src/web/packages/ui declares lodash"


def test_package_manager_dependency(items: dict[str, Item]) -> None:
    exe = items["@pnpm/exe.linux-x64"]
    assert exe.removeCommand.startswith("(cd ~/src/web && npm pkg delete packageManager); sqlite3 ")
    assert exe.removeCommand.endswith("; rm -rf ~/.local/share/pnpm/store/v11/links/@pnpm/exe.linux-x64")
    assert exe.removeVia == "~/src/web via pnpm → @pnpm/exe.linux-x64"


def test_transitive_chain_and_unlisted_but_reachable(items: dict[str, Item]) -> None:
    assert items["scheduler"].removeCommand == (
        "(cd ~/src/web && pnpm remove react); "
        "rm -rf ~/.local/share/pnpm/store/v10/index/aa/h-scheduler@1.0.0.json"
    )
    yocto = items["yocto-queue"]
    assert yocto.requiredBy == []
    assert yocto.removeCommand == (
        "(cd ~/src/web && pnpm remove vitest); "
        "rm -rf ~/.local/share/pnpm/store/v10/https+++codeload.github.com+x+tar.gz+1"
    )
    assert yocto.removeVia == "~/src/web via vitest → @vitest/runner → p-limit → yocto-queue"
    assert items["p-limit"].removeCommand == (
        "(cd ~/src/web && pnpm remove vitest); rm -rf ~/.local/share/pnpm/store/v10/files/bb/hash-index.json"
    )


def test_npm_lock_several_projects_and_workspace(items: dict[str, Item]) -> None:
    debug = items["debug"]
    key = f"{REG}debug/-/debug-1.0.0.tgz"
    assert debug.removeCommand == (
        "(cd ~/src/old && npm uninstall express); (cd ~/src/v1 && npm uninstall left-pad); "
        f"npm cache clean --cache ~/.npm {key}"
    )
    assert debug.removeVia == "~/src/old via express → body-parser → debug; ~/src/v1 via left-pad → debug"
    assert items["chalk"].removeCommand.startswith("(cd ~/src/old && npm uninstall -w packages/w chalk); ")
    assert items["jest"].removeCommand.startswith("(cd ~/src/old && npm uninstall jest); ")


def test_relock_and_stale(items: dict[str, Item]) -> None:
    assert items["unreached"].removeCommand.startswith(
        "(cd ~/src/web && pnpm install --lockfile-only); npm cache clean "
    )
    leftover = items["leftover"]
    first = f"{REG}leftover/-/leftover-1.0.0.tgz"
    # Both keys share one tarball: clean drops it once, the other key's index bucket goes by rm.
    assert (
        leftover.removeCommand
        == f"npm cache clean --cache ~/.npm {first}; rm -rf {bucket('pacote:tarball:leftover@1.0.0')}"
    )
    assert leftover.removeVia.startswith("stale: ")
    gitpkg = "make-fetch-happen:request-cache:https://codeload.github.com/k/g/tar.gz/abc"
    assert items["gitpkg"].removeCommand == f"npm cache clean --cache ~/.npm {gitpkg}"
    assert items["gitdep"].removeCommand == (
        "sqlite3 ~/.local/share/pnpm/store/v11/index.db 'DELETE FROM package_index WHERE key IN ("
        f"{Q}https://codeload.github.com/k/gitdep/tar.gz/abc{Q} || char(9) || {Q}built{Q}, "
        f"{Q}https://codeload.github.com/k/gitdep/tar.gz/abc{Q} || char(9) || {Q}not-built{Q})'"
    )
    assert all(i.removeCommand for i in items.values())
