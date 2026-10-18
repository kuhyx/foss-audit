"""One npm package's license, deps and URL from its package.json and files; never the network."""

# ruff: noqa: F811  (the autouse no_network fixture is imported)
from __future__ import annotations

from typing import Any

import pytest

from foss_audit.scan_cache_npm_fallback import repository_url, upstream, url_license
from foss_audit.scan_cache_npm_manifest import (
    LICENSE_NAME,
    NOWHERE,
    excerpt,
    field_text,
    found,
    project_url,
    readme_license,
    recognised,
    resolve_license,
    runtime_deps,
)
from tests.npm_helpers import MIT, OFFLINE, PROPRIETARY, PUBLIC_DOMAIN, files, no_network  # noqa: F401

# --- manifest --------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (" MIT ", "MIT"),
        ({"type": "BSD"}, "BSD"),
        ({"name": "ISC"}, "ISC"),
        ([{"type": "MIT"}], "MIT"),
        (["MIT", {"type": "Apache-2.0"}], "(MIT OR Apache-2.0)"),
        ([], ""),
        (3, ""),
    ],
)
def test_field_text_shapes(value: Any, text: str) -> None:
    assert field_text(value) == text


def test_license_file_names() -> None:
    good = ["LICENSE", "licence.md", "COPYING", "LICENSE-MIT", "MIT-LICENSE.txt", "UNLICENSE"]
    bad = ["._MIT-LICENSE.txt", "license-checker.js", "licenses", "mylicense"]
    assert all(LICENSE_NAME.match(n) for n in good)
    assert not any(LICENSE_NAME.match(n) for n in bad)


def test_excerpt_and_recognised() -> None:
    assert excerpt("/*\n a \n=====\n\nb\nc\nd") == "a b c"
    assert recognised("MIT")
    assert not recognised("")
    assert not recognised("Open Source")


def test_url_license(no_network: dict[str, Any]) -> None:
    no_network["urls"] = {"https://m": MIT.encode(), "https://pd": PUBLIC_DOMAIN.encode(), "https://x": b"Hi"}
    assert url_license("https://m") == ("MIT", "license URL https://m")
    lic, where = url_license("https://pd")
    assert lic.startswith('Author: G Year: 2013 This code is released into the "public domain"')
    assert where == "license URL https://pd"
    assert url_license("https://x") == ("", "license URL https://x: unrecognised text 'Hi'")
    assert url_license("https://gone") == ("", "license URL https://gone: fetch failed: offline")


@pytest.mark.parametrize(
    ("repo", "url"),
    [
        ({"url": "git+https://h/r.git"}, "git+https://h/r.git"),
        (" https://h/r ", "https://h/r"),
        ("github:u/r", "https://github.com/u/r"),
        ("gitlab:u/r", "https://gitlab.com/u/r"),
        ("bitbucket:u/r", "https://bitbucket.org/u/r"),
        ("u/r.js", "https://github.com/u/r.js"),
        (None, ""),
        ({"type": "git"}, ""),
    ],
)
def test_repository_url(repo: Any, url: str) -> None:
    assert repository_url({"repository": repo}) == url


def test_upstream(no_network: dict[str, Any]) -> None:
    assert upstream({}) == ("", "no repository URL")
    no_network["upstream"] = ("MIT", "upstream https://h/r HEAD: LICENSE file")
    assert upstream({"repository": "https://h/r"}) == ("MIT", "upstream https://h/r HEAD: LICENSE file")
    assert no_network["asked"] == ["https://h/r"]


def test_license_url_field(no_network: dict[str, Any]) -> None:
    url = "http://example.org/LICENSE.txt"
    no_network["urls"] = {url: PUBLIC_DOMAIN.encode()}
    lic, where = resolve_license({"license": url}, {})
    assert "public domain" in lic
    assert where == f"license URL {url}"
    # A failed fetch is named, and the package's own LICENSE still answers.
    lic, where = resolve_license({"license": "https://gone"}, files(LICENSE=MIT))
    assert (lic, where) == ("MIT", "LICENSE file (package.json: https://gone)")
    lic, where = resolve_license({"license": "https://gone"}, {})
    assert lic == "https://gone"
    assert where == (
        "package.json; license URL https://gone: fetch failed: offline; "
        "LICENSE file, README license section; no repository URL"
    )


def test_unjudgeable_field_asks_upstream_last(no_network: dict[str, Any]) -> None:
    data = {"license": "Open Source", "repository": "github:u/r"}
    no_network["upstream"] = ("BSD-3-Clause", "upstream https://github.com/u/r HEAD: LICENSE file")
    assert resolve_license(data, files(README_md="hi")) == (
        "BSD-3-Clause",
        "upstream https://github.com/u/r HEAD: LICENSE file (default branch, not this version)"
        " (package.json: Open Source)",
    )
    no_network["upstream"] = ("", OFFLINE)
    lic, where = resolve_license(data, files(LICENSE="Inno Setup License\n=====\nUse it freely."))
    assert lic == "Inno Setup License Use it freely."
    assert where == (
        "LICENSE file (unrecognised text); checked package.json; LICENSE file, README license section; "
        + OFFLINE
    )
    assert resolve_license(data, {}) == (
        "Open Source",
        f"package.json; LICENSE file, README license section; {OFFLINE}",
    )


@pytest.mark.parametrize(
    ("text", "lic"),
    [
        ("# x\nno words here", ""),
        ("## License: MIT\n", "MIT"),
        ("**License**: ISC", "ISC"),
        ("## License\n\n" + MIT + "## Next\nBSD", "MIT"),
        ("License\n=======\n\n(The MIT License)\n\n## Other\n", "The MIT License"),
        ("## License\n\n## Credits\n", ""),
    ],
)
def test_readme_license(text: str, lic: str) -> None:
    assert readme_license(text) == lic


def test_field_wins() -> None:
    assert resolve_license({"license": "MIT"}, files(LICENSE=PROPRIETARY)) == ("MIT", "package.json")
    assert resolve_license({"licenses": [{"type": "BSD"}]}, {}) == ("BSD", "package.json")


def test_no_field_reads_license_then_readme() -> None:
    assert resolve_license({}, files(LICENSE=MIT)) == ("MIT", "LICENSE file")
    readme = files(LICENSE="Copyright me", README_md="## License\n\nISC")
    assert resolve_license({}, readme) == ("ISC", "README.md license section")
    assert resolve_license({}, files(LICENSE=PROPRIETARY)) == (
        "(c) Acme Corp. All rights reserved. No use without a contract.",
        "LICENSE file (unrecognised text)",
    )
    assert resolve_license({}, files(README_md="nothing")) == ("", f"{NOWHERE}; no repository URL")


def test_no_field_no_files_asks_upstream_last(no_network: dict[str, Any]) -> None:
    data = {"version": "1.0.0", "repository": {"url": "git+https://github.com/u/r.git"}}
    no_network["upstream"] = ("MIT", "upstream https://github.com/u/r HEAD: LICENSE file")
    assert resolve_license(data, files(README_md="nothing")) == (
        "MIT",
        "upstream https://github.com/u/r HEAD: LICENSE file (default branch, not 1.0.0)",
    )
    assert no_network["asked"] == ["git+https://github.com/u/r.git"]
    no_network["upstream"] = ("", OFFLINE)
    assert resolve_license({"repository": "u/r"}, {}) == ("", f"{NOWHERE}; {OFFLINE}")
    # An unrecognised LICENSE text is the package's own answer: upstream is not asked.
    no_network["asked"].clear()
    assert resolve_license(data, files(LICENSE=PROPRIETARY))[1] == "LICENSE file (unrecognised text)"
    assert no_network["asked"] == []


def test_unrecognised_field_falls_back_to_a_recognised_file() -> None:
    assert resolve_license({"license": "BDS-3-Clause"}, files(LICENSE=MIT)) == (
        "MIT",
        "LICENSE file (package.json: BDS-3-Clause)",
    )
    assert resolve_license({"license": "Apache2"}, files(LICENSE=PROPRIETARY)) == ("Apache2", "package.json")


def test_see_license_in_named_file() -> None:
    field = {"license": "SEE LICENSE IN ./LICENSE.txt"}
    assert resolve_license(field, files(LICENSE_txt=MIT)) == (
        "MIT",
        "LICENSE.txt (package.json: SEE LICENSE IN ./LICENSE.txt)",
    )
    lic, where = resolve_license(field, files(LICENSE_txt=PROPRIETARY))
    assert lic.startswith("SEE LICENSE IN ./LICENSE.txt: (c) Acme Corp. All rights reserved")
    assert where.startswith("LICENSE.txt")


def test_see_license_in_readme_without_section_reads_license_file() -> None:
    field = {"license": "SEE LICENSE IN README.md"}
    assert resolve_license(field, files(README_md="# SDK\n", LICENSE_md=MIT)) == (
        "MIT",
        "LICENSE.md file (package.json: SEE LICENSE IN README.md)",
    )
    readme = files(README_md="## License\n\nISC\n")
    assert resolve_license(field, readme) == ("ISC", "README.md (package.json: SEE LICENSE IN README.md)")
    lic, where = resolve_license(field, files(README_md="# SDK\n", LICENSE_md=PROPRIETARY))
    assert lic.startswith("SEE LICENSE IN README.md: (c) Acme")
    assert where == "package.json, nothing in README.md"


def test_bare_see_license_and_missing_target() -> None:
    assert resolve_license({"license": "SEE LICENSE"}, {}) == ("SEE LICENSE", "package.json")
    assert resolve_license({"license": "SEE LICENSE IN EULA"}, {}) == (
        "SEE LICENSE IN EULA",
        "package.json, nothing in EULA",
    )


def test_project_url_and_deps() -> None:
    assert project_url({"homepage": "https://h"}, "x") == "https://h"
    assert project_url({"homepage": "h", "repository": {"url": "git+https://r"}}, "x") == "https://r"
    assert project_url({"repository": "https://r2"}, "x") == "https://r2"
    assert project_url({"repository": "user/repo"}, "@s/x") == "https://www.npmjs.com/package/@s/x"
    assert runtime_deps({"dependencies": {"b": "1", "a": "2"}, "devDependencies": {"c": "1"}}) == ("a", "b")
    assert runtime_deps({"dependencies": ["a"]}) == ()


def test_found_fills_gaps_from_index() -> None:
    item = found({"name": 3}, {}, "idx", "1.0", "pnpm store v10")
    assert (item.name, item.cached.version, item.cached.license) == ("idx", "1.0", "")
    assert item.cached.license_from == f"{NOWHERE}; no repository URL (pnpm store v10)"
