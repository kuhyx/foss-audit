"""E2E guard: no visible chrome words anywhere in the UI (textgate, kuhy 2026-11-08).

Usage: text_free.py <ui-url> <shot-dir>   (run by scripts/e2e_selection.sh)
Reuses cdp.py next to it.

Walks every rendered text node with a 2+ letter run on each screen (summary,
table + row cells, detail panel, selection bar, help sheet, wins, filters at
390 px, 404) and fails unless the text is scan content: a string value from
/api/scan, or a ", "/" · "-joined list of them. Exit 1 lists the offenders.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from collections.abc import Iterator
from typing import Any

from cdp import Browser

PROBE = """
(() => {
  const out = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const t = n.textContent.trim();
    if (!/[A-Za-z]{2,}/.test(t)) continue;
    const el = n.parentElement;
    // aria-hidden text still paints, so it is checked too; only unpainted or content nodes are skipped.
    if (el.closest('.sr-only, script, style, template, [hidden], code, time')) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (getComputedStyle(el).visibility === 'hidden') continue;
    out.push([el.tagName.toLowerCase() + '.' + [...el.classList].join('.'), t]);
  }
  // CSS generated text (::before/::after content) paints too.
  for (const el of document.body.querySelectorAll('*')) {
    for (const pseudo of ['::before', '::after']) {
      const c = getComputedStyle(el, pseudo).content;
      if (c && c !== 'none' && c !== 'normal' && /[A-Za-z]{2,}/.test(c)) {
        out.push([el.tagName.toLowerCase() + pseudo, c]);
      }
    }
  }
  for (const el of document.body.querySelectorAll('[placeholder], [title]')) {
    for (const a of ['placeholder', 'title']) {
      const v = el.getAttribute(a);
      if (v && /[A-Za-z]{2,}/.test(v)) out.push([el.tagName.toLowerCase() + '@' + a, v]);
    }
  }
  return out;
})()
"""

SPLIT = re.compile(r",\s*|\s+·\s+")
# A number with its unit symbol is content (R4), e.g. "8,480 ms".
UNIT = re.compile(r"^[\d,.]+\s?(ms|s|m|h|d)$")


def strings(value: Any) -> Iterator[str]:
    """Every string anywhere in a JSON value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for inner in value.values():
            yield from strings(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from strings(inner)


# keep.md rows: the 404 page links to the AgentReady docs pages by title (real text required there).
KEEP = {"FOSS audit", "How verdicts are decided", "Views and shortcuts", "What gets scanned"}


def is_content(text: str, content: set[str]) -> bool:
    """True when the text is scan content, a list of it, or a keep-list row."""
    if text in KEEP:
        return True
    if UNIT.match(text):
        return True
    return text in content or all(part in content for part in SPLIT.split(text) if part)


class Probe:
    """Collects offending text per screen."""

    def __init__(self, browser: Browser, content: set[str], shot_dir: str) -> None:
        self.b = browser
        self.content = content
        self.shot_dir = shot_dir
        self.bad: list[str] = []

    def check(self, name: str) -> None:
        """Record every non-content text node on the current screen and save a frame."""
        seen: set[tuple[str, str]] = set()
        for where, text in self.b.js(PROBE):
            if (where, text) in seen or is_content(text, self.content):
                continue
            seen.add((where, text))
            self.bad.append(f"{name}: {where}: {text[:90]}")
        self.b.screenshot(f"{self.shot_dir}/{name}-{time.time_ns()}.png")

    def load(self, url: str, ready: str) -> None:
        self.b.call("Page.navigate", url=url)
        self.b.wait(ready, f"{url} to render", timeout=15.0)
        time.sleep(0.5)


def run(probe: Probe, base: str) -> None:
    """Visit every screen."""
    b = probe.b
    probe.load(f"{base}/?view=summary", "document.querySelector('summary-view .tiles') !== null")
    probe.check("summary")
    probe.load(f"{base}/?view=table", "document.querySelector('.tr.row[data-id]') !== null")
    probe.check("table")
    b.js("document.querySelector('.tr.row[data-id]').click()")
    b.wait("document.querySelector('.panel') !== null", "the detail panel")
    time.sleep(1.0)
    probe.check("detail")
    b.js("document.querySelectorAll('.tr.row[data-id] input.check')[1].click()")
    b.js("document.querySelectorAll('.tr.row[data-id] input.check')[2].click()")
    b.wait("document.querySelector('.selection-bar') !== null", "the selection bar")
    probe.check("selection")
    b.key("?")
    b.wait("document.querySelector('dialog.scrim') !== null", "the help sheet")
    probe.check("help")
    probe.load(
        f"{base}/?view=wins", "document.querySelector('easy-wins .win, easy-wins .table-empty') !== null"
    )
    time.sleep(1.0)
    probe.check("wins")
    b.call("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
    probe.load(f"{base}/?view=table", "document.querySelector('.tr.row[data-id]') !== null")
    b.js("document.querySelector('.filter-toggle')?.click()")
    probe.check("table-390")
    b.call("Emulation.setDeviceMetricsOverride", width=1920, height=1080, deviceScaleFactor=1, mobile=False)
    probe.load(f"{base}/?view=table&q=zzzzqqqqxxxx", "document.querySelector('.table-empty') !== null")
    probe.check("empty")
    probe.load(f"{base}/nope", "document.querySelector('main') !== null")
    probe.check("404")


def main() -> int:
    base, shot_dir = sys.argv[1], sys.argv[2]
    with urllib.request.urlopen(f"{base}/api/scan", timeout=10) as response:  # noqa: S310 - loopback
        scan = json.load(response)
    content = set(strings(scan))
    browser = Browser()
    probe = Probe(browser, content, shot_dir)
    try:
        browser.call(
            "Emulation.setDeviceMetricsOverride", width=1920, height=1080, deviceScaleFactor=1, mobile=False
        )
        run(probe, base)
    finally:
        browser.close()
    sys.stdout.write("".join(f"{line}\n" for line in probe.bad))
    sys.stdout.write(f"{len(probe.bad)} visible chrome text node(s)\n")
    return 1 if probe.bad else 0


if __name__ == "__main__":
    sys.exit(main())
