"""Step runner shared by the e2e flows: numbered steps, a screenshot on failure.

Kept apart from full_flow.py so that file stays under the 250-line cap.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from cdp import Browser


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def say(line: str) -> None:
    sys.stdout.write(f"{line}\n")
    sys.stdout.flush()


def run_steps(
    browser: Browser,
    steps: list[tuple[str, Callable[[], None]]],
    notes: list[str],
    fail_png: str,
) -> int:
    """Run each step in order; 1 on the first failure (all with --keep-going)."""
    failed = 0
    try:
        for number, (title, step) in enumerate(steps, 1):
            say(f"step {number}/{len(steps)}: {title}")
            try:
                step()
            except (AssertionError, RuntimeError) as err:
                browser.screenshot(fail_png)
                say(f"FAIL step {number}/{len(steps)}: {err}\n  shot: {fail_png}")
                failed += 1
                if "--keep-going" in sys.argv:
                    continue
                return 1
            say(f"  ok: {notes[-1]}")
        return 1 if failed else 0
    finally:
        browser.close()
