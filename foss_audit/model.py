"""Data model shared by every scanner; mirrors DOCS-api-contract.md."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Source = Literal[
    "pacman",
    "aur",
    "pip-user",
    "pipx",
    "uv-tool",
    "npm-global",
    "cargo",
    "flatpak",
    "appimage",
    "opt",
    "local-bin",
    "conda",
    "steam",
    "wine",
    "waydroid",
]
Verdict = Literal["foss", "foss-partial", "nonfree", "blob", "own", "unknown"]
# Verdicts that get a curated FOSS alternative attached (not the "free" headline).
NEEDS_ALTERNATIVE: frozenset[str] = frozenset({"nonfree", "foss-partial", "blob", "unknown"})


@dataclass
class Alternative:
    """A curated FOSS replacement for a non-free item."""

    names: list[str]
    fit: str
    effort: str | None
    effortReason: str
    lockIn: str
    installed: list[str] = field(default_factory=list)


@dataclass
class Item:
    """One installed program/package found by a scanner."""

    name: str
    source: Source
    verdict: Verdict
    version: str | None = None
    license: str = ""
    reason: str = ""
    url: str | None = None
    explicit: bool = True
    orphan: bool = False
    requiredBy: list[str] = field(default_factory=list)
    alternative: Alternative | None = None
    removeCommand: str | None = None

    @property
    def id(self) -> str:
        """Stable unique key: source plus name."""
        return f"{self.source}:{self.name}"

    def to_json(self) -> dict[str, Any]:
        """Serialise with the computed id first."""
        return {"id": self.id, **asdict(self)}


@dataclass
class ScanError:
    """A scanner that failed; the rest of the scan still succeeds."""

    source: str
    message: str
