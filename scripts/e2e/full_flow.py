"""E2E: the whole UI on a real scan in real Chromium (load, sort, filter,
URL state, summary, easy wins, detail and help dialogs, 404, page health).

Usage: full_flow.py <ui-url> <scan.json> <fail.png>

Prints each numbered step before it runs; exits 1 with a screenshot at
<fail.png> on the first failure. Started by e2e_selection.sh, which owns the
servers. Nothing on the clipboard is ever run.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cdp import Browser
from page import Page

# Text that means a value leaked into the page unformatted (R9).
LEAK = r"/\[object Object\]|\bundefined\b|\bNaN\b/"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class Flow:
    p: Page  # set by open_table, always the first step

    def __init__(self, browser: Browser, url: str, items: list[dict[str, Any]]) -> None:
        self.browser = browser
        self.url = url
        self.items = items
        self.total = len(items)
        self.notes: list[str] = []

    def param(self, name: str) -> str | None:
        value = self.p.js(f"new URLSearchParams(location.search).get({json.dumps(name)})")
        return None if value is None else str(value)

    def top_ids(self, n: int = 12) -> list[str]:
        return list(self.p.js(f"__fa.rows().slice(0, {n}).map((r) => r.id)"))

    def open_table(self) -> None:
        self.p = Page(self.browser, f"{self.url}/?view=table")
        shown = self.p.shown()
        check(shown == self.total, f"table shows {shown} items, the scan has {self.total}")
        self.notes.append(f"{shown} items rendered")

    def custom_elements(self) -> None:
        defined = self.p.js(
            "['items-table', 'filter-bar', 'selection-bar'].map((n) => !!customElements.get(n))"
        )
        check(all(defined), f"custom elements items-table/filter-bar/selection-bar defined: {defined}")
        react = self.p.js(
            "!!document.querySelector('#root')?._reactRootContainer"
            " || '__reactContainer' in (document.querySelector('#root') ?? {})"
            " || Object.keys(document.querySelector('#root') ?? {}).some((k) => k.startsWith('__react'))"
        )
        check(not react, "a React root is mounted")
        self.notes.append("items-table, filter-bar, selection-bar defined; no React root")

    def sort_every_column(self) -> None:
        names = list(
            self.p.js(
                "[...document.querySelectorAll('.th-button')]"
                ".map((b) => b.textContent.replace(/[▲▼↑↓]/g, '').trim())"
            )
        )
        check(len(names) >= 3, f"only {len(names)} sortable headers")
        changed = []
        for name in names:
            first = self.p.sort_by(name)
            asc = self.top_ids()
            second = self.p.sort_by(name)
            desc = self.top_ids()
            check(
                first.lstrip("-") == second.lstrip("-") and first != second,
                f"{name}: sort {first} then {second}, not a toggle",
            )
            check(asc != desc, f"{name}: asc and desc show the same top rows")
            changed.append(f"{name}={first}/{second}")
        self.notes.append(f"{len(names)} columns toggle: {', '.join(changed)}")

    def search_and_filter(self) -> None:
        nonfree = {i["id"] for i in self.items if i["verdict"] == "nonfree"}
        chip = (
            "[...document.querySelectorAll('.chips[aria-label=\"Verdict\"] .chip')]"
            ".find((c) => c.textContent.startsWith('Non-free'))"
        )
        self.p.js(f"{chip}.click()")
        self.p.b.wait("new URLSearchParams(location.search).has('v')", "a verdict filter in the URL")
        self.p.b.wait(f"__fa.shown() === {len(nonfree)}", f"Non-free to show {len(nonfree)} rows")
        ids = {r["id"] for r in self.p.collect()}
        check(
            ids == nonfree, f"Non-free filter: {len(ids - nonfree)} wrong rows, {len(nonfree - ids)} missing"
        )
        self.p.js(f"{chip}.click()")
        self.p.b.wait(f"__fa.shown() === {self.total}", "un-ticking the chip to restore every row")
        self.p.search("firefox")
        hits = self.p.shown()
        check(0 < hits < self.total, f"search firefox shows {hits} of {self.total}")
        rows = self.p.collect()
        check(len(rows) == hits, f"{len(rows)} rows rendered, count says {hits}")
        self.p.js(f"{chip}.click()")
        self.p.b.wait("new URLSearchParams(location.search).has('v')", "a verdict filter in the URL")
        time.sleep(0.2)
        narrowed = self.p.shown()
        expect = sum(1 for r in rows if r["id"] in nonfree)
        check(narrowed == expect, f"firefox + Non-free shows {narrowed}, expected {expect}")
        self.reload_keeps_state()
        reset = (
            "[...document.querySelectorAll('.filters button')].find((b) => b.textContent.includes('Reset'))"
        )
        self.p.js(f"{reset}.click()")
        self.p.b.wait(f"__fa.shown() === {self.total}", "reset to restore every row")
        self.notes.append(
            f"Non-free {len(nonfree)} exact, firefox {hits}, +Non-free {narrowed}, "
            f"reload kept it, reset -> {self.total}"
        )

    def reload_keeps_state(self) -> None:
        before = self.p.js("location.search")
        shown = self.p.shown()
        # The marker dies with the old document, so a slow (dev-mode) reload
        # cannot satisfy the wait before the new page exists.
        self.p.js("window.__beforeReload = true")
        self.p.b.call("Page.reload")
        self.p.b.wait(
            "window.__beforeReload === undefined"
            " && (document.querySelector('.table-scroll .tr.row') !== null"
            " || document.querySelector('.table-empty') !== null)",
            "the table after reload",
            25,
        )
        self.p.b.js(self.p.helpers)
        check(self.p.js("location.search") == before, "reload changed the URL")
        self.p.b.wait(f"__fa.shown() === {shown}", f"reload to show the same {shown} rows")
        check(
            self.p.js("document.querySelector('input[aria-label^=\"Search\"]').value") == "firefox",
            "search box lost its text on reload",
        )

    def tab(self, view: str) -> None:
        index = {"summary": 0, "table": 1, "wins": 2}[view]
        self.p.js(f"document.querySelectorAll('.tabs .tab')[{index}].click()")
        self.p.b.wait(
            f"(new URLSearchParams(location.search).get('view') ?? 'summary') === '{view}'",
            f"view={view} in the URL",
        )

    def summary_and_wins(self) -> None:
        self.tab("summary")
        self.p.b.wait("document.querySelector('.summary .tiles') !== null", "summary tiles")
        tiles = self.p.js(
            "[...document.querySelectorAll('.tiles .tile-value')]"
            ".reduce((s, t) => s + __fa.num(t.textContent), 0)"
        )
        check(tiles == self.total, f"verdict tiles sum to {tiles}, the scan has {self.total}")
        svg = self.p.js("document.querySelectorAll('.chart svg').length")
        check(svg >= 1, "the source chart is not an SVG")
        self.tab("wins")
        self.p.b.wait("document.querySelector('.wins .win, .table-empty') !== null", "easy wins")
        cards = self.p.js("document.querySelectorAll('.wins .win').length")
        badge = self.p.js("__fa.num(document.querySelectorAll('.tabs .tab-count')[2].textContent)")
        check(cards == badge, f"{cards} easy-win cards, the tab says {badge}")
        self.p.js("history.back()")
        self.p.b.wait(
            "(new URLSearchParams(location.search).get('view') ?? 'summary') === 'summary'",
            "Back to return to summary",
        )
        self.notes.append(f"tiles sum {tiles}, chart svg x{svg}, {cards} wins, Back -> summary")

    def detail_and_help(self) -> None:
        self.tab("table")
        self.p.b.wait("document.querySelector('.table-scroll .tr.row') !== null", "the table")
        row_id = self.p.js("document.querySelector('.tr.row[data-id]').dataset.id")
        spot = self.p.js("__fa.center(document.querySelector('.tr.row[data-id] .td:nth-child(3)'))")
        self.p.b.click(spot["x"], spot["y"])
        self.p.b.wait(
            "(() => { const p = document.querySelector('.panel');"
            " return p !== null && p.getBoundingClientRect().width > 0; })()",
            "the detail panel",
        )
        check(self.param("sel") == row_id, f"sel={self.param('sel')}, clicked {row_id}")
        text = str(self.p.js("document.querySelector('.panel').innerText"))
        check("Alternative" in text or "alternative" in text, "detail panel has no alternatives section")
        self.p.b.key("Escape")
        self.p.b.wait(
            "(() => { const p = document.querySelector('.panel');"
            " return p === null || p.getBoundingClientRect().width === 0; })()",
            "Esc to close the panel",
        )
        focus = self.p.js(
            "document.activeElement?.closest('.tr.row')?.dataset.id ?? document.activeElement?.className"
        )
        check(focus == row_id, f"focus after Esc is on {focus!r}, not row {row_id}")
        self.p.b.key("?")
        self.p.b.wait(
            "(() => { const h = document.querySelector('.help');"
            " return h !== null && h.getBoundingClientRect().width > 0; })()",
            "? to open help",
        )
        self.p.b.key("Escape")
        self.p.b.wait(
            "(() => { const h = document.querySelector('.help');"
            " return h === null || h.getBoundingClientRect().width === 0; })()",
            "Esc to close help",
        )
        self.notes.append(f"detail {row_id} opened/closed, focus back on row, help opened/closed")

    def not_found(self) -> None:
        got = self.p.js("fetch('/nope').then(async (r) => [r.status, await r.text()])")
        check(got[0] == 404, f"/nope answered {got[0]}")
        check("<style" in got[1] or "stylesheet" in got[1], "the 404 page has no styles")
        # Match the element tag, not the bare name: dev mode inlines the app CSS
        # (which mentions items-table) into every page, the 404 included.
        check('id="root"' not in got[1] and "<items-table" not in got[1], "/nope served the app shell")
        self.notes.append("/nope: 404 with the styled not-found page")

    def health(self) -> None:
        errors = self.p.js("window.__errors")
        check(not errors, f"console errors / exceptions: {errors[:5]}")
        leaks = self.p.js(f"document.body.innerText.match({LEAK})?.[0] ?? null")
        check(leaks is None, f"page text contains {leaks!r}")
        self.notes.append("no console errors, no [object Object]/undefined/NaN")


def say(line: str) -> None:
    sys.stdout.write(f"{line}\n")
    sys.stdout.flush()


def main() -> int:
    url, scan_path, fail_png = sys.argv[1:4]
    items = json.loads(Path(scan_path).read_text())["items"]
    browser = Browser()
    flow = Flow(browser, url, items)
    steps: list[tuple[str, Callable[[], None]]] = [
        ("open the All items view", flow.open_table),
        ("custom elements, no React", flow.custom_elements),
        ("every column sorts asc then desc", flow.sort_every_column),
        ("search + verdict filter, reload keeps it, reset restores", flow.search_and_filter),
        ("summary tiles + SVG chart, easy wins, Back", flow.summary_and_wins),
        ("detail panel + help dialog, Esc, focus", flow.detail_and_help),
        ("/nope is a real 404", flow.not_found),
        ("no console errors or leaked values", flow.health),
    ]
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
            say(f"  ok: {flow.notes[-1]}")
        return 1 if failed else 0
    finally:
        browser.close()


if __name__ == "__main__":
    sys.exit(main())
