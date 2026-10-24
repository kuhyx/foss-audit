"""E2E: multi-select in the all-items table, on a real scan, in real Chromium.

Usage: selection_flow.py <ui-url> <scan.json> <table.png> <bar.png> <fail.png>

Prints each numbered step before it runs, so on failure the last line names
it; exits 1 with a screenshot at <fail.png>. Started by e2e_selection.sh,
which owns the servers.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cdp import Browser
from page import Page

GMS = "com.google.android.gms"
NULL_TOKEN = re.compile(r"(^|\s)null(\s|$)", re.MULTILINE)
SECTION = re.compile(r"^#### .* \(`([^`]+)`\)", re.MULTILINE)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def prompt_ids(prompt: str, count: int, expected: set[str]) -> str:
    ids = SECTION.findall(prompt)
    check(len(ids) == count, f"prompt has {len(ids)} #### sections, the bar says {count}")
    check(set(ids) == expected, f"prompt ids differ from the selection: {sorted(set(ids) ^ expected)[:5]}")
    group = re.search(rf"^### Group \d+ of \d+: .*{re.escape(GMS)}.*$", prompt, re.MULTILINE)
    check(group is not None, f"no group heading names {GMS}")
    return group.group(0) if group else ""


def has_command(lines: list[str], command: str) -> bool:
    """Verbatim, or merged into one `<manager> a b c` line (remove-script.ts)."""
    if command in lines:
        return True
    prefix, _, arg = command.rpartition(" ")
    return any(line.startswith(f"{prefix} ") and arg in line[len(prefix) :].split() for line in lines)


def script_ok(script: str, ids: set[str], items: dict[str, dict[str, Any]]) -> None:
    check(script.startswith("#!/bin/bash\n"), f"script starts {script[:20]!r}")
    check(NULL_TOKEN.search(script) is None, "script contains a bare `null`")
    check(f"for {len(ids)} selected item" in script, "script header has the wrong item count")
    lines = script.splitlines()
    for item_id in sorted(ids):
        command = items[item_id]["removeCommand"]
        wanted = f"# no remove command: {item_id}" if command is None else command
        check(has_command(lines, wanted), f"script lacks {wanted!r} for {item_id}")


class Flow:
    p: Page  # set by open_table, always the first step

    def __init__(self, browser: Browser, url: str, items: dict[str, dict[str, Any]]) -> None:
        self.browser = browser
        self.url = url
        self.items = items
        self.picked: set[str] = set()
        self.firebase: list[str] = []
        self.notes: list[str] = []

    def haystack(self, item_id: str) -> str:
        return f"{self.items[item_id]['name']} {item_id}".lower()

    def expect_count(self, want: int, what: str) -> None:
        try:
            self.p.b.wait(f"__fa.count() === {want}", f"{what}: bar count {want}", timeout=3)
        except AssertionError as err:
            raise AssertionError(f"{err}; the bar shows {self.p.count()}") from None

    def expect_view_marks(self, rows: list[dict[str, Any]]) -> None:
        wrong = [r["index"] + 1 for r in rows if r["checked"] != (r["id"] in self.picked)]
        check(not wrong, f"checkbox state wrong on displayed rows {wrong[:10]}")
        hits = sum(r["id"] in self.picked for r in rows)
        state = "none" if hits == 0 else "all" if hits == len(rows) else "some"
        check(
            self.p.header() == state,
            f"header checkbox is {self.p.header()!r}, {hits}/{len(rows)} shown are selected",
        )

    def open_table(self) -> None:
        self.p = Page(self.browser, f"{self.url}/?view=table")
        self.notes.append(f"{self.p.shown()} items rendered")

    def select_all_google(self) -> None:
        self.p.search("com.google")
        rows = self.p.collect()
        check(len(rows) > 0, "com.google matches nothing")
        self.p.click_header()
        self.picked = {r["id"] for r in rows}
        self.expect_count(len(rows), "header checkbox")
        self.expect_view_marks(self.p.collect())
        self.notes.append(f"com.google: {len(rows)} rows, bar {self.p.count()}")

    def refilter_firebase(self) -> None:
        self.p.search("firebase")
        self.expect_count(len(self.picked), "after refilter")
        rows = self.p.collect()
        stray = [r["id"] for r in rows if "firebase" not in self.haystack(r["id"])]
        check(not stray, f"firebase shows rows without firebase in name or id: {stray[:5]}")
        want = {i for i in self.items if "firebase" in self.haystack(i)}
        self.firebase = [r["id"] for r in rows]
        check(set(self.firebase) == want, f"firebase shows {len(rows)} rows, {len(want)} contain it")
        self.expect_view_marks(rows)
        header, bar = self.p.header(), self.p.count()
        self.notes.append(f"firebase: {len(rows)} rows, all contain it, header {header}, bar {bar}")

    def add_one(self) -> None:
        rows = self.p.collect()
        target = next((r for r in rows if r["id"] not in self.picked), None)
        check(target is not None, "every firebase row is already selected: nothing to add")
        assert target is not None
        check("firebase" in self.haystack(target["id"]), f"picked a non-firebase row {target['id']}")
        self.p.click_row(target["index"])
        self.picked.add(target["id"])
        self.expect_count(len(self.picked), "one more")
        check(not self.p.panel_open(), "clicking a row checkbox opened the detail panel")
        self.notes.append(f"+1 ({target['id']}): bar {self.p.count()}, no panel")

    def typo_firbase(self) -> None:
        self.p.search("firbase")
        rows = self.p.collect()
        ids = [r["id"] for r in rows]
        head = ids[: len(self.firebase)]
        check(set(head) == set(self.firebase), f"firbase: the {len(head)} firebase rows are not ranked first")
        self.expect_count(len(self.picked), "after typo search")
        self.expect_view_marks(rows)
        extra = ids[len(head) :]
        self.notes.append(f"firbase: {len(rows)} rows, the {len(head)} firebase rows first, extra {extra}")

    def sorted_rows(self) -> tuple[str, list[dict[str, Any]]]:
        """Sort by name until the top rows are NOT in scan order, so a range
        taken from `items` instead of the displayed rows would pick other ids."""
        scan_pos = {item_id: pos for pos, item_id in enumerate(self.items)}
        for _ in range(2):  # ascending, then descending
            sort = self.p.sort_by("Name")
            rows = self.p.collect()
            top = [scan_pos[r["id"]] for r in rows[:7]]
            if top != sorted(top):
                return sort, rows
        raise AssertionError(
            "sorting by name leaves the top rows in scan order: the range test would be vacuous"
        )

    def shift_range(self) -> None:
        sort, rows = self.sorted_rows()
        check(len(rows) >= 6, f"need 6 rows for the range, view has {len(rows)}")
        before = len(self.picked)
        # A plain click toggles row 2 (it becomes the anchor); the shift-click
        # then turns on rows 2..6 whatever row 2's state was.
        self.p.click_row(1)
        self.p.click_row(5, shift=True)
        self.picked |= {r["id"] for r in rows[1:6]}
        self.expect_count(len(self.picked), "shift range 2..6")
        check(not self.p.panel_open(), "shift-clicking a checkbox opened the detail panel")
        self.expect_view_marks(self.p.collect())
        self.notes.append(f"sort={sort}, range 2..6: +{len(self.picked) - before}, bar {self.p.count()}")

    def layout(self, table_png: str, bar_png: str) -> None:
        geo = self.p.js(
            "({bar: __fa.rect('.selection-bar'), scroll: __fa.rect('.table-scroll'),"
            " head: __fa.rect('input[aria-label=\"Select all shown\"]'),"
            " row: __fa.rect('.tr.row input.check'), row3: __fa.rect('.tr.row[aria-rowindex=\"4\"]')})"
        )
        head_x = geo["head"]["x"] + geo["head"]["width"] / 2
        row_x = geo["row"]["x"] + geo["row"]["width"] / 2
        check(abs(head_x - row_x) <= 1.5, f"header checkbox x {head_x:.1f} vs row checkbox x {row_x:.1f}")
        bar_bottom = geo["bar"]["y"] + geo["bar"]["height"]
        check(
            bar_bottom <= geo["scroll"]["y"] + 0.5, f"selection bar (bottom {bar_bottom}) overlaps the table"
        )
        self.p.b.screenshot(table_png)
        top = geo["bar"]["y"] - 8
        bottom = geo["row3"]["y"] + geo["row3"]["height"] + 8
        self.p.b.screenshot(bar_png, {"x": 0, "y": top, "width": 1400, "height": bottom - top})
        table_top = geo["scroll"]["y"]
        self.notes.append(
            f"check x {head_x:.1f}/{row_x:.1f}; bar end {bar_bottom:.0f}, table {table_top:.0f}"
        )

    def copy_prompt(self) -> None:
        heading = prompt_ids(self.p.copy("Copy Claude prompt"), self.p.count(), self.picked)
        self.notes.append(f"prompt: {len(self.picked)} sections; {heading}")

    def copy_script(self) -> None:
        script_ok(self.p.copy("Copy remove commands"), self.picked, self.items)
        self.notes.append(f"script: #!/bin/bash, no null, {len(self.picked)} ids covered")


def say(line: str) -> None:
    sys.stdout.write(f"{line}\n")
    sys.stdout.flush()


def main() -> int:
    url, scan_path, table_png, bar_png, fail_png = sys.argv[1:6]
    items = {item["id"]: item for item in json.loads(Path(scan_path).read_text())["items"]}
    browser = Browser()
    flow = Flow(browser, url, items)
    steps: list[tuple[str, Callable[[], None]]] = [
        ("open the All items view", flow.open_table),
        ("filter com.google, header checkbox selects every shown row", flow.select_all_google),
        ("filter firebase: only rows with it in name/id, count kept", flow.refilter_firebase),
        ("select one more firebase row (no detail panel)", flow.add_one),
        ("typo firbase: firebase rows ranked first", flow.typo_firbase),
        ("sort by name, shift+click rows 2..6", flow.shift_range),
        ("layout + screenshots", lambda: flow.layout(table_png, bar_png)),
        ("Copy Claude prompt", flow.copy_prompt),
        ("Copy remove commands", flow.copy_script),
    ]
    try:
        for number, (title, step) in enumerate(steps, 1):
            say(f"step {number}/{len(steps)}: {title}")
            try:
                step()
            except (AssertionError, RuntimeError) as err:
                browser.screenshot(fail_png)
                say(f"FAIL step {number}/{len(steps)}: {err}\n  shot: {fail_png}")
                return 1
            say(f"  ok: {flow.notes[-1]}")
        return 0
    finally:
        browser.close()


if __name__ == "__main__":
    sys.exit(main())
