"""POM parsing for the Maven/Gradle cache scanner.

Only what the license lookup needs: the declared licenses, the `<parent>` to
walk when there are none, the runtime dependencies, and the one dependency of
a Gradle plugin marker. POMs come from an untrusted cache: parse failures
return None, nothing is resolved over the network here, and ElementTree
never fetches external entities.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from foss_audit.own_license import TEXT_IDS, identify

Gav = tuple[str, str, str]
RUNTIME_SCOPES = frozenset({"", "compile", "runtime"})
PROPERTY = re.compile(r"\$\{([^}]+)\}")
HEADER_COMMENT = re.compile(rb"<!--(.*?)-->", re.DOTALL)
KNOWN_IDS = frozenset(spdx for _, spdx in TEXT_IDS)


@dataclass(frozen=True)
class Pom:
    """The license-relevant part of one POM."""

    licenses: tuple[str, ...]
    # The URL of each license that has no <name>, which then stands in for it.
    unnamed_urls: tuple[str, ...]
    parent: Gav | None
    deps: tuple[str, ...]
    group: str
    # <scm> and project <url>s: where the source, and its LICENSE, live.
    source_urls: tuple[str, ...]
    # A Gradle plugin marker (<id>.gradle.plugin, no license, one dependency)
    # points at the real plugin artifact.
    marker: Gav | None
    # The license a comment before <project> grants the POM file itself.
    header: str = ""


def gav_name(gav: Gav) -> str:
    """`group:artifact:version`."""
    return ":".join(gav)


def pom_path(gav: Gav) -> str:
    """`gav`'s POM below a repository base URL."""
    group, artifact, version = gav
    return f"{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}.pom"


def _strip_namespaces(root: ET.Element) -> ET.Element:
    for element in root.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]
    return root


def _text(element: ET.Element | None, path: str) -> str:
    return (element.findtext(path) or "").strip() if element is not None else ""


def _properties(root: ET.Element, parent: ET.Element | None) -> dict[str, str]:
    """The simple `${...}` values a dependency coordinate may use."""
    group = _text(root, "groupId") or _text(parent, "groupId")
    values = {
        key: value
        for key, value in (
            ("project.groupId", group),
            ("pom.groupId", group),
            ("groupId", group),
            ("project.parent.groupId", _text(parent, "groupId")),
            ("parent.groupId", _text(parent, "groupId")),
            ("project.artifactId", _text(root, "artifactId")),
            ("artifactId", _text(root, "artifactId")),
        )
        if value
    }
    props = root.find("properties")
    for prop in props if props is not None else ():
        values.setdefault(prop.tag, (prop.text or "").strip())
    return values


def _resolve(value: str, props: dict[str, str]) -> str:
    """`value` with known properties substituted; "" when one is unknown."""
    resolved = PROPERTY.sub(lambda m: props.get(m.group(1), m.group(0)), value)
    return "" if "${" in resolved else resolved


def _parent(element: ET.Element | None) -> Gav | None:
    gav = (_text(element, "groupId"), _text(element, "artifactId"), _text(element, "version"))
    return gav if all(gav) and not any("${" in part for part in gav) else None


def _deps(root: ET.Element, props: dict[str, str]) -> tuple[list[str], list[Gav]]:
    """Runtime `group:artifact` names, and every dependency's full coordinate."""
    names: list[str] = []
    coords: list[Gav] = []
    for dep in root.findall("dependencies/dependency"):
        group = _resolve(_text(dep, "groupId"), props)
        artifact = _resolve(_text(dep, "artifactId"), props)
        if not group or not artifact:
            continue
        coords.append((group, artifact, _resolve(_text(dep, "version"), props)))
        if _text(dep, "scope") in RUNTIME_SCOPES and _text(dep, "optional") != "true":
            names.append(f"{group}:{artifact}")
    return names, coords


def header_license(data: bytes) -> str:
    """The license the POM's leading comments name, when `identify` knows it."""
    head = data.split(b"<project", 1)[0]
    text = " ".join(c.decode("utf-8", errors="replace") for c in HEADER_COMMENT.findall(head))
    spdx = identify(text) if text.strip() else ""
    return spdx if spdx in KNOWN_IDS else ""


def parse_pom(data: bytes) -> Pom | None:
    """The license-relevant fields of a POM, or None when it is not valid XML."""
    try:
        root = _strip_namespaces(ET.fromstring(data))  # noqa: S314 - expat resolves no external entities
    except ET.ParseError:
        return None
    licenses: list[str] = []
    unnamed: list[str] = []
    for lic in root.findall("licenses/license"):
        name, url = _text(lic, "name"), _text(lic, "url")
        if name or url:
            licenses.append(name or url)
        if url and not name:
            unnamed.append(url)
    parent_el = root.find("parent")
    props = _properties(root, parent_el)
    names, coords = _deps(root, props)
    parent = _parent(parent_el)
    is_marker = _text(root, "artifactId").endswith(".gradle.plugin") and not licenses and parent is None
    marker = coords[0] if is_marker and len(coords) == 1 and coords[0][2] else None
    return Pom(
        licenses=tuple(licenses),
        unnamed_urls=tuple(unnamed),
        parent=parent,
        deps=tuple(dict.fromkeys(names)),
        group=_text(root, "groupId") or _text(parent_el, "groupId"),
        source_urls=tuple(u for u in (_text(root, p) for p in ("scm/url", "scm/connection", "url")) if u),
        marker=marker,
        header=header_license(data),
    )
