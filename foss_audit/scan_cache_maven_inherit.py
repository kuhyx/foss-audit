"""Maven versions whose own data names no license borrow one, labelled as borrowed.

Runs after `resolve_all`, on versions it left blank (its POM, parent chain,
.module, JAR and scm source repository all checked), in this order:

b. another cached version of the SAME artifact: the nearest newer licensed
   one, else the nearest older ("license of 2.0, not 1.0");
c. a sibling artifact in the same groupId: one of the same version first,
   then the nearest newer, then the nearest older ("license of g:sibling 1.0").
   Siblings that disagree on the verdict lend nothing: a group like
   com.google.android.gms mixes free and proprietary artifacts, and a false
   "foss" is the costly mistake.

A version whose lookup hit a failed fetch is not proven blank and borrows
nothing. Donors are versions that declare a license in their own data, so nothing
borrowed is lent on. A version still blank says where else it looked.
"""

from __future__ import annotations

from foss_audit.cache_common import CachedArtifact, CachedVersion, version_key
from foss_audit.licenses import classify_text


def _own(cv: CachedVersion) -> bool:
    """A donor: a license of its own that `classify_text` recognises."""
    return bool(cv.license.strip()) and not classify_text(cv.license)[1].startswith("unrecognised")


def proven_blank(cv: CachedVersion) -> bool:
    """No license, and not because a fetch failed: a failure stays visible, retried next scan."""
    return not cv.license.strip() and "fetch failed" not in cv.license_from


def _nearest(donors: list[CachedVersion], version: str) -> CachedVersion | None:
    """The same version, else the nearest newer, else the nearest older; ties keep list order."""
    key = version_key(version)
    others = [d for d in donors if d.version != version]
    newer = sorted((d for d in others if version_key(d.version) > key), key=lambda d: version_key(d.version))
    older = sorted(
        (d for d in others if version_key(d.version) <= key),
        key=lambda d: version_key(d.version),
        reverse=True,
    )
    return next(iter([*(d for d in donors if d.version == version), *newer, *older]), None)


def _sibling(group: str, name: str, version: str, own: dict[str, list[CachedVersion]]) -> tuple[str, str]:
    """(license, label) from the best sibling, or ("", why none)."""
    picks = sorted(
        (sib, pick)
        for sib, donors in own.items()
        if sib != name and sib.split(":")[0] == group and (pick := _nearest(donors, version)) is not None
    )
    if not picks:
        return "", f"no {group} sibling declares one"
    if len({classify_text(cv.license)[0] for _, cv in picks}) > 1:
        said = ", ".join(f"{sib} {cv.version} {cv.license}" for sib, cv in picks)
        return "", f"{group} siblings disagree ({said})"
    best = _nearest([cv for _, cv in picks], version)
    sib, cv = next(p for p in picks if p[1] is best)
    return cv.license, f"license of {sib} {cv.version} ({cv.license_from})"


def borrow(arts: list[CachedArtifact]) -> None:
    """Fill each blank version from another version, else a group sibling."""
    own = {a.name: [cv for cv in a.versions if _own(cv)] for a in arts}
    for art in arts:
        group = art.name.split(":")[0]
        for cv in art.versions:
            if not proven_blank(cv):
                continue
            donor = _nearest(own[art.name], cv.version)
            if donor is not None:
                lic = donor.license
                label = f"license of {donor.version}, not {cv.version} ({donor.license_from})"
            else:
                lic, label = _sibling(group, art.name, cv.version, own)
            if lic:
                cv.license, cv.license_from = lic, f"{label}; {cv.version} itself: {cv.license_from}"
            else:
                cv.license_from = f"{cv.license_from}; no other version of it declares one; {label}"
