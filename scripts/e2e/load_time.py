"""Page-load timing in a fresh headless Chromium per run.

Usage:
  load_time.py warm <ui-url> [runs]              median load -> table rows visible
  load_time.py cold <ui-url> <shot-dir> [secs..] screenshots of the loading page

`warm` expects the API to serve a saved scan at once and a `?view=table` URL
(the default view is the Summary, whose first paint is prerendered). Each run
is a new browser (empty HTTP cache), so the number includes fetching the
bundle. The clock is the page's own `performance.now()` (0 = navigation
start), read when a MutationObserver first sees a table row.

`cold` expects an API with no saved scan: it loads the page, then screenshots
and reads the page text at each given second (default 2 and 8).
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

from cdp import Browser

BOOT = """
window.__rowAt = null;
new MutationObserver((_, obs) => {
  if (document.querySelector('.tr.row[data-id]') !== null) {
    window.__rowAt = performance.now();
    obs.disconnect();
  }
}).observe(document, { childList: true, subtree: true });
"""

RESOURCES = """
JSON.stringify(performance.getEntriesByType('resource')
  .filter((e) => e.name.includes('/api/scan') && !e.name.includes('progress'))
  .map((e) => ({ url: e.name.replace(location.origin, ''), ms: Math.round(e.responseEnd - e.startTime),
    wire: e.transferSize, body: e.decodedBodySize })))
"""


def say(line: str) -> None:
    sys.stdout.write(f"{line}\n")


def warm_run(url: str) -> dict[str, object]:
    browser = Browser()
    try:
        browser.call("Page.enable")
        browser.call("Page.addScriptToEvaluateOnNewDocument", source=BOOT)
        browser.call("Page.navigate", url=url)
        browser.wait("window.__rowAt !== null", "a table row", 30)
        return {
            "tableMs": round(float(browser.js("window.__rowAt")), 1),
            "api": json.loads(browser.js(RESOURCES)),
        }
    finally:
        browser.close()


def warm(url: str, runs: int) -> None:
    results = [warm_run(url) for _ in range(runs)]
    times = sorted(float(str(r["tableMs"])) for r in results)
    for result in results:
        say(json.dumps(result))
    say(f"load->table ms: {times}  median={statistics.median(times)}")


def cold(url: str, shot_dir: Path, marks: list[float]) -> None:
    browser = Browser()
    try:
        browser.call("Page.enable")
        started = time.monotonic()
        browser.call("Page.navigate", url=url)
        for mark in marks:
            time.sleep(max(0.0, mark - (time.monotonic() - started)))
            text = browser.js("document.body.innerText.replaceAll('\\n', ' | ').slice(0, 300)")
            path = shot_dir / f"fa-cold-{mark:g}s.png"
            browser.screenshot(str(path))
            say(f"t={time.monotonic() - started:.1f}s {path}: {text}")
    finally:
        browser.close()


def main() -> int:
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "warm":
        warm(args[1], int(args[2]) if len(args) > 2 else 5)
    elif len(args) >= 3 and args[0] == "cold":
        cold(args[1], Path(args[2]), [float(a) for a in args[3:]] or [2.0, 8.0])
    else:
        say(__doc__ or "")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
