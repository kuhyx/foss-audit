"""pip-cache remove commands: uv/poetry remove or a requirements edit, else the parents, else cache files."""

# ruff: noqa: F811  (the autouse no_network fixture is imported)
from __future__ import annotations

from pathlib import Path

import pytest

from foss_audit import cache_common, cache_remove, scan_cache_pip, scan_cache_pip_used
from foss_audit.cache_remove_pip import requirement_regex
from foss_audit.model import Item
from tests.pip_helpers import dist_info, meta, no_network, wheel  # noqa: F401

UV_CLEAN = "uv cache clean --cache-dir ~/.cache/uv"

SVC = """[project]
name = "svc"
dependencies = ["torch==2.0", "requests>=2"]
[project.optional-dependencies]
gpu = ["CuPy"]
[dependency-groups]
dev = ["pytest", {include-group = "x"}]
[build-system]
requires = ["hatchling>=1", "editables"]
"""

UV_LOCK = """version = 1
[[package]]
name = "svc"
source = { virtual = "." }
dependencies = [{ name = "torch" }, { name = "requests" }]
[package.optional-dependencies]
gpu = [{ name = "cupy" }]
[package.dev-dependencies]
dev = [{ name = "pytest" }]
[[package]]
name = "torch"
dependencies = [{ name = "nvidia-cudnn-cu13" }]
[[package]]
name = "nvidia-cudnn-cu13"
[[package]]
name = "requests"
dependencies = [{ name = "urllib3" }]
[[package]]
name = "urllib3"
[[package]]
name = "cupy"
[[package]]
name = "pytest"
[[package]]
name = "unreached"
[[package]]
name = "member"
source = { editable = "member" }
"""

POETRY = """[tool.poetry.dependencies]
python = "^3.12"
requests = "^2"
[tool.poetry.group.dev.dependencies]
black = "*"
[tool.poetry.dev-dependencies]
legacy-dev = "*"
"""

POETRY_LOCK = """[[package]]
name = "requests"
[package.dependencies]
urllib3 = ">=1"
[[package]]
name = "urllib3"
[[package]]
name = "black"
"""


def write(path: Path, data: str | bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data)
    return path


def body(pip: Path, digest: str, name: str, *headers: str) -> None:
    """A pip http-v2 entry: the response body plus its header file."""
    folder = pip / "http-v2/a/b/c/d/e"
    write(folder / f"{digest}.body", meta(name, "1.0", "License-Expression: MIT", *headers))
    write(folder / digest, "headers")


@pytest.fixture
def items(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Item]:
    src, pip, uv = tmp_path / "src", tmp_path / ".cache/pip", tmp_path / ".cache/uv"
    for module, name, value in (
        (scan_cache_pip, "PIP_CACHE", pip),
        (scan_cache_pip, "UV_CACHE", uv),
        (scan_cache_pip, "SRC", src),
        (cache_remove, "HOME", tmp_path),
    ):
        monkeypatch.setattr(module, name, value)
    real_files, real_of = cache_common.project_files, cache_common.project_of
    monkeypatch.setattr(scan_cache_pip_used, "project_files", lambda names: real_files(names, src))
    monkeypatch.setattr(scan_cache_pip_used, "project_of", lambda path: real_of(path, src))
    write(src / "svc/pyproject.toml", SVC)
    write(src / "svc/uv.lock", UV_LOCK)
    write(src / "svc/member/pyproject.toml", '[project]\nname = "member"\ndependencies = ["urllib3"]\n')
    write(src / "legacy/requirements.txt", "Torch>=2  # gpu\n-e git+https://x/y#egg=y\nnumpy\n")
    write(src / "legacy/requirements-dev.txt", "pytest\n")
    write(src / "legacy/.venv/lib/pyproject.toml", '[project]\ndependencies = ["graperoot"]\n')
    write(src / "poet/pyproject.toml", POETRY)
    write(src / "poet/poetry.lock", POETRY_LOCK)
    write(src / "bad/pyproject.toml", "[project\n")
    # torch's cached metadata pulls in filelock, which no project file names.
    body(pip, "01", "torch", "Requires-Dist: nvidia-cudnn-cu13", "Requires-Dist: filelock")
    for digest, name in enumerate(["nvidia_cudnn_cu13", "requests", "urllib3", "filelock", "graperoot"], 2):
        body(pip, f"0{digest}", name)
    body(pip, "07", "pytest")
    body(pip, "08", "hatchling")
    body(pip, "09", "unreached")
    body(pip, "10", "legacy-dev")
    body(pip, "11", "svc")  # the project itself, cached by some other install
    write(pip / "http/a/b/c/d/e/old", "not a cache entry")
    whl = pip / "wheels/a/b/c/h/built-1.0-py3-none-any.whl"
    write(whl, wheel({"built-1.0.dist-info/METADATA": meta("built", "1.0", "License: MIT")}))
    dist_info(uv / "archive-v0/id1", "cupy", meta("cupy", "1.0", "License: MIT"))
    env = uv / "archive-v0/envid/lib/python3.14/site-packages"
    dist_info(env, "envonly", meta("envonly", "1.0", "License: MIT"))
    dist_info(env, "other", meta("other", "1.0", "License: MIT"))
    return {i.name: i for i in scan_cache_pip.scan_pip_cache()}


def http(*digests: str) -> str:
    return " ".join(
        f"~/.cache/pip/http-v2/a/b/c/d/e/{d} ~/.cache/pip/http-v2/a/b/c/d/e/{d}.body" for d in digests
    )


def test_requirement_regex_matches_any_spelling() -> None:
    assert requirement_regex("nvidia-cudnn-cu13") == (
        r"^[[:space:]]*nvidia[-_.]+cudnn[-_.]+cu13[[:space:]]*([[:space:]<>=!~;@,[]|$)"
    )


def test_direct_dependency_per_section(items: dict[str, Item]) -> None:
    assert items["cupy"].removeCommand == f"(cd ~/src/svc && uv remove --optional gpu cupy); {UV_CLEAN} cupy"
    pytest_cmd = items["pytest"].removeCommand
    assert "(cd ~/src/svc && uv remove --group dev pytest)" in str(pytest_cmd)
    assert (
        "(cd ~/src/legacy && sed -i -E -e '/^[[:space:]]*pytest[[:space:]]*([[:space:]<>=!~;@,[]|$)/Id' "
        "requirements-dev.txt)" in str(pytest_cmd)
    )
    assert items["hatchling"].removeCommand == (
        '(cd ~/src/svc && sed -i -E \'/^requires[[:space:]]*=/,/]/s/"hatchling([[:space:]<>=!~;@,[][^"]*)?"'
        ",?[[:space:]]*//I' pyproject.toml); rm -rf " + http("08")
    )


def test_transitive_from_a_lock_and_from_requirements(items: dict[str, Item]) -> None:
    cudnn = items["nvidia-cudnn-cu13"]
    assert cudnn.requiredBy == ["~/src/svc"]
    assert cudnn.removeCommand == (
        "(cd ~/src/legacy && sed -i -E -e '/^[[:space:]]*torch[[:space:]]*([[:space:]<>=!~;@,[]|$)/Id' "
        "requirements.txt); (cd ~/src/svc && uv remove torch); rm -rf " + http("02")
    )
    assert (
        cudnn.removeVia
        == "~/src/legacy via torch → nvidia-cudnn-cu13; ~/src/svc via torch → nvidia-cudnn-cu13"
    )


def test_unlisted_but_reachable_is_transitive(items: dict[str, Item]) -> None:
    filelock = items["filelock"]
    assert filelock.requiredBy == []
    assert filelock.removeVia == "~/src/legacy via torch → filelock"


def test_several_projects_and_tools(items: dict[str, Item]) -> None:
    assert items["urllib3"].removeCommand == (
        "(cd ~/src/poet && poetry remove requests); (cd ~/src/svc && uv remove requests); "
        "(cd ~/src/svc/member && uv remove urllib3); rm -rf " + http("04")
    )


def test_unreached_lock_entry_is_relocked(items: dict[str, Item]) -> None:
    assert items["unreached"].removeCommand == "(cd ~/src/svc && uv lock); rm -rf " + http("09")
    assert items["svc"].removeCommand == "rm -rf " + http("11")


def test_legacy_poetry_dev_dependencies(items: dict[str, Item]) -> None:
    assert items[
        "legacy-dev"
    ].removeCommand == "(cd ~/src/poet && poetry remove --group dev legacy-dev); rm -rf " + http("10")


def test_stale_entries_by_cache(items: dict[str, Item]) -> None:
    assert items["graperoot"].removeCommand == "rm -rf " + http("06")
    assert items["graperoot"].removeVia.startswith("stale: ")
    assert items["built"].removeCommand == "rm -rf ~/.cache/pip/wheels/a/b/c/h/built-1.0-py3-none-any.whl"
    env = items["envonly"]
    assert env.removeCommand == "rm -rf ~/.cache/uv/archive-v0/envid"
    assert env.removeVia.endswith("deletes the whole cached uv environment envid (uv rebuilds it on demand)")
    assert all(i.removeCommand for i in items.values())
