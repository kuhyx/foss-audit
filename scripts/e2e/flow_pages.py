"""The page-level steps of full_flow.py (detail panel, help, 404, page health), mixed into its Flow."""

from __future__ import annotations

# Text that means a value leaked into the page unformatted (R9).
LEAK = r"/\[object Object\]|\bundefined\b|\bNaN\b/"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class PageSteps:
    """Needs `p`, `notes`, `param` and `tab` from the Flow that mixes it in."""

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
        # Section headings are glyphs; their spoken name is the aria-label.
        has_alt = self.p.js("document.querySelector('.panel h3[aria-label=\"FOSS alternative\"]') !== null")
        check(bool(has_alt), "detail panel has no alternatives section")
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
