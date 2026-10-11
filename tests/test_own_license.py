"""License discovery for checkouts, manifests and loose ~/.local/bin copies."""

from __future__ import annotations

from pathlib import Path

from conftest import make_repo

from foss_audit import own_license
from foss_audit.scan_pacman import parse_expac


def test_identify_known_texts_and_fallback() -> None:
    assert own_license.identify("GNU LESSER GENERAL PUBLIC LICENSE\nGNU GENERAL PUBLIC LICENSE") == "LGPL"
    assert (
        own_license.identify("\n  Copyright me, do what you like\nmore") == "Copyright me, do what you like"
    )
    assert own_license.identify("   ") == ""
    # The file's own license comes first; bundled parts it names later lose.
    bsd = "Redistribution and use in source and binary forms...\nWine is under the Mozilla Public License"
    assert own_license.identify(bsd) == "BSD"
    ofl = "Licensed under the SIL Open Font License.\nPermission is hereby granted, free of charge"
    assert own_license.identify(ofl) == "OFL-1.1"


def test_manifest_licenses_nearest_wins(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "src/r", license_text=None)
    (repo / "pyproject.toml").write_text('[project]\nlicense = {text = "BSD-3-Clause"}\n')
    pkg = repo / "web"
    pkg.mkdir()
    (pkg / "package.json").write_text('{"license": "ISC"}')
    empty = repo / "empty"
    empty.mkdir()
    (empty / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    assert own_license.declared_license(pkg, repo) == "ISC"
    assert own_license.declared_license(repo, repo) == "BSD-3-Clause"
    assert own_license.declared_license(empty, repo) == "BSD-3-Clause"
    bare = make_repo(tmp_path / "src/bare", license_text=None)
    assert own_license.license_for_path(bare / "run.sh") == ("", True)
    outside = tmp_path / "loose"
    outside.mkdir()
    assert own_license.license_for_path(outside / "f") == ("", False)


def test_worktree_and_submodule_git_files(tmp_path: Path) -> None:
    main = make_repo(tmp_path / "main")
    (main / ".git/worktrees/wt").mkdir(parents=True)
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {main / '.git/worktrees/wt'}\n")
    assert own_license.is_kuhy_repo(wt)
    (main / ".git/modules/sub").mkdir(parents=True)
    (main / ".git/modules/sub/config").write_text("url = https://github.com/other/sub\n")
    sub = main / "sub"
    sub.mkdir()
    (sub / ".git").write_text("gitdir: ../.git/modules/sub\n")
    assert not own_license.is_kuhy_repo(sub)


def test_checkout_for_url_and_origin(tmp_path: Path) -> None:
    make_repo(tmp_path / "src/todo", remote="https://github.com/kuhyx/todo-app.git")
    make_repo(tmp_path / "src/foreign", remote="https://github.com/other/todo-app.git")
    make_repo(tmp_path / ".claude", remote="https://github.com/kuhyx/claude-config.git")
    assert own_license.checkout_for_url("https://github.com/kuhyx/todo-app") == tmp_path / "src/todo"
    assert own_license.checkout_for_url("https://github.com/kuhyx/missing") is None
    assert own_license.checkout_for_url("https://example.com/x") is None
    assert tmp_path / ".claude" in own_license.kuhy_repos()
    assert own_license.origin_of(tmp_path / "nothing-tracks-this") is None


def test_own_aur_package_reads_checkout_license(tmp_path: Path) -> None:
    make_repo(tmp_path / "src/todo", remote="https://github.com/kuhyx/todo-app.git")
    make_repo(tmp_path / "src/nolic", remote="https://github.com/kuhyx/nolic", license_text=None)
    lines = [
        "todo-flutter\t1-1\tcustom\thttps://github.com/kuhyx/todo-app\t",
        "nolic\t1-1\tcustom\thttps://github.com/kuhyx/nolic\t",
        "mine\t1-1\tMIT\thttps://github.com/kuhyx/mine\t",
    ]
    by = {i.name: i for i in parse_expac(lines, set(), set(), set())}
    assert by["todo-flutter"].verdict == "foss"
    assert by["todo-flutter"].reason == f"MIT (LICENSE in {tmp_path / 'src/todo'})"
    assert (by["nolic"].verdict, by["nolic"].reason) == ("nonfree", "unrecognised license: custom")
    assert (by["mine"].verdict, by["mine"].own) == ("foss", True)


def test_walk_outside_home_stops_at_root() -> None:
    assert own_license.declared_license(Path("/nonexistent-foss-audit/a"), Path("/elsewhere")) == ""


def test_script_key_matches_install_names() -> None:
    assert own_license.script_key("keepass_consolidate.sh") == own_license.script_key("keepass-consolidate")
    assert own_license.script_key("Tool.PY") == "tool"


def test_local_only_repo_under_repo_root_is_kuhys(tmp_path: Path) -> None:
    local = make_repo(tmp_path / "src/mine", remote=None)
    assert own_license.is_kuhy_repo(local)
    assert own_license.license_for_path(local / "run.sh") == ("MIT", True)
    assert local in own_license.kuhy_repos()
    # No remote but outside the repo roots (or nested below a checkout): not kuhy's.
    assert not own_license.is_kuhy_repo(make_repo(tmp_path / "elsewhere/x", remote=None))
    assert not own_license.is_kuhy_repo(make_repo(tmp_path / "src/mine/vendor", remote=None))
    # Someone else's remote under ~/src stays not-own.
    assert not own_license.is_kuhy_repo(
        make_repo(tmp_path / "src/clone", remote="https://github.com/o/x.git")
    )


def test_checkout_without_git_config_is_not_kuhys(tmp_path: Path) -> None:
    (tmp_path / "src/odd/.git").mkdir(parents=True)
    assert not own_license.is_kuhy_repo(tmp_path / "src/odd")
