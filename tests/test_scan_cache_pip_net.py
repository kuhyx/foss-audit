"""pip fallbacks: the ~/src checkout, PyPI JSON and sdist, then the source repository."""

# ruff: noqa: F811  (the autouse no_network fixture is imported)
from __future__ import annotations

import json
from pathlib import Path

import pytest

from foss_audit import scan_cache_pip_net
from tests.pip_helpers import MIT_TEXT, meta, no_network, rec, sdist  # noqa: F401

# --- network and checkout fallbacks ---------------------------------------------


def test_checkout_fallback(tmp_path: Path) -> None:
    bad, empty, good = (tmp_path / n for n in ("bad", "empty", "good"))
    for d in (bad, empty, good):
        d.mkdir()
    (bad / "pyproject.toml").write_text("[project\n")
    (good / "pyproject.toml").write_text('[project]\nlicense = "MIT"\n')
    record = scan_cache_pip_net.from_checkout(rec(), [bad, good])
    assert (record.license, record.license_from) == ("MIT", f"LICENSE/pyproject of ~/src checkout {good}")
    record = scan_cache_pip_net.from_checkout(rec(), [empty])
    assert record.license_from == f"METADATA in x; no license in ~/src checkout {empty}"
    plain = tmp_path / "plain"
    (plain / ".git").mkdir(parents=True)  # a git root whose README names nothing
    (empty / ".git").mkdir()
    (empty / "README").write_text("License: ISC\n")
    record = scan_cache_pip_net.from_checkout(rec(), [plain, empty])
    assert (record.license, record.license_from) == (
        "ISC",
        f"README of {empty} names the license (no license file)",
    )


JSON_URL = "https://pypi.org/pypi/demo/1.0/json"


def pypi(info: dict[str, object], urls: list[dict[str, str]] | None = None) -> bytes:
    return json.dumps({"info": info, "urls": urls or []}).encode()


def test_pypi_json_license(no_network: dict[str, bytes]) -> None:
    no_network[JSON_URL] = pypi(
        {
            "license_expression": None,
            "license": "UNKNOWN",
            "classifiers": ["License :: OSI Approved :: MIT License"],
        }
    )
    record = scan_cache_pip_net.from_pypi(rec())
    assert (record.license, record.license_from) == ("MIT License", f"PyPI JSON {JSON_URL}")


def test_pypi_sdist_license_file(no_network: dict[str, bytes]) -> None:
    sdist_url = "https://files/demo-1.0.tar.gz"
    no_network[JSON_URL] = pypi(
        {}, [{"packagetype": "bdist_wheel", "url": "w"}, {"packagetype": "sdist", "url": sdist_url}]
    )
    no_network[sdist_url] = sdist({"demo-1.0/PKG-INFO": meta("demo"), "demo-1.0/LICENSE": MIT_TEXT})
    record = scan_cache_pip_net.from_pypi(rec())
    assert (record.license, record.license_from) == ("MIT", f"license file in PyPI sdist {sdist_url}")


def upstream(monkeypatch: pytest.MonkeyPatch, answers: dict[str, tuple[str, str]]) -> list[str]:
    """Serve upstream_license from `answers` (else offline); returns the URLs asked."""
    asked: list[str] = []

    def lookup(repo: str) -> tuple[str, str]:
        asked.append(repo)
        return answers.get(repo, ("", f"upstream {repo}: fetch failed: offline"))

    monkeypatch.setattr(scan_cache_pip_net.upstream_license, "upstream_license", lookup)
    return asked


def test_source_repo_license_any_forge(no_network: dict[str, bytes], monkeypatch: pytest.MonkeyPatch) -> None:
    repo = "https://codeberg.org/o/r"
    urls = {
        "Documentation": "https://o.readthedocs.io",
        "Homepage": "https://github.com/o/site",
        "Source": f"{repo}/src/branch/main",
    }
    no_network[JSON_URL] = pypi({"project_urls": urls})
    asked = upstream(monkeypatch, {repo: ("Apache-2.0", f"upstream {repo} HEAD: LICENSE file")})
    record = scan_cache_pip_net.from_pypi(rec())
    assert (record.license, record.license_from) == (
        "Apache-2.0",
        f"upstream {repo} HEAD: LICENSE file (default branch, not 1.0)",
    )
    assert asked == [repo]  # the repository-named link beats an earlier forge homepage


def test_source_repo_falls_back_to_home_page(no_network: dict[str, bytes]) -> None:
    info = {"project_urls": {"Docs": "https://o.readthedocs.io"}, "home_page": "https://gitlab.com/o/r"}
    assert scan_cache_pip_net.source_repo(info, None) == "https://gitlab.com/o/r"
    assert scan_cache_pip_net.source_repo({}, "https://github.com/o/r.git") == "https://github.com/o/r"
    assert scan_cache_pip_net.source_repo({"project_urls": None}, "https://example.org") == ""


def test_every_place_tried_is_named(no_network: dict[str, bytes], monkeypatch: pytest.MonkeyPatch) -> None:
    sdist_url = "https://files/demo-1.0.tar.gz"
    repo = "https://github.com/o/r"
    no_network[JSON_URL] = pypi({}, [{"packagetype": "sdist", "url": sdist_url}])
    no_network[sdist_url] = sdist({"demo-1.0/PKG-INFO": meta("demo")})
    upstream(monkeypatch, {})
    record = scan_cache_pip_net.from_pypi(rec(url=repo))
    assert record.license_from == (
        f"METADATA in x; PyPI JSON {JSON_URL} (no license); PyPI sdist {sdist_url} (no license file); "
        f"upstream {repo}: fetch failed: offline"
    )
    upstream(monkeypatch, {repo: ("", f"upstream {repo} HEAD: no license file")})
    record = scan_cache_pip_net.from_pypi(rec(url=repo))
    assert record.license_from.endswith(f"(no license file); upstream {repo} HEAD: no license file")
    no_network[JSON_URL] = pypi({})
    record = scan_cache_pip_net.from_pypi(rec())
    assert record.license_from.endswith("(no license); PyPI lists no sdist; no source repository URL")


def test_failed_fetch_is_visible() -> None:
    record = scan_cache_pip_net.from_pypi(rec())
    assert record.license == ""
    assert record.license_from == f"METADATA in x; fetch failed: {JSON_URL}: HTTP Error 404: Not Found"


def test_resolve_only_blank_and_never_local_on_pypi(tmp_path: Path, no_network: dict[str, bytes]) -> None:
    no_network["https://pypi.org/pypi/remote/1.0/json"] = pypi({"license": "BSD"})
    (tmp_path / "LICENSE").write_text(MIT_TEXT)
    records = [
        rec("kept", lic="MPL2"),
        rec("mine"),
        rec("editable", local=True),
        rec("remote"),
    ]
    out = scan_cache_pip_net.resolve(records, {"mine": [tmp_path]})
    assert [r.license for r in out] == ["MPL2", "MIT", "", "BSD"]
