"""The license a README names: its "License" section or a `License: X` line."""

from __future__ import annotations

import re
from pathlib import Path

from foss_audit.upstream_git import README_FILE

README_BYTES = 1 << 20
# "## License" + the next lines, or a "License: X" line; the license token comes after.
README_SECTION = re.compile(
    r"(?im)^(?:#{1,6}[ \t]*|\W*)licen[cs]e(?:[ \t]*:\W*|[ \t]*\n)(.{0,300})", re.DOTALL
)
README_IDS = (
    (re.compile(r"(?i)\bapache(?: licen[cs]e)?,? (?:version |v)?2(?:\.0)?"), lambda m: "Apache-2.0"),
    (re.compile(r"(?i)\bbsd[- ]([234])[- ]clause"), lambda m: f"BSD-{m[1]}-Clause"),
    (re.compile(r"(?i)\bmpl[- ]?2(?:\.0)?\b"), lambda m: "MPL-2.0"),
    (
        re.compile(r"\b(A?L?GPL)[- ]?v?(\d(?:\.\d)?)"),
        lambda m: f"{m[1]}-{m[2] if '.' in m[2] else m[2] + '.0'}",
    ),
    (re.compile(r"\b(MIT|ISC|Unlicense)\b"), lambda m: m[1]),
)


def readme_license(text: str) -> str:
    """A license named in the README's License section or `License: X` line, else ""."""
    section = README_SECTION.search(text)
    if not section:
        return ""
    hits = [(m.start(), build(m)) for pattern, build in README_IDS if (m := pattern.search(section.group(1)))]
    return min(hits)[1] if hits else ""


def local_readme_license(root: Path) -> tuple[str, str]:
    """(license, where) a local checkout's README names, as upstream READMEs are read
    (first README only, its License section or `License: X` line); ("", "") if none."""
    readme = next((p for p in sorted(root.glob("*")) if README_FILE.match(p.name) and p.is_file()), None)
    if readme is None:
        return "", ""
    named = readme_license(readme.read_bytes()[:README_BYTES].decode("utf-8", errors="replace"))
    return (named, f"{readme.name} of {root} names the license (no license file)") if named else ("", "")
