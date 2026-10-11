"""Apply data/curated.json: hand-verified verdicts and FOSS alternatives."""

from __future__ import annotations

import json
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from foss_audit.model import NEEDS_ALTERNATIVE, Alternative, Item

CURATED_PATH = Path(__file__).resolve().parent.parent / "data" / "curated.json"


@dataclass
class Curated:
    """Parsed curated.json; keys are fnmatch globs, first match wins."""

    verdicts: dict[str, list[str]]
    alternatives: dict[str, dict[str, Any]]

    @classmethod
    def load(cls, path: Path = CURATED_PATH) -> Curated:
        """Read and parse the curated file."""
        data = json.loads(path.read_text())
        return cls(verdicts=data["verdicts"], alternatives=data["alternatives"])

    def verdict_for(self, name: str) -> list[str] | None:
        """[verdict, reason] for the first matching glob, else None."""
        return next((v for k, v in self.verdicts.items() if fnmatchcase(name, k)), None)

    def alternative_for(self, item: Item) -> dict[str, Any] | None:
        """The first alternative whose glob matches and whose onlySource fits.

        A `null` entry means "curated: no alternative applies" and stops the
        search, so a broader glob further down cannot attach one.
        """
        for key, alt in self.alternatives.items():
            if not fnmatchcase(item.name, key):
                continue
            if alt is None:
                return None
            if alt.get("onlySource", item.source) == item.source:
                return alt
        return None


def installed_names(items: list[Item]) -> set[str]:
    """Every name present on the machine, for 'alternative already installed'."""
    return {i.name.lower() for i in items}


def apply(items: list[Item], curated: Curated) -> list[Item]:
    """Override verdicts, then attach alternatives to every non-free item (in place)."""
    present = installed_names(items)
    for item in items:
        hit = curated.verdict_for(item.name)
        # Never let a curated glob downgrade kuhy's own code.
        if hit and item.verdict != "own":
            item.verdict, item.reason = hit[0], hit[1]  # type: ignore[assignment]
        if item.verdict not in NEEDS_ALTERNATIVE:
            continue
        alt = curated.alternative_for(item)
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
    return items
