"""The all-items table as seen through the browser: reads and real clicks.

Everything the flow asserts on comes from the rendered DOM (or the text the
page put on the clipboard), never from re-implementing the UI's filter.
"""

from __future__ import annotations

import json
import time
from typing import Any

from cdp import Browser

# Runs before the app's own scripts: records every clipboard write (and still
# performs it, so the "Copied" status proves the real API succeeded).
BOOT = """
window.__copied = [];
window.__errors = [];
addEventListener('error', (e) => window.__errors.push(`error: ${e.message}`));
addEventListener('unhandledrejection', (e) => window.__errors.push(`rejection: ${e.reason}`));
const realError = console.error.bind(console);
console.error = (...args) => { window.__errors.push(`console: ${args.join(' ')}`); realError(...args); };
const realWrite = navigator.clipboard.writeText.bind(navigator.clipboard);
navigator.clipboard.writeText = (text) => { window.__copied.push(text); return realWrite(text); };
"""

# Shared DOM readers, installed once the app has rendered.
HELPERS = """
window.__fa = {
  num: (text) => Number(text.replaceAll(',', '')),
  shown() { return this.num(document.querySelector('.result-count strong').textContent); },
  count() {
    const el = document.querySelector('.selection-count');
    return el === null ? 0 : this.num(el.textContent.trim().split(' ')[0]);
  },
  rows() {
    return [...document.querySelectorAll('.tr.row[data-id]')].map((row) => ({
      id: row.dataset.id,
      index: Number(row.getAttribute('aria-rowindex')) - 2,
      checked: row.querySelector('input.check').checked,
    })).sort((a, b) => a.index - b.index);
  },
  header() {
    const box = document.querySelector('input[aria-label="Select all shown"]');
    return box.indeterminate ? 'some' : box.checked ? 'all' : 'none';
  },
  frame: () => new Promise((done) => requestAnimationFrame(() => setTimeout(done, 16))),
  async collect() {
    const scroller = document.querySelector('.table-scroll');
    const seen = new Map();
    scroller.scrollTop = 0;
    for (;;) {
      await this.frame();
      for (const row of this.rows()) seen.set(row.index, row);
      if (scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 1) break;
      scroller.scrollTop += scroller.clientHeight - 120;
    }
    scroller.scrollTop = 0;
    await this.frame();
    return [...seen.values()].sort((a, b) => a.index - b.index);
  },
  async reveal(index) {
    const scroller = document.querySelector('.table-scroll');
    scroller.scrollTop = Math.max(0, index * 40 - 80);
    await this.frame();
    const box = document.querySelector(`.tr.row[aria-rowindex="${index + 2}"] input.check`);
    if (box === null) return null;
    const r = box.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    return { x, y, hit: document.elementFromPoint(x, y) === box };
  },
  focusSearch() {
    const input = document.querySelector('input[aria-label^="Search"]');
    input.focus();
    input.select();
  },
  button: (prefix) => [...document.querySelectorAll('.selection-bar button')]
    .find((b) => b.textContent.startsWith(prefix)),
  sortButton: (column) => [...document.querySelectorAll('.th-button')]
    .find((b) => b.textContent.trim().startsWith(column)),
  center(el) {
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  },
  rect(selector) {
    const el = document.querySelector(selector);
    if (el === null) return null;
    const r = el.getBoundingClientRect();
    return { x: r.left, y: r.top, width: r.width, height: r.height };
  },
};
true
"""


class Page:
    """The foss-audit UI in one headless tab."""

    helpers = HELPERS

    def __init__(self, browser: Browser, url: str) -> None:
        self.b = browser
        origin = url.split("/?", maxsplit=1)[0].rstrip("/")
        browser.call(
            "Browser.grantPermissions",
            browser=True,
            origin=origin,
            permissions=["clipboardReadWrite", "clipboardSanitizedWrite"],
        )
        browser.call("Page.enable")
        browser.call("Emulation.setFocusEmulationEnabled", enabled=True)
        browser.call("Page.addScriptToEvaluateOnNewDocument", source=BOOT)
        browser.call("Page.navigate", url=url)
        browser.wait("document.querySelector('.table-scroll .tr.row') !== null", "the table to render", 25)
        browser.js(HELPERS)

    def js(self, expression: str) -> Any:
        return self.b.js(expression)

    def count(self) -> int:
        return int(self.js("__fa.count()"))

    def shown(self) -> int:
        return int(self.js("__fa.shown()"))

    def header(self) -> str:
        return str(self.js("__fa.header()"))

    def collect(self) -> list[dict[str, Any]]:
        """Every row of the current view, in displayed order (scrolls the virtual list)."""
        rows: list[dict[str, Any]] = self.js("__fa.collect()")
        if len(rows) != self.shown():
            raise AssertionError(f"collected {len(rows)} rows, the result count says {self.shown()}")
        return rows

    def search(self, text: str) -> None:
        """Type into the header search box and wait for the table to settle."""
        self.js("__fa.focusSearch()")
        self.b.call("Input.insertText", text=text)
        want = json.dumps(text)
        self.b.wait(f"new URLSearchParams(location.search).get('q') === {want}", f"q={text} in the URL")
        self._settle()
        self.js("document.activeElement.blur()")

    def sort_by(self, column: str) -> str:
        """Click a column's sort button; return the new `sort=` URL value."""
        before = self.js("new URLSearchParams(location.search).get('sort')")
        self.js(
            f"__fa.sortButton({json.dumps(column)}).scrollIntoView({{block: 'nearest', inline: 'nearest'}})"
        )
        spot = self.js(f"__fa.center(__fa.sortButton({json.dumps(column)}))")
        self.b.click(spot["x"], spot["y"])
        sort = str(
            self.b.wait(
                f"(() => {{ const s = new URLSearchParams(location.search).get('sort');"
                f" return s !== null && s !== {json.dumps(before)} && s; }})()",
                f"sort by {column} in the URL",
            )
        )
        self._settle()
        return sort

    def _settle(self) -> None:
        """Wait until the result count and first rows stop changing (deferred render)."""
        last, same = "", 0
        deadline = time.monotonic() + 10
        while same < 3 and time.monotonic() < deadline:
            snap = self.js("JSON.stringify([__fa.shown(), __fa.rows().slice(0, 5).map((r) => r.id)])")
            same = same + 1 if snap == last else 0
            last = snap
            time.sleep(0.05)

    def click_row(self, index: int, *, shift: bool = False) -> None:
        """Real click on the checkbox of displayed row `index` (0-based)."""
        spot = self.js(f"__fa.reveal({index})")
        if spot is None or not spot["hit"]:
            raise AssertionError(
                f"row {index + 1} checkbox is not clickable (covered or not mounted): {spot}"
            )
        self.b.click(spot["x"], spot["y"], shift=shift)
        self.b.wait(f"__fa.rows().some((r) => r.index === {index})", f"row {index + 1} to stay mounted")

    def click_header(self) -> None:
        box = self.js("__fa.rect('input[aria-label=\"Select all shown\"]')")
        self.b.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

    def copy(self, prefix: str) -> str:
        """Click the selection-bar button starting with `prefix`; return what it copied."""
        before = int(self.js("window.__copied.length"))
        finder = f"__fa.button({json.dumps(prefix)})"
        box = self.js(f"__fa.center({finder})")
        self.b.click(box["x"], box["y"])
        self.b.wait(f"window.__copied.length > {before}", f"'{prefix}' to write the clipboard")
        self.b.wait(f"{finder}.nextElementSibling.textContent === 'Copied'", f"'{prefix}' to report Copied")
        text = str(self.js(f"window.__copied[{before}]"))
        if self.js("navigator.clipboard.readText()") != text:
            raise AssertionError(f"system clipboard does not hold what '{prefix}' copied")
        return text

    def panel_open(self) -> bool:
        return bool(
            self.js(
                "document.querySelector('.panel') !== null"
                " && document.querySelector('.panel').getBoundingClientRect().width > 0"
                " || location.search.includes('sel=')"
            )
        )
