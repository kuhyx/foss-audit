"""pub-cache remove commands: `dart|flutter pub remove` where declared, else the parents, else rm."""

from __future__ import annotations

from pathlib import Path

import pytest

from foss_audit import cache_remove, scan_cache_pub, upstream_license
from foss_audit.model import Item
from foss_audit.scan_cache_pub_parse import declared_deps

MIT = "MIT License\n\nPermission is hereby granted, free of charge, to any person...\n"
HOSTED = "~/.pub-cache/hosted/pub.dev"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def pkg(root: Path, name: str, version: str, deps: str = "") -> None:
    write(root / "pubspec.yaml", f"name: {name}\nversion: {version}\ndependencies:\n{deps}")
    write(root / "LICENSE", MIT)


def lock(*names: str, flutter: bool = False) -> str:
    body = "".join(f"  {n}:\n    dependency: transitive\n    version: '1.0.0'\n" for n in names)
    sdks = 'sdks:\n  dart: ">=3.0.0"\n' + ('  flutter: ">=3.0.0"\n' if flutter else "")
    return f"packages:\n{body}{sdks}"


APP = """name: app
dependencies:
  flutter:
    sdk: flutter
  http: ^1.0.0
  local_pkg:
    path: ../local_pkg
  inline: {sdk: flutter}
dev_dependencies:
  flutter_test:
    sdk: flutter
  lints: ^3.0.0
"""


@pytest.fixture
def items(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Item]:
    cache, src = tmp_path / ".pub-cache", tmp_path / "src"
    monkeypatch.setattr(scan_cache_pub, "PUB_CACHE", cache)
    monkeypatch.setattr(scan_cache_pub, "SRC", src)
    monkeypatch.setattr(cache_remove, "HOME", tmp_path)
    monkeypatch.setattr(upstream_license, "upstream_license", {}.__getitem__)
    write(src / "app/pubspec.yaml", APP)
    listed = ("http", "http_parser", "meta", "lints", "unreached", "path")
    write(src / "app/pubspec.lock", lock(*listed, flutter=True))
    write(src / "app/build/x/pubspec.yaml", "name: x\ndependencies:\n  gone: any\n")
    write(src / "local_pkg/pubspec.yaml", "name: local_pkg\ndependencies:\n  path: any\n")
    write(src / "cli/pubspec.yaml", "name: cli\ndependencies:\n  http: any\n")
    write(src / "cli/pubspec.lock", lock("http", "http_parser", "dartonly"))
    write(src / "ws/pubspec.yaml", "name: ws\nworkspace:\n  - pkgs/m\n")
    write(src / "ws/pubspec.lock", lock("collection"))
    write(
        src / "ws/pkgs/m/pubspec.yaml", "name: m\nresolution: workspace\ndependencies:\n  collection: any\n"
    )
    hosted = cache / "hosted/pub.dev"
    pkg(hosted / "http-1.0.0", "http", "1.0.0", "  http_parser: ^4.0.0\n")
    # Listed by no pubspec.lock; http_parser's cached pubspec still pulls it in.
    pkg(hosted / "http_parser-4.0.0", "http_parser", "4.0.0", "  typed_data: any\n")
    for name in ("typed_data", "meta", "lints", "collection", "unreached", "dartonly", "path"):
        pkg(hosted / f"{name}-1.0.0", name, "1.0.0")
    pkg(hosted / "gone-1.0.0", "gone", "1.0.0")
    pkg(hosted / "gone-2.0.0", "gone", "2.0.0")
    write(cache / "hosted-hashes/pub.dev/gone-1.0.0.sha256", "x")
    pkg(cache / "git/mono-abc123/a", "a", "0.1.0")
    pkg(cache / "git/mono-abc123/b", "b", "0.1.0")
    pkg(cache / "git/solo-def456", "solo", "0.2.0")
    return {i.name: i for i in scan_cache_pub.scan_pub_cache()}


def test_declared_deps_by_source() -> None:
    assert declared_deps(APP) == [
        ("flutter", "sdk"),
        ("http", "hosted"),
        ("local_pkg", "path"),
        ("inline", "sdk"),
        ("flutter_test", "sdk"),
        ("lints", "hosted"),
    ]
    assert declared_deps("name: x\n") == []


def test_direct_dev_dependency_of_a_flutter_app(items: dict[str, Item]) -> None:
    lints = items["lints"]
    assert lints.removeCommand == f"(cd ~/src/app && flutter pub remove lints); rm -rf {HOSTED}/lints-1.0.0"
    assert lints.removeVia == "~/src/app declares lints"


def test_workspace_member_runs_in_its_own_directory(items: dict[str, Item]) -> None:
    assert items["collection"].removeCommand == (
        f"(cd ~/src/ws/pkgs/m && dart pub remove collection); rm -rf {HOSTED}/collection-1.0.0"
    )


def test_transitive_in_several_projects(items: dict[str, Item]) -> None:
    parser = items["http_parser"]
    assert parser.removeCommand == (
        "(cd ~/src/app && flutter pub remove http); (cd ~/src/cli && dart pub remove http); "
        f"rm -rf {HOSTED}/http_parser-4.0.0"
    )
    assert parser.removeVia == "~/src/app via http → http_parser; ~/src/cli via http → http_parser"


def test_unlisted_but_reachable_is_transitive(items: dict[str, Item]) -> None:
    typed = items["typed_data"]
    assert typed.requiredBy == []
    assert (
        typed.removeVia
        == "~/src/app via http → http_parser → typed_data; ~/src/cli via http → http_parser → typed_data"
    )


def test_sdk_pinned_package_only_loses_its_cache_entry(items: dict[str, Item]) -> None:
    meta = items["meta"]
    assert meta.removeCommand == f"rm -rf {HOSTED}/meta-1.0.0"
    assert meta.removeVia == "pinned by the Flutter SDK; only removable with the app (~/src/app)"
    assert not any("pub remove flutter" in str(i.removeCommand) for i in items.values())


def test_locked_through_a_path_dependency_is_not_blamed_on_the_sdk(items: dict[str, Item]) -> None:
    path = items["path"]
    assert path.removeCommand == f"(cd ~/src/local_pkg && dart pub remove path); rm -rf {HOSTED}/path-1.0.0"
    assert (
        path.removeVia
        == "~/src/app lockfile lists path through its local local_pkg; ~/src/local_pkg declares path"
    )


def test_unreached_lock_entry_is_relocked(items: dict[str, Item]) -> None:
    assert (
        items["dartonly"].removeCommand == f"(cd ~/src/cli && dart pub get); rm -rf {HOSTED}/dartonly-1.0.0"
    )


def test_stale_hosted_versions_and_hashes(items: dict[str, Item]) -> None:
    gone = items["gone"]
    assert gone.removeCommand == (
        f"rm -rf {HOSTED}/gone-1.0.0 {HOSTED}/gone-2.0.0 ~/.pub-cache/hosted-hashes/pub.dev/gone-1.0.0.sha256"
    )
    assert gone.removeVia.startswith("stale: ")


def test_git_checkout_names_what_else_it_holds(items: dict[str, Item]) -> None:
    a = items["a"]
    assert a.removeCommand == "rm -rf ~/.pub-cache/git/mono-abc123"
    assert a.removeVia.endswith("; the git checkout mono-abc123 also holds b")
    assert items["solo"].removeCommand == "rm -rf ~/.pub-cache/git/solo-def456"
    assert all(i.removeCommand for i in items.values())
