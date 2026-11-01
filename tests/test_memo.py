"""The persistent per-artifact memo: hits, invalidation, pruning, damage."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from foss_audit import memo


@pytest.fixture
def memo_file(tmp_path: Path) -> Path:
    return tmp_path / "memo" / "src.json"


def filled(path: Path, entries: dict[str, object], version: int = memo.MEMO_VERSION) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": version, "entries": entries}))


def test_a_saved_entry_is_a_hit_in_the_next_run(memo_file: Path) -> None:
    first = memo.Memo(memo_file)
    assert first.get("a") is None
    first.put("a", {"license": "MIT"})
    first.save()
    assert memo.Memo(memo_file).get("a") == {"license": "MIT"}


def test_a_memo_version_bump_discards_everything(memo_file: Path) -> None:
    filled(memo_file, {"a": 1}, version=memo.MEMO_VERSION - 1)
    assert memo.Memo(memo_file).get("a") is None


@pytest.mark.parametrize("text", ["{not json", "[]", '{"version": 1, "entries": []}', ""])
def test_a_corrupt_memo_is_empty(memo_file: Path, text: str) -> None:
    memo_file.parent.mkdir(parents=True)
    memo_file.write_text(text)
    loaded = memo.Memo(memo_file)
    assert loaded.get("a") is None
    loaded.put("a", 1)
    loaded.save()
    assert memo.Memo(memo_file).get("a") == 1


def test_a_missing_directory_is_empty(tmp_path: Path) -> None:
    assert memo.Memo(tmp_path / "nope" / "x.json").get("a") is None


def test_entries_not_touched_this_run_are_dropped_on_save(memo_file: Path) -> None:
    filled(memo_file, {"kept": 1, "gone": 2})
    run = memo.Memo(memo_file)
    assert run.get("kept") == 1
    run.put("new", 3)
    run.save()
    assert json.loads(memo_file.read_text())["entries"] == {"kept": 1, "new": 3}


def test_a_run_that_changes_nothing_does_not_rewrite_the_file(memo_file: Path) -> None:
    filled(memo_file, {"a": 1})
    before = memo_file.stat().st_mtime_ns
    run = memo.Memo(memo_file)
    assert run.get("a") == 1
    run.save()
    assert memo_file.stat().st_mtime_ns == before
    assert [p.name for p in memo_file.parent.iterdir()] == ["src.json"]


def test_a_vanished_entry_alone_triggers_a_rewrite(memo_file: Path) -> None:
    filled(memo_file, {"a": 1, "b": 2})
    run = memo.Memo(memo_file)
    assert run.get("a") == 1
    run.save()
    assert json.loads(memo_file.read_text())["entries"] == {"a": 1}


def test_a_bypassing_memo_never_hits_and_replaces_the_file(memo_file: Path) -> None:
    filled(memo_file, {"a": "old", "b": "stale"})
    run = memo.Memo(memo_file, bypass=True)
    assert run.get("a") is None
    run.put("a", "fresh")
    run.save()
    assert json.loads(memo_file.read_text())["entries"] == {"a": "fresh"}


def test_a_bypassing_memo_with_nothing_to_store_still_discards(memo_file: Path) -> None:
    filled(memo_file, {"a": 1})
    memo.Memo(memo_file, bypass=True).save()
    assert json.loads(memo_file.read_text())["entries"] == {}


def test_a_memo_without_a_file_stores_nothing(tmp_path: Path) -> None:
    off = memo.Memo(None)
    off.put("a", 1)
    assert off.get("a") is None
    off.save()
    assert list(tmp_path.iterdir()) == []


def test_an_unwritable_memo_dir_is_not_an_error(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("")
    run = memo.Memo(blocker / "sub" / "x.json")
    run.put("a", 1)
    run.save()


def test_for_source_follows_the_env_dir_and_the_bypass_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(memo.ENV_DIR, str(tmp_path / "m"))
    run = memo.Memo.for_source("npm-cache")
    run.put("a", 1)
    run.save()
    assert (tmp_path / "m/npm-cache.json").is_file()
    assert memo.Memo.for_source("npm-cache").get("a") == 1
    memo.set_bypass(True)
    try:
        assert memo.Memo.for_source("npm-cache").get("a") is None
    finally:
        memo.set_bypass(False)


def test_the_default_dir_is_under_the_cache_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(memo.ENV_DIR)
    assert memo.memo_dir() == Path.home() / ".cache/foss-audit/memo"


def test_stat_key_changes_with_size_and_mtime(tmp_path: Path) -> None:
    file = tmp_path / "f"
    file.write_text("a")
    first = memo.stat_key(file)
    os.utime(file, ns=(1, 1))
    second = memo.stat_key(file)
    file.write_text("abc")
    os.utime(file, ns=(1, 1))
    assert len({first, second, memo.stat_key(file)}) == 3
    assert memo.stat_key(tmp_path / "missing") == f"{tmp_path / 'missing'}|gone"


@pytest.mark.parametrize(
    ("license_id", "license_from", "ok"),
    [
        ("MIT", "package.json (pnpm store v10)", True),
        ("", "package.json", False),
        ("MIT", "upstream https://x HEAD: LICENSE file", False),
        ("Custom", "license URL http://x; fetch failed: boom", False),
    ],
)
def test_only_local_readings_are_reusable(license_id: str, license_from: str, ok: bool) -> None:
    assert memo.reusable(license_id, license_from) is ok


def garble(path: Path) -> None:
    """Keep the file valid but make every stored entry the wrong shape."""
    doc = json.loads(path.read_text())
    doc["entries"] = dict.fromkeys(doc["entries"], 42)
    path.write_text(json.dumps(doc))


def test_recall_decodes_a_stored_entry(memo_file: Path) -> None:
    filled(memo_file, {"a": [1, 2]})
    assert memo.Memo(memo_file).recall("a", tuple) == (True, (1, 2))
    assert memo.Memo(memo_file).recall("missing", tuple) == (False, None)


def test_recall_treats_a_malformed_entry_as_a_miss_and_heals_the_file(memo_file: Path) -> None:
    filled(memo_file, {"bad": 42, "good": [1]})
    run = memo.Memo(memo_file)
    assert run.recall("bad", tuple) == (False, None)
    assert run.recall("good", tuple) == (True, (1,))
    run.put("bad", [2])
    run.save()
    assert json.loads(memo_file.read_text())["entries"] == {"bad": [2], "good": [1]}


def test_a_malformed_entry_that_is_not_recomputed_is_pruned(memo_file: Path) -> None:
    filled(memo_file, {"bad": 42})
    run = memo.Memo(memo_file)
    assert run.recall("bad", tuple)[0] is False
    run.save()
    assert json.loads(memo_file.read_text())["entries"] == {}


def test_require_text_rejects_non_strings() -> None:
    memo.require_text("a", "")
    with pytest.raises(TypeError):
        memo.require_text("a", 1)
