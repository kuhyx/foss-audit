"""Local HTTP API for the UI: GET /api/scan[?refresh=1], GET /api/health.

Binds 127.0.0.1 only; the package list never leaves the machine. The scan is
cached in memory and recomputed on ?refresh=1 (a full scan takes ~2 s).
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from foss_audit.scan import run_scan

DEFAULT_PORT = 5191


class ScanCache:
    """One cached scan; a lock keeps concurrent refreshes from scanning twice."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._result: dict[str, Any] | None = None

    def get(self, *, refresh: bool) -> dict[str, Any]:
        """Return the cached scan, rescanning when asked or when empty."""
        with self._lock:
            if refresh or self._result is None:
                self._result = run_scan()
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
    """Parse --port and serve forever."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    sys.stdout.write(f"foss-audit API on http://127.0.0.1:{args.port}/api/scan\n")
    sys.stdout.flush()
    server.serve_forever()


if __name__ == "__main__":
    main()
