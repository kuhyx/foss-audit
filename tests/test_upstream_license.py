"""upstream_license: URL normalisation and the forge-agnostic git path (local file:// repos only)."""

# ruff: noqa: F811  (pytest fixtures are imported, then named as parameters)
from __future__ import annotations

import json
from pathlib import Path

import pytest

from foss_audit import upstream_git, upstream_readme
from foss_audit import upstream_license as ul
from tests.upstream_helpers import APACHE, MIT, TODO, cache_file, git, make_repo  # noqa: F401

# --- URL normalisation --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://github.com/o/r", "https://github.com/o/r"),
        ("https://github.com/o/r.git", "https://github.com/o/r"),
        ("https://github.com/o/r/", "https://github.com/o/r"),
        ("git+https://github.com/o/r.git", "https://github.com/o/r"),
        ("git+https://GitHub.com/o/r.git#abc123", "https://github.com/o/r"),
        ("git@github.com:o/r.git", "https://github.com/o/r"),
        ("git@gitlab.example.org:group/sub/r", "https://gitlab.example.org/group/sub/r"),
        ("host.example:/srv/git/r.git", "https://host.example/srv/git/r"),
        ("ssh://git@codeberg.org/o/r.git", "https://codeberg.org/o/r"),
        ("ssh://git@git.example.org:2222/o/r", "https://git.example.org/o/r"),
        ("git+ssh://git@git.sr.ht/~o/r", "https://git.sr.ht/~o/r"),
        ("git://git.example.org/o/r.git", "https://git.example.org/o/r"),
        ("https://user:secret@bitbucket.org/o/r.git", "https://bitbucket.org/o/r"),
        ("https://git.example.org:8443/o/r.git?x=1", "https://git.example.org:8443/o/r"),
        ("http://git.example.org/o/r", "http://git.example.org/o/r"),
        ("  https://gitea.example.org/o/r.git  ", "https://gitea.example.org/o/r"),
        ("file:///tmp/x/repo.git", "file:///tmp/x/repo"),
        ("github:u/r", "https://github.com/u/r"),
        ("gitlab:u/r", "https://gitlab.com/u/r"),
        ("bitbucket:u/r.git", "https://bitbucket.org/u/r"),
        ("github:u/r#v1.2", "https://github.com/u/r"),
        ("u/r", "https://github.com/u/r"),
        ("github.com:o/r", "https://github.com/o/r"),
        ("", ""),
        ("/home/me/repo", ""),
        ("ext::sh -c evil", ""),
        ("ftp://example.org/o/r", ""),
        ("https:///o/r", ""),
        ("https://example.org:notaport/o/r", ""),
    ],
)
def test_normalise(raw: str, expected: str) -> None:
    assert ul.normalise(raw) == expected


# --- the git path ---------------------------------------------------------------------------


def test_license_file_is_identified_and_cached(tmp_path: Path, cache_file: Path) -> None:
    url = make_repo(tmp_path, {"LICENSE": MIT, "README.md": "# hi\n", "src/LICENSE": APACHE})
    found, checked = ul.upstream_license(url)
    assert (found, checked) == ("MIT", f"upstream {url} HEAD: LICENSE file")
    entry = json.loads(cache_file.read_text())[url]
    assert entry == {"license": "MIT", "checked": checked, "fetched_at": 1_000_000.0}


def test_several_files_join_and_dedupe(tmp_path: Path) -> None:
    url = make_repo(
        tmp_path, {"LICENSE-MIT": MIT, "LICENSE-APACHE": APACHE, "COPYING": MIT, "UNLICENSE": MIT}
    )
    found, checked = ul.upstream_license(url)
    assert found == "Apache-2.0 AND MIT"
    assert checked == f"upstream {url} HEAD: COPYING, LICENSE-APACHE file"


def test_no_license_file_is_a_result_not_a_failure(tmp_path: Path, cache_file: Path) -> None:
    url = make_repo(tmp_path, {"README.md": "# nothing here\n", "LICENSE.d/x": "dir, not a file"})
    assert ul.upstream_license(url) == ("", f"upstream {url} HEAD: no license file")
    assert json.loads(cache_file.read_text())[url]["license"] == ""


def test_flutter_placeholder_counts_as_no_license(tmp_path: Path) -> None:
    url = make_repo(tmp_path, {"LICENSE": TODO})
    assert ul.upstream_license(url) == (
        "",
        f"upstream {url} HEAD: no license file (placeholder LICENSE skipped)",
    )


def test_symlinked_and_oversized_license_are_not_read(
    tmp_path: Path, cache_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = make_repo(tmp_path, {"LICENSE": MIT, "real": MIT})
    repo = tmp_path / "repo"
    (repo / "LICENSE.link").symlink_to("/etc/passwd")
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "link")
    assert ul.upstream_license(url)[0] == "MIT"
    cache_file.unlink()
    monkeypatch.setattr(upstream_git, "MAX_BLOB", 10)
    assert ul.upstream_license(url + "/")[1].endswith("no license file")  # normalised key is the same repo


@pytest.mark.parametrize(
    ("readme", "expected"),
    [
        ("# x\n\n## License\n\nMIT (c) someone\n", "MIT"),
        ("# x\n\nLicense: Apache License 2.0\n", "Apache-2.0"),
        ("x\n\n## License\nLicensed under BSD-3-Clause, see file.\n", "BSD-3-Clause"),
        ("**License:** GPLv3 or later\n", "GPL-3.0"),
        ("## Licence\nLGPL-2.1 only\n", "LGPL-2.1"),
        ("## License\nGPL-2 only\n", "GPL-2.0"),
        ("## License\nAGPL 3\n", "AGPL-3.0"),
        ("## License\nMPL-2.0\n", "MPL-2.0"),
        ("## License\nThe Unlicense, ISC\n", "Unlicense"),
        ("## License\nISC\n", "ISC"),
        ("<div>\n\n[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://x)\n", "MIT"),
        ("## License\nAll rights reserved.\n", ""),
        ("# no such section, MIT mentioned in passing\n", ""),
    ],
)
def test_readme_is_the_last_resort(tmp_path: Path, readme: str, expected: str) -> None:
    url = make_repo(tmp_path, {"README.md": readme})
    found, checked = ul.upstream_license(url)
    assert found == expected
    assert checked == (
        f"upstream {url} HEAD: README.md names the license (no license file)"
        if expected
        else f"upstream {url} HEAD: no license file"
    )


def test_local_readme_license(tmp_path: Path) -> None:
    assert upstream_readme.local_readme_license(tmp_path) == ("", "")
    (tmp_path / "readme").mkdir()
    (tmp_path / "README.md").write_text(
        "[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)]\n"
    )
    assert upstream_readme.local_readme_license(tmp_path) == (
        "MIT",
        f"README.md of {tmp_path} names the license (no license file)",
    )
    (tmp_path / "README.md").write_text("## License\nAll rights reserved.\n")
    assert upstream_readme.local_readme_license(tmp_path) == ("", "")


def test_license_file_beats_readme(tmp_path: Path) -> None:
    url = make_repo(
        tmp_path, {"LICENSE": APACHE, "README.md": "## License\nMIT\n", "README": "ignored second"}
    )
    assert ul.upstream_license(url)[0] == "Apache-2.0"


def test_second_readme_is_ignored(tmp_path: Path) -> None:
    url = make_repo(tmp_path, {"README": "no license section", "README.md": "## License\nMIT\n"})
    assert ul.upstream_license(url)[0] == ""


# --- source links -> a fetchable repository ----------------------------------------------


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        ("scm:git:git@github.com:o/r.git", "https://github.com/o/r"),
        ("scm:git:https://git.example.org/srv/r.git", "https://git.example.org/srv/r"),
        ("SCM:GIT:git://host.example/r", "https://host.example/r"),
        ("scm:svn:https://svn.example.org/r/trunk", ""),
        ("scm:hg:https://hg.example.org/r", ""),
        ("https://github.com/o/r/tree/main/sub", "https://github.com/o/r"),
        ("https://github.com/o/r#readme", "https://github.com/o/r"),
        ("https://github.com/o", ""),
        ("https://codeberg.org/o/r/src/branch/main", "https://codeberg.org/o/r"),
        ("https://gitlab.com/g/sub/r/-/blob/main/LICENSE", "https://gitlab.com/g/sub/r"),
        ("https://gitlab.com/g/src", "https://gitlab.com/g/src"),
        ("https://git.sr.ht/~o/r/tree", "https://git.sr.ht/~o/r"),
        ("https://gitea.example.org/o/r/src/branch/main", "https://gitea.example.org/o/r"),
        ("https://example.org/project", ""),
        ("https://o.readthedocs.io/en/latest", ""),
        ("not a url", ""),
        ("", ""),
    ],
)
def test_repository(link: str, expected: str) -> None:
    assert ul.repository(link) == expected


def test_not_this_version() -> None:
    assert ul.not_this_version("1.2") == " (default branch, not 1.2)"
    assert ul.not_this_version("") == " (default branch, not this version)"
    assert ul.not_this_version(None) == " (default branch, not this version)"
