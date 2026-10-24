"""Local HTTP API for the UI: GET /api/scan[?refresh=1], GET /api/health.

Binds 127.0.0.1 only; the package list never leaves the machine. The scan is
cached in memory and recomputed on ?refresh=1 (a full scan takes ~45 s).

With --scan-file PATH it serves a saved `python -m foss_audit.scan` result
instead: loaded once at startup (a bad file is a usage error, not a 500),
re-read from disk on ?refresh=1, never a live scan. This is what lets the E2E
flow (scripts/e2e_selection.sh) start the app in a second, not a minute.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from foss_audit.scan import run_scan

DEFAULT_PORT = 5191


def load_scan_file(path: Path) -> dict[str, Any]:
    """A saved scan result; ValueError unless it is a JSON object with `items`."""
    result = json.loads(path.read_text())
    if not isinstance(result, dict) or "items" not in result:
        raise ValueError("not a foss_audit.scan result (no top-level `items`)")
    return result


class ScanCache:
    """One cached scan; a lock keeps concurrent refreshes from scanning twice.

    `scan_file` replaces the live scan with that saved result.
    """

    def __init__(self, scan_file: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._result: dict[str, Any] | None = None
        self._scan_file = scan_file

    def get(self, *, refresh: bool) -> dict[str, Any]:
        """Return the cached scan, rescanning (or re-reading) when asked or when empty."""
        with self._lock:
            if refresh or self._result is None:
                # run_scan is looked up per call so tests can monkeypatch it.
                self._result = run_scan() if self._scan_file is None else load_scan_file(self._scan_file)
            return self._result


CACHE = ScanCache()


class Handler(BaseHTTPRequestHandler):
    """Routes the two GET endpoints; everything else is 404."""

    def do_GET(self) -> None:
        """Serve /api/scan and /api/health."""
        url = urlparse(self.path)
        if url.path == "/api/health":
            self._send(HTTPStatus.OK, {"ok": True})
        elif url.path == "/api/scan":
            refresh = parse_qs(url.query).get("refresh", ["0"])[0] == "1"
            self._send(HTTPStatus.OK, CACHE.get(refresh=refresh))
        else:
            self._send(HTTPStatus.NOT_FOUND, {"error": f"no route {url.path}"})

    def _send(self, status: HTTPStatus, body: dict[str, Any]) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        """Quiet per-request logging; run.sh prints its own status lines."""


def main() -> None:
    """Parse --port / --scan-file and serve forever."""
    global CACHE  # noqa: PLW0603 - the handler reads the module-level cache
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--scan-file", type=Path, help="serve this saved scan instead of scanning live")
    args = parser.parse_args()
    if args.scan_file is not None:
        CACHE = ScanCache(scan_file=args.scan_file)
        try:
            CACHE.get(refresh=False)
        except (OSError, ValueError) as err:
            parser.error(f"--scan-file {args.scan_file}: {err}")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    sys.stdout.write(f"foss-audit API on http://127.0.0.1:{args.port}/api/scan\n")
    sys.stdout.flush()
    server.serve_forever()


if __name__ == "__main__":
    main()
