"""cache_remove: the shared planner that turns project usage into a permanent remove command."""

from __future__ import annotations

from pathlib import Path

import pytest

from foss_audit import cache_remove
from foss_audit.cache_common import CachedArtifact, CachedVersion
from foss_audit.cache_remove import Manifest, Planner, joined, nearest, rm, shell_path
from foss_audit.model import Item


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(cache_remove, "HOME", tmp_path)
    return tmp_path


def tool(kind: str, names: list[str]) -> str:
    return " ".join(["tool", "remove", *([kind] if kind else []), *names])


def test_shell_path_keeps_tilde_expandable_and_quotes_the_rest(home: Path) -> None:
    assert shell_path(home / "src/a b/c") == "~/'src/a b/c'"
    assert shell_path(home / "src/x") == "~/src/x"
    assert shell_path(home) == "~"
    assert shell_path(Path("/opt/it's")) == "'/opt/it'\"'\"'s'"


def test_rm_and_joined(home: Path) -> None:
    assert rm([home / "b", home / "a", home / "a"]) == "rm -rf ~/a ~/b"
    assert rm([]) == ""
    assert joined(["a", "", "b", "a"]) == "a; b"


def test_nearest_stops_at_the_repo(tmp_path: Path) -> None:
    repo = tmp_path / "src/r"
    (repo / "sub/deep").mkdir(parents=True)
    (repo / "x.lock").write_text("")
    (tmp_path / "src/y.lock").write_text("")
    assert nearest(repo / "sub/deep", ["x.lock"], repo) == repo / "x.lock"
    assert nearest(repo / "sub/deep", ["y.lock"], repo) is None
    assert nearest(tmp_path / "elsewhere", ["x.lock"], repo) is None


def test_projects_skip_worktrees_build_output_and_vendored_copies(tmp_path: Path) -> None:
    for rel in ("app", "app/.claude/worktrees/w", "app/build/x", "app/node_modules/y", "app/.venv"):
        (tmp_path / rel).mkdir(parents=True, exist_ok=True)
        (tmp_path / rel / "Cargo.toml").write_text("")
    assert cache_remove.projects(["Cargo.toml"], tmp_path) == [tmp_path / "app/Cargo.toml"]
    # A workspace member deeper than the global search, found below its lockfile.
    deep = tmp_path / "a/b/ws/crates/x/Cargo.toml"
    deep.parent.mkdir(parents=True)
    deep.write_text("")
    (tmp_path / "a/b/ws/Cargo.lock").write_text("")
    assert deep not in cache_remove.projects(["Cargo.toml"], tmp_path)
    assert deep in cache_remove.projects(["Cargo.toml"], tmp_path, lock="Cargo.lock")


def test_cache_graph_unions_every_version() -> None:
    art = CachedArtifact("a", [CachedVersion("1", "", "", ("b",)), CachedVersion("2", "", "", ("c",))])
    assert cache_remove.cache_graph([art]) == {"a": {"b", "c"}}


def manifest(home: Path, rel: str, **direct: str) -> Manifest:
    m = Manifest(home / rel, tool)
    for name, kind in direct.items():
        m.declare(name, kind)
    m.declare(next(iter(direct)), next(iter(direct.values())))  # a repeat is recorded once
    return m


def test_direct_transitive_and_several_projects(home: Path) -> None:
    app = manifest(home, "src/app", torch="", pytest="--dev")
    app.edges = {"torch": {"cudnn"}}
    other = manifest(home, "src/other", cudnn="")
    planner = Planner([other, app], {"pytest": {"pluggy"}})
    command, via = planner.plan("cudnn", "rm -rf ~/c")
    assert command == "(cd ~/src/app && tool remove torch); (cd ~/src/other && tool remove cudnn); rm -rf ~/c"
    assert via == "~/src/app via torch → cudnn; ~/src/other declares cudnn"
    # Reached only through the cache's own dependency data, in a dev group.
    assert planner.plan("pluggy", "x") == (
        "(cd ~/src/app && tool remove --dev pytest); x",
        "~/src/app via pytest → pluggy",
    )


def test_the_lockfile_beats_the_cache_for_what_it_lists(home: Path) -> None:
    app = manifest(home, "src/app", torch="")
    app.edges = {"torch": set()}
    planner = Planner([app], {"torch": {"old-dep"}, "new": {"x"}})
    assert planner.plan("old-dep", "c")[1].startswith("stale:")


def test_every_parent_and_the_direct_declaration_are_removed(home: Path) -> None:
    app = manifest(home, "src/app", torch="", chatter="", cudnn="")
    # A diamond (and a cycle back to the root) keeps the shortest chain.
    planner = Planner([app], {"chatter": {"torch", "hub"}, "hub": {"cudnn"}, "torch": {"cudnn", "chatter"}})
    command, via = planner.plan("cudnn", "c", "note")
    assert command == "(cd ~/src/app && tool remove cudnn chatter torch); c"
    assert via == (
        "~/src/app declares cudnn; ~/src/app via chatter → hub → cudnn; ~/src/app via torch → cudnn; note"
    )


def test_local_packages_are_never_blamed(home: Path) -> None:
    app = manifest(home, "src/app", member="")
    member = manifest(home, "src/app/member", leaf="")
    app.local = frozenset({"member"})
    # Local only where it is linked: another repo's registry copy of "member" still counts.
    other = manifest(home, "src/other", member="")
    planner = Planner([app, member, other], {"member": {"leaf"}})
    assert planner.plan("leaf", "c")[1] == "~/src/app/member declares leaf; ~/src/other via member → leaf"


def test_stale_deletes_only_the_cache(home: Path) -> None:
    planner = Planner([manifest(home, "src/app", a="")], {})
    assert planner.plan("gone", "rm -rf ~/gone", "also x") == (
        "rm -rf ~/gone",
        "stale: no ~/src project reaches it, so only its cache entries are deleted; also x",
    )


def test_listed_but_unreached_blames_sdk_roots_else_relocks_once(home: Path) -> None:
    flutter = manifest(home, "src/f", flutter="", http="")
    flutter.locked, flutter.fallback = frozenset({"meta"}), ("flutter",)
    flutter.relock = (home / "src/f", "pub get")
    assert Planner([flutter], {}).plan("meta", "c") == (
        "(cd ~/src/f && tool remove flutter); c",
        "~/src/f via flutter (SDK, its pubspec is not in the cache) → meta",
    )
    root = manifest(home, "src/ws", a="")
    member = manifest(home, "src/ws/m", b="")
    for m in (root, member):
        m.locked, m.relock = frozenset({"old", "b"}), (home / "src/ws", "relock")
    planner = Planner([root, member], {})
    assert planner.plan("old", "c") == (
        "(cd ~/src/ws && relock); c",
        "~/src/ws lockfile lists old but nothing it declares reaches it",
    )
    # A member reaching it is enough: no re-lock for the root.
    assert planner.plan("b", "c") == ("(cd ~/src/ws/m && tool remove b); c", "~/src/ws/m declares b")
    # The workspace's own package is listed by its lock but never re-locked away.
    root.local = frozenset({"old"})
    assert Planner([root, member], {}).plan("old", "c")[0] == "c"


def test_apply_fills_every_item(home: Path) -> None:
    item = Item("a", "cargo-cache", "foss")
    cache_remove.apply([item], Planner([], {}), lambda name: (f"rm -rf ~/{name}", ""))
    assert (item.removeCommand, item.removeVia) == (
        "rm -rf ~/a",
        cache_remove.Planner([], {}).plan("a", "")[1],
    )
