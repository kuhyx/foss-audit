"""E2E: the table view at the five R1 viewports (C15).

Usage: viewports.py <ui-url> <shot-dir>

For each size: emulate it, load `?view=table`, wait for rows, screenshot to
<shot-dir>/vp-<w>x<h>.png and assert every primary control (header, tabs,
search, first table row) is on screen, not covered (elementFromPoint at its
centre is inside it) and above the fold. Exits 1 listing every failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

from cdp import Browser

SIZES = [(3840, 2160), (2560, 1440), (1920, 1080), (1366, 768), (390, 844)]
CONTROLS = {
    "header": "header",
    "tabs": ".tabs",
    "search": 'input[aria-label^="Search"]',
    "first row": ".table-scroll .tr.row",
}
PROBE = """
((sel) => {
  const el = document.querySelector(sel);
  if (el === null) return 'missing';
  const r = el.getBoundingClientRect();
  if (r.width === 0 || r.height === 0) return 'zero size';
  if (r.bottom > innerHeight + 0.5)
    return `below the fold (bottom ${Math.round(r.bottom)} > ${innerHeight})`;
  if (r.right > innerWidth + 0.5 && sel !== '.table-scroll .tr.row')
    return `off the right edge (${Math.round(r.right)} > ${innerWidth})`;
  const x = Math.min(r.left + Math.min(r.width, innerWidth) / 2, innerWidth - 1);
  const hit = document.elementFromPoint(x, r.top + r.height / 2);
  if (hit === null || !(el.contains(hit) || hit.contains(el)))
    return `covered by ${hit?.tagName}.${hit?.className}`;
  return 'ok';
})
"""


def main() -> int:
    url, shot_dir = sys.argv[1], Path(sys.argv[2])
    shot_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    browser = Browser()
    try:
        for width, height in SIZES:
            browser.call(
                "Emulation.setDeviceMetricsOverride",
                width=width,
                height=height,
                deviceScaleFactor=1,
                mobile=width < 600,
            )
            browser.call("Page.navigate", url=f"{url.rstrip('/')}/?view=table")
            shot = str(shot_dir / f"vp-{width}x{height}.png")
            try:
                browser.wait("document.querySelector('.table-scroll .tr.row') !== null", "table rows", 25)
            except AssertionError as err:
                browser.screenshot(shot)
                failures.append(f"{width}x{height}: {err}")
                continue
            browser.screenshot(shot)
            for name, selector in CONTROLS.items():
                verdict = browser.js(f"{PROBE}({selector!r})")
                if verdict != "ok":
                    failures.append(f"{width}x{height} {name}: {verdict}")
            hscroll = browser.js("document.documentElement.scrollWidth > innerWidth")
            if hscroll:
                failures.append(f"{width}x{height}: page scrolls horizontally")
            sys.stdout.write(f"{width}x{height}: checked\n")
    finally:
        browser.close()
    for line in failures:
        sys.stdout.write(f"FAIL {line}\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
