"""Apply data/curated.json: hand-verified verdicts, FOSS alternatives and rankings."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from foss_audit.model import NEEDS_ALTERNATIVE, Alternative, Item

CURATED_PATH = Path(__file__).resolve().parent.parent / "data" / "curated.json"
# Scan values that mean "nobody has filled this column in".
BLANK_VERSIONS = frozenset({"", "unknown"})
BLANK_URLS = frozenset({"", "unknown"})
BLANK_LICENSES = frozenset({"", "none found"})


@dataclass
class Ranking:
    """`ranking` in curated.json: ids ordered heaviest first, plus a reason per id."""

    fit: list[str] = field(default_factory=list)
    effort: list[str] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)


@dataclass
class Curated:
    """Parsed curated.json; keys are fnmatch globs, first match wins."""

    verdicts: dict[str, list[Any]]
    alternatives: dict[str, dict[str, Any]]
    ranking: Ranking = field(default_factory=Ranking)

    @classmethod
    def load(cls, path: Path = CURATED_PATH) -> Curated:
        """Read and parse the curated file."""
        data = json.loads(path.read_text())
        ranking = data.get("ranking", {})
        return cls(
            verdicts=data["verdicts"],
            alternatives=data["alternatives"],
            ranking=Ranking(
                fit=list(ranking.get("fit", [])),
                effort=list(ranking.get("effort", [])),
                reasons=dict(ranking.get("reasons", {})),
            ),
        )

    def verdict_for(self, name: str) -> list[Any] | None:
        """[verdict, reason, license append?, {"homepage", "license", "version"}?] of the first glob match."""
        return next((v for k, v in self.verdicts.items() if fnmatchcase(name, k)), None)

    def alternative_entry(self, item: Item) -> tuple[bool, dict[str, Any] | None]:
        """(matched, entry): whether a curated entry speaks for the item, and its alternative.

        A `null` entry means "curated: no alternative applies": it matches, has no
        alternative, and stops the search, so a broader glob further down cannot
        attach one.
        """
        for key, alt in self.alternatives.items():
            if not fnmatchcase(item.name, key):
                continue
            if alt is None:
                return True, None
            if alt.get("onlySource", item.source) == item.source:
                return True, alt
        return False, None

    def alternative_for(self, item: Item) -> dict[str, Any] | None:
        """The first alternative whose glob matches and whose onlySource fits."""
        return self.alternative_entry(item)[1]


def installed_names(items: list[Item]) -> set[str]:
    """Every name present on the machine, for 'alternative already installed'."""
    return {i.name.lower() for i in items}


def to_replace(item: Item) -> bool:
    """Non-free or partly-FOSS code that is not kuhy's own: the items that get ranked."""
    return item.verdict in NEEDS_ALTERNATIVE and not item.own


def positions(order: list[str], present: set[str]) -> dict[str, int]:
    """1-based place of each id of `order` that is in `present`; repeats count once."""
    kept = [i for i in dict.fromkeys(order) if i in present]
    return {item_id: place for place, item_id in enumerate(kept, 1)}


def fill_gaps(item: Item, extra: dict[str, str]) -> None:
    """Curated `homepage` / `license` / `version` of a verdict entry: fills a gap, never overrides a scan."""
    if "version" in extra and (item.version or "").strip().lower() in BLANK_VERSIONS:
        item.version = extra["version"]
    if "homepage" in extra and (item.url or "").strip().lower() in BLANK_URLS:
        item.url = extra["homepage"]
    if "license" in extra and item.license.strip().lower() in BLANK_LICENSES:
        item.license = extra["license"]


def has_blank_column(item: Item, has_entry: bool) -> bool:
    """True when version, licence, homepage or the curated alternative is not filled in."""
    return (
        (item.version or "").strip().lower() in BLANK_VERSIONS
        or not item.license.strip()
        or (item.url or "").strip().lower() in BLANK_URLS
        or not has_entry
    )


def apply(items: list[Item], curated: Curated) -> list[Item]:
    """Override verdicts, attach alternatives, then rank the to-replace items (in place)."""
    present = installed_names(items)
    entries: dict[str, bool] = {}
    for item in items:
        hit = curated.verdict_for(item.name)
        # Never let a curated glob override kuhy's own code: its verdict comes
        # from his LICENSE files.
        if hit and not item.own:
            item.verdict, item.reason = hit[0], hit[1]
            # An optional third string names a license the files do not
            # state; it is added to what the scanner found, never replaces it.
            if len(hit) > 2 and isinstance(hit[2], str):
                item.license = f"{item.license} {hit[2]}".strip()
            if isinstance(hit[-1], dict):
                fill_gaps(item, hit[-1])
        if item.own or item.verdict not in NEEDS_ALTERNATIVE:
            continue
        entries[item.id], alt = curated.alternative_entry(item)
        if alt is None:
            continue
        item.alternative = Alternative(
            names=list(alt["names"]),
            fit=alt["fit"],
            effort=alt["effort"],
            effortReason=alt["effortReason"],
            lockIn=alt["lockIn"],
            installed=[c for c in alt["candidates"] if c.lower() in present],
        )
    rank_items(items, curated.ranking, entries)
    return items


def rank_items(items: list[Item], ranking: Ranking, entries: dict[str, bool]) -> None:
    """Number the to-replace items by their place in the ranking lists and flag gaps.

    Ids the scan does not contain are skipped, so the numbers stay 1..N.
    """
    replace = {i.id: i for i in items if to_replace(i)}
    fit = positions(ranking.fit, set(replace))
    effort = positions(ranking.effort, set(replace))
    for item_id, item in replace.items():
        item.fitRank = fit.get(item_id)
        item.effortRank = effort.get(item_id)
        item.rankReason = ranking.reasons.get(item_id)
        item.unranked = (
            item.fitRank is None or item.effortRank is None or has_blank_column(item, entries[item_id])
        )
