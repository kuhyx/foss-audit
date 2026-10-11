"""Scan pacman's local database (native repo packages and AUR/foreign ones)."""

from __future__ import annotations

import subprocess

from foss_audit.licenses import classify_spdx, classify_text
from foss_audit.model import Item, Verdict
from foss_audit.own_license import checkout_for_url, declared_license

# expac prints one line per package; fields are tab-separated and the
# multi-valued ones (%L licenses, %N required-by) are joined with the -l delimiter.
EXPAC_FORMAT = "%n\t%v\t%L\t%u\t%N"
LIST_DELIM = "|"


def _lines(cmd: list[str]) -> list[str]:
    """Run a command and return its non-empty stdout lines (empty on exit 1)."""
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    # pacman -Qdtq exits 1 when there are no orphans; that is not an error.
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"{cmd[0]} failed: {proc.stderr.strip()[:200]}")
    return [ln for ln in proc.stdout.splitlines() if ln]


def own_repo_verdict(url: str, verdict: Verdict, reason: str) -> tuple[Verdict, str]:
    """Re-classify one of kuhy's packages from its local checkout's LICENSE."""
    repo = checkout_for_url(url)
    lic = declared_license(repo, repo) if repo else ""
    if not lic:
        return verdict, reason
    new_verdict, new_reason = classify_text(lic)
    return new_verdict, new_reason or f"{lic} (LICENSE in {repo})"


def parse_expac(lines: list[str], explicit: set[str], foreign: set[str], orphans: set[str]) -> list[Item]:
    """Build Items from expac output lines."""
    items: list[Item] = []
    for line in lines:
        name, version, lic, url, required = (line.split("\t") + [""] * 5)[:5]
        license_expr = lic.replace(LIST_DELIM, " ")
        verdict, reason = classify_spdx(name, license_expr)
        own = "github.com/kuhyx/" in url
        if own and verdict != "foss":
            # kuhy's PKGBUILDs often just say "custom"; his checkout's LICENSE is the truth.
            verdict, reason = own_repo_verdict(url, verdict, reason)
        items.append(
            Item(
                name=name,
                version=version or None,
                source="aur" if name in foreign else "pacman",
                verdict=verdict,
                license=license_expr,
                reason=reason,
                url=url or None,
                explicit=name in explicit,
                orphan=name in orphans,
                own=own,
                requiredBy=[r for r in required.split(LIST_DELIM) if r],
                removeCommand=f"sudo pacman -Rns {name}",
            ),
        )
    return items


def scan() -> list[Item]:
    """Return every installed pacman package."""
    rows = _lines(["expac", "-Q", "-l", LIST_DELIM, EXPAC_FORMAT])
    explicit = set(_lines(["pacman", "-Qqe"]))
    foreign = set(_lines(["pacman", "-Qqm"]))
    orphans = set(_lines(["pacman", "-Qdtq"]))
    return parse_expac(rows, explicit, foreign, orphans)


def owned_by_pacman(paths: list[str]) -> set[str]:
    """Return the subset of paths that some installed package owns."""
    if not paths:
        return set()
    proc = subprocess.run(["pacman", "-Qqo", *paths], capture_output=True, text=True, check=False)
    # pacman reports unowned paths on stderr and still owns-lists the rest in order;
    # map back via the error lines instead of trusting stdout order. Match whole
    # lines: "No package owns /usr/bin/pacman.orig" must not unown /usr/bin/pacman.
    prefix = "error: No package owns "
    unowned = {line.removeprefix(prefix) for line in proc.stderr.splitlines() if line.startswith(prefix)}
    return set(paths) - unowned
