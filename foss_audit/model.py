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
    "unowned",
    "app-home",
    "toolchain",
    "desktop",
    "docker",
    "user-app",
    "maven-cache",
    "pub-cache",
    "npm-cache",
    "cargo-cache",
    "pip-cache",
]
Verdict = Literal["foss", "foss-partial", "nonfree"]
# Verdicts that get a curated FOSS alternative attached (not the "free" headline).
NEEDS_ALTERNATIVE: frozenset[str] = frozenset({"nonfree", "foss-partial"})
# No license grant at all is "all rights reserved", even for public code.
NO_LICENSE = "no license (all rights reserved)"


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
    own: bool = False
    # A ~/.local/bin file no package, pip dist, symlink or repo accounts for.
    loose: bool = False
    # A .desktop launcher whose Exec target no longer exists.
    dangling: bool = False
    requiredBy: list[str] = field(default_factory=list)
    alternative: Alternative | None = None
    removeCommand: str | None = None
    # Scanner-found detail (EULA link, bundled free parts) that a curated
    # reason must not wipe out; serialised as the tail of `reason`.
    note: str = ""

    @property
    def id(self) -> str:
        """Stable unique key: source plus name."""
        return f"{self.source}:{self.name}"

    def to_json(self) -> dict[str, Any]:
        """Serialise with the computed id first and the note folded into reason."""
        data = asdict(self)
        note = data.pop("note")
        if note:
            data["reason"] = f"{self.reason}; {note}" if self.reason else note
        return {"id": self.id, **data}


@dataclass
class ScanError:
    """A scanner that failed; the rest of the scan still succeeds."""

    source: str
    message: str
