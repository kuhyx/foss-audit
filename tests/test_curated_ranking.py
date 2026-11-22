"""Strict fit/effort ranks and the `unranked` flag from data/curated.json `ranking`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from foss_audit.curated import CURATED_PATH, Curated, Ranking, apply
from foss_audit.model import Item

ALT: dict[str, Any] = {
    "names": ["X"],
    "candidates": ["x"],
    "fit": "good",
    "effort": "S",
    "effortReason": "",
    "lockIn": "",
}


def curated(fit: list[str], effort: list[str], reasons: dict[str, str] | None = None) -> Curated:
    return Curated(
        verdicts={},
        alternatives={"a*": ALT, "b*": ALT, "c*": ALT, "none*": None, "ownx": ALT, "d*": ALT},
        ranking=Ranking(fit=fit, effort=effort, reasons=reasons or {}),
    )


def item(name: str, verdict: str = "nonfree", **kw: Any) -> Item:
    kw.setdefault("version", "1.0")
    kw.setdefault("license", "custom")
    kw.setdefault("url", "https://example.org")
    return Item(name=name, source="pacman", verdict=verdict, **kw)  # type: ignore[arg-type]


def test_ranks_are_dense_among_present_nonfree_items() -> None:
    items = [item("a1"), item("b1", "foss-partial"), item("c1"), item("fossy", "foss")]
    ranking = curated(
        fit=["pacman:gone", "pacman:c1", "pacman:fossy", "pacman:a1", "pacman:c1", "pacman:b1"],
        effort=["pacman:b1", "pacman:a1", "pacman:c1"],
        reasons={"pacman:a1": "why a", "pacman:fossy": "ignored"},
    )
    apply(items, ranking)
    assert [(i.fitRank, i.effortRank) for i in items[:3]] == [(2, 2), (3, 1), (1, 3)]
    assert [i.rankReason for i in items[:3]] == ["why a", None, None]
    assert [i.unranked for i in items] == [False, False, False, False]
    foss = items[3]
    assert (foss.fitRank, foss.effortRank, foss.rankReason, foss.unranked) == (None, None, None, False)


def test_unranked_when_a_rank_is_missing() -> None:
    items = [item("a1"), item("b1"), item("c1")]
    apply(items, curated(fit=["pacman:a1", "pacman:b1"], effort=["pacman:a1", "pacman:c1"]))
    assert [(i.fitRank, i.effortRank, i.unranked) for i in items] == [
        (1, 1, False),
        (2, None, True),
        (None, 2, True),
    ]


def test_unranked_when_a_column_is_blank() -> None:
    blanks = [
        item("a1", version=None),
        item("a2", version="unknown"),
        item("a3", license=""),
        item("a4", url=None),
        item("a5", url="unknown"),
        item("zz"),  # no curated alternative entry matched
    ]
    ids = [i.id for i in blanks]
    apply(blanks, curated(fit=ids, effort=ids))
    assert all(i.unranked for i in blanks)
    assert [i.fitRank for i in blanks] == [1, 2, 3, 4, 5, 6]


def test_explicit_null_alternative_counts_as_filled() -> None:
    researched = item("none1")
    apply([researched], curated(fit=["pacman:none1"], effort=["pacman:none1"]))
    assert researched.alternative is None
    assert (researched.fitRank, researched.unranked) == (1, False)


def test_only_source_mismatch_is_not_a_match() -> None:
    alts = {"a*": ALT | {"onlySource": "steam"}}
    c = Curated(verdicts={}, alternatives=alts, ranking=Ranking(["pacman:a1"], ["pacman:a1"], {}))
    thing = item("a1")
    apply([thing], c)
    assert thing.unranked is True


def test_own_code_is_never_to_replace() -> None:
    mine = item("ownx", own=True)
    apply([mine], curated(fit=["pacman:ownx"], effort=["pacman:ownx"]))
    assert (mine.fitRank, mine.effortRank, mine.unranked) == (None, None, False)


def test_to_json_carries_the_four_fields() -> None:
    data = item("a1").to_json()
    assert (data["fitRank"], data["effortRank"], data["rankReason"], data["unranked"]) == (
        None,
        None,
        None,
        False,
    )


FILL = {"homepage": "https://cur.example", "license": "Curated terms"}


def test_curated_homepage_and_license_fill_only_gaps() -> None:
    c = Curated(
        verdicts={
            "empty": ["nonfree", "r", FILL],
            "set": ["nonfree", "r", "L", FILL],
            "unk": ["nonfree", "r", FILL],
            "none": ["nonfree", "r", FILL],
            "only-home": ["nonfree", "r", {"homepage": "https://cur.example"}],
        },
        alternatives={},
        ranking=Ranking([], [], {}),
    )
    empty = item("empty", url=None, license="")
    unknown = item("unk", url="unknown", license="none found")
    scanned = item("set", url="https://scanned.example", license="MIT")
    appended = item("none", url="", license="")
    only_home = item("only-home", url=None, license="")
    apply([empty, scanned, unknown, appended, only_home], c)
    assert (empty.url, empty.license) == ("https://cur.example", "Curated terms")
    assert (unknown.url, unknown.license) == ("https://cur.example", "Curated terms")
    assert (scanned.url, scanned.license) == ("https://scanned.example", "MIT L")
    assert (only_home.url, only_home.license) == ("https://cur.example", "")


def test_third_element_license_still_counts_before_the_fill() -> None:
    c = Curated(verdicts={"x": ["nonfree", "r", "Extra", FILL]}, alternatives={}, ranking=Ranking([], [], {}))
    thing = item("x", license="", url=None)
    apply([thing], c)
    assert thing.license == "Extra"
    assert thing.url == "https://cur.example"


def test_load_defaults_and_real_file(tmp_path: Path) -> None:
    custom = tmp_path / "c.json"
    custom.write_text(json.dumps({"verdicts": {}, "alternatives": {}}))
    assert Curated.load(custom).ranking == Ranking([], [], {})
    ranking = {"fit": ["a"], "effort": ["b"], "reasons": {"a": "r"}}
    custom.write_text(json.dumps({"verdicts": {}, "alternatives": {}, "ranking": ranking}))
    assert Curated.load(custom).ranking == Ranking(["a"], ["b"], {"a": "r"})
    real = json.loads(CURATED_PATH.read_text())
    assert list(real)[-1] == "ranking"
    assert set(real["ranking"]) == {"fit", "effort", "reasons"}
    assert Curated.load().ranking.fit == real["ranking"]["fit"]
