"""pip/uv cache scanner: metadata parsing, project usage and the whole scan.

Every cache is a small fixture under tmp_path; the network is never touched
(`cache_common.fetch_cached` is replaced for every test).
"""

# ruff: noqa: F811  (the autouse no_network fixture is imported)
from __future__ import annotations

import json
from email.parser import HeaderParser
from pathlib import Path

import pytest

from foss_audit import cache_common, scan_cache_pip, scan_cache_pip_used
from foss_audit.scan_cache_pip_meta import (
    FIELDS,
    Record,
    choose,
    classifier_license,
    extra_deps,
    known,
    norm,
    parse,
    project_url,
    runtime_deps,
)
from tests.pip_helpers import MIT_TEXT, dist_info, legacy, meta, no_files, no_network, rec, wheel  # noqa: F401

# --- metadata parsing ---------------------------------------------------------


def test_norm_is_pep503() -> None:
    assert norm("Foo.Bar__baz-Q") == "foo-bar-baz-q"


def test_known_rejects_blank_placeholder_and_unrecognised() -> None:
    assert known("MIT")
    assert not known("  ")
    assert not known("UNKNOWN")
    assert not known("Copyright 2020 Someone")


def test_runtime_deps_skip_extras_and_garbage() -> None:
    reqs = ["requests (>=2)", "Bar_Baz; python_version < '3.9'", "pytest; extra == 'test'", "!!!"]
    assert runtime_deps(reqs) == ("bar-baz", "requests")


def test_extra_deps_are_the_ones_an_extra_gates() -> None:
    reqs = ["requests", "Nvidia_Cublas==13.*; (sys_platform == 'linux') and extra == 'all'", "x; extra=='t'"]
    assert extra_deps(reqs) == ("nvidia-cublas", "x")
    record = parse(meta("Meta", "1", *(f"Requires-Dist: {r}" for r in reqs)), "o", no_files)
    assert record is not None
    assert (record.deps, record.extra_deps) == (("requests",), ("nvidia-cublas", "x"))
    [version] = scan_cache_pip.artifacts([record])[0].versions
    assert version.extra_deps == ("nvidia-cublas", "x")


def test_project_url_precedence() -> None:
    assert project_url(" https://home ", [], "x") == "https://home"
    urls = ["Documentation, https://docs", "Homepage, ", "Source Code, https://src"]
    assert project_url("UNKNOWN", urls, "x") == "https://src"
    assert project_url("", ["Docs, https://docs"], "Foo_Bar") == "https://pypi.org/project/foo-bar/"


def test_classifier_license_drops_bare_osi() -> None:
    classifiers = ["License :: OSI Approved", "License :: OSI Approved :: MIT License", "Topic :: X"]
    assert classifier_license(classifiers) == "MIT License"


def header(*lines: str) -> object:
    return HeaderParser().parsestr("\n".join(lines) + "\n\n")


def boom() -> list[tuple[str, str]]:
    raise AssertionError("files loaded")


def test_expression_is_final_even_unrecognised() -> None:
    found = choose(header("License-Expression: MIT", "License: UNKNOWN"), boom)
    assert found == ("MIT", "License-Expression")
    lines = ("License-Expression: BUSL-1.1", "Classifier: License :: OSI Approved :: Apache Software License")
    assert choose(header(*lines), boom) == ("BUSL-1.1", "License-Expression")


def test_license_field_text_is_identified() -> None:
    multi = header("License: Copyright Foo", "        Permission is hereby granted, free of charge")
    assert choose(multi, boom) == ("MIT", "License field (license text)")
    long_known = header("License: " + "x " * 70 + "Permission is hereby granted, free of charge")
    assert choose(long_known, boom) == ("MIT", "License field (license text)")
    long_unknown = "Copyright " + "y" * 130
    assert choose(header(f"License: {long_unknown}"), list) == (long_unknown, "License field")


def test_unrecognised_field_falls_through_to_classifier_then_files() -> None:
    lines = ("License: Copyright Foo", "Classifier: License :: Zope Public License")
    assert choose(header(*lines), boom) == ("Zope Public License", "License classifier")
    files = [("empty", "  "), ("NOTICE", "Copyright Bar"), ("LICENSE", MIT_TEXT)]
    assert choose(header("License: Copyright Foo"), lambda: files) == ("MIT", "license file LICENSE")


def test_unrecognised_kept_when_nothing_better() -> None:
    assert choose(header("License: MPL2"), list) == ("MPL2", "License field")
    assert choose(header(), lambda: [("NOTICE", "Copyright Bar")]) == ("Copyright Bar", "license file NOTICE")
    assert choose(header(), list) is None


def test_parse_record_and_blank_license_names_fields() -> None:
    text = meta("Demo_Pkg", "2.0", "Requires-Dist: Click", "Home-page: https://demo")
    record = parse(text, "pip wheels", no_files)
    assert record == Record("demo-pkg", "2.0", "", f"{FIELDS} in pip wheels", ("click",), "https://demo")
    assert parse("Metadata-Version: 2.1\n\n", "x", no_files) is None
    assert Record.from_json(json.loads(json.dumps(record.to_json()))) == record


# --- project usage ---------------------------------------------------------------


def test_names_in_project_files(tmp_path: Path) -> None:
    files = {
        "uv.lock": '[[package]]\nname = "Foo_Bar"\n[[package]]\nversion = "1"\n',
        "poetry.lock": '[[package]]\nname = "poetry.dep"\n',
        "requirements-dev.txt": "# comment\n-r base.txt\n-e .\nRequests>=2  # pinned\n\n",
        "pyproject.toml": (
            '[project]\ndependencies = ["click>=8"]\n[project.optional-dependencies]\nx = ["rich"]\n'
            '[dependency-groups]\ndev = ["pytest", {include-group = "x"}]\nbad = "nope"\n'
            '[build-system]\nrequires = ["hatchling"]\n'
            '[tool.poetry.dependencies]\npython = "^3"\nTyper = "*"\n'
            '[tool.poetry.group.test.dependencies]\nmypy = "*"\n'
        ),
        "broken/pyproject.toml": "[x",
    }
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    names = scan_cache_pip_used.names_in
    assert names(tmp_path / "uv.lock") == {"foo-bar"}
    assert names(tmp_path / "poetry.lock") == {"poetry-dep"}
    assert names(tmp_path / "requirements-dev.txt") == {"requests"}
    assert names(tmp_path / "pyproject.toml") == {"click", "rich", "pytest", "hatchling", "typer", "mypy"}
    assert names(tmp_path / "broken/pyproject.toml") == set()
    assert names(tmp_path / "missing.lock") == set()


def src_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "src"
    for repo, text in {
        "app": '[project]\nname = "My_App"\ndependencies = ["demo-pkg"]\n',
        "lib": '[project]\ndependencies = ["Demo.Pkg"]\n',
        "bad": "[project",
    }.items():
        (root / repo).mkdir(parents=True)
        (root / repo / "pyproject.toml").write_text(text)
    real_files, real_of = cache_common.project_files, cache_common.project_of
    monkeypatch.setattr(scan_cache_pip_used, "project_files", lambda names: real_files(names, root))
    monkeypatch.setattr(scan_cache_pip_used, "project_of", lambda path: real_of(path, root))
    return root


def test_used_by_and_checkouts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = src_tree(tmp_path, monkeypatch)
    assert scan_cache_pip_used.used_by() == {"demo-pkg": {"~/src/app", "~/src/lib"}}
    assert scan_cache_pip_used.checkouts() == {"my-app": [root / "app"]}


# --- whole scan -------------------------------------------------------------------


def test_any_metadata_only_copy_makes_the_version_a_meta_package() -> None:
    [one] = scan_cache_pip.per_version([rec(), rec(meta=True)])
    assert one.meta
    [version] = scan_cache_pip.artifacts([one])[0].versions
    assert version.meta


def test_best_copy_of_a_version() -> None:
    assert scan_cache_pip.best([rec(lic="Custom Corp License"), rec(lic="MIT")]).license == "MIT"
    assert scan_cache_pip.best([rec(), rec(lic="Custom Corp License")]).license == "Custom Corp License"
    assert scan_cache_pip.best([rec(license_from="a"), rec()]).license_from == "a"


def test_scan_pip_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ticks: dict[str, tuple[int, int | None]]
) -> None:
    pip, uv = tmp_path / "pip", tmp_path / "uv"
    body = pip / "http-v2/a/b/c/d/e/0001.body"
    body.parent.mkdir(parents=True)
    body.write_bytes(meta("Demo_Pkg", "1.0", "License-Expression: MIT", "Requires-Dist: Closed").encode())
    (pip / "http-v2/a/b/c/d/e/0002.body").write_bytes(b"PK\x03\x04broken")
    (pip / "http-v2/a/b/c/d/e/0003.body").write_bytes(meta("demo.pkg", "1.0").encode())
    (pip / "http-v2/a/b/c/d/e/dir.body").mkdir()
    old = pip / "http/a/b/c/d/e/f00"
    old.parent.mkdir(parents=True)
    old.write_bytes(legacy(meta("demo-pkg", "0.9", "License: BSD").encode()))
    whl = pip / "wheels/a/b/c/hash/closed-2.0-py3-none-any.whl"
    whl.parent.mkdir(parents=True)
    whl.write_bytes(wheel({"closed-2.0.dist-info/METADATA": meta("closed", "2.0")}))
    dist_info(uv / "archive-v0/id1", "freeware", meta("freeware", "1.0", "License: MIT"))
    monkeypatch.setattr(scan_cache_pip, "PIP_CACHE", pip)
    monkeypatch.setattr(scan_cache_pip, "UV_CACHE", uv)
    monkeypatch.setattr(scan_cache_pip, "checkouts", dict)
    monkeypatch.setattr(scan_cache_pip, "used_by", lambda: {"demo-pkg": {"~/src/app"}})

    records, bad = scan_cache_pip.all_records()
    assert (len(records), bad) == (5, 1)
    items = {i.name: i for i in scan_cache_pip.scan_pip_cache()}
    assert ticks["pip-cache"][0] == ticks["pip-cache"][1] > 0
    assert sorted(items) == ["closed", "demo-pkg", "freeware"]
    demo = items["demo-pkg"]
    assert (demo.source, demo.verdict, demo.version, demo.license) == (
        "pip-cache",
        "foss-partial",
        "1.0, 0.9",
        "MIT",
    )
    assert demo.reason == "depends on non-free closed"
    assert demo.requiredBy == ["~/src/app"]
    closed = items["closed"]
    assert closed.verdict == "nonfree"
    assert "fetch failed: https://pypi.org/pypi/closed/2.0/json" in closed.reason
    assert closed.url == "https://pypi.org/project/closed/"
