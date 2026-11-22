"""Python port of the grouping in src/lib/selection-prompt.ts (groupItems).

The e2e must not hardcode a group that the host's caches may stop having, so
it picks one from the scan it is given, selects its members, and then expects
the heading the UI builds for them.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

Item = dict[str, Any]
Group = tuple[str, list[str]]  # (label, member ids)


def _alternative_key(item: Item) -> str | None:
    names = (item.get("alternative") or {}).get("names") or []
    return ", ".join(names) if names else None


def _namespace_of(item: Item) -> str | None:
    """Maven `group:artifact` -> group; npm `@scope/name` -> `@scope`; else none."""
    name = item["name"]
    if ":" in name:
        return name.split(":", 1)[0]
    return name.split("/", 1)[0] if name.startswith("@") and "/" in name else None


def _shared(counts: Counter[str], value: str | None) -> bool:
    return value is not None and counts[value] > 1


def prompt_groups(items: Iterable[Item]) -> dict[str, Group]:
    """The groups the prompt forms: {key: (label, ids)}, `item:` singletons included.

    Only non-FOSS items are grouped; a shared alternative wins over a shared
    namespace; a key only one item has is no group.
    """
    candidates = [item for item in items if item["verdict"] != "foss"]
    alt_counts = Counter(k for k in map(_alternative_key, candidates) if k is not None)
    rest = [item for item in candidates if not _shared(alt_counts, _alternative_key(item))]
    ns_counts = Counter(k for k in map(_namespace_of, rest) if k is not None)
    groups: dict[str, Group] = {}
    for item in candidates:
        alt, ns = _alternative_key(item), _namespace_of(item)
        if _shared(alt_counts, alt):
            key, label = f"alt:{alt}", f"shared alternative {alt}"
        elif _shared(ns_counts, ns):
            key, label = f"ns:{ns}", f"namespace {ns}"
        else:
            key, label = f"item:{item['id']}", item["name"]
        groups.setdefault(key, (label, []))[1].append(item["id"])
    return groups


def pick_group(items: Iterable[Item]) -> tuple[str, Group]:
    """The first multi-item group by sorted key; fails closed when the scan has none."""
    multi = {key: group for key, group in prompt_groups(items).items() if len(group[1]) > 1}
    if not multi:
        raise AssertionError(
            "the scan has no multi-item prompt group: need 2+ non-FOSS items sharing an"
            " alternative, or a Maven group:artifact / npm @scope/name prefix, to check a group heading"
        )
    key = min(multi)
    return key, multi[key]
