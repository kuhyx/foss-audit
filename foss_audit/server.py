"""Local HTTP API for the UI: /api/scan, /api/scan/progress, /api/health.

Binds 127.0.0.1 only. /api/scan never waits for a scan: it serves the last
result (memory, saved in ~/.cache/foss-audit/scan.json) with `scanning` set
while a background rescan runs, or 202 when there is none yet. A rescan starts
at startup and on ?refresh=1|full unless one runs (cold ~30 s).

--scan-file PATH serves a saved `python -m foss_audit.scan` result instead:
loaded at startup (a bad file is a usage error), re-read on ?refresh=1, never
scanned live, never written to ~/.cache. The E2E flow relies on it.
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

from foss_audit.progress import ScanProgress
from foss_audit.scan import run_scan
from foss_audit.scan_store import load_saved, load_scan_file, save_atomic

DEFAULT_PORT = 5191
DEFAULT_STORE = Path.home() / ".cache/foss-audit/scan.json"
REFRESH_MODES = frozenset({"1", "full"})


class ScanCache:
    """The last result plus the background rescan's state; `store` None keeps memory only."""

    def __init__(self, scan_file: Path | None = None, store: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._result: dict[str, Any] | None = None
        self._scanning = False
        self._error: str | None = None
        self._scan_file = scan_file
        self._store = store
        self.progress = ScanProgress()

    def start(self) -> None:
        """Load the scan file (OSError/ValueError if bad), else the saved result and rescan."""
        with self._lock:
            if self._scan_file is not None:
                self._result = load_scan_file(self._scan_file)
                return
            self._result = load_saved(self._store) if self._store is not None else None
            self._start_rescan()

    def get(self, *, refresh: bool, full: bool = False) -> dict[str, Any] | None:
        """The result to serve now (None before the first); `refresh` starts a rescan."""
        with self._lock:
            if self._scan_file is not None:
                if refresh or self._result is None:
                    self._result = load_scan_file(self._scan_file)
            elif refresh:
                self._start_rescan(full)
            return None if self._result is None else {**self._result, "scanning": self._scanning}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            generated = None if self._result is None else self._result.get("generatedAt")
            return {
                "scanning": self._scanning,
                "generatedAt": generated,
                **self.progress.snapshot(),
                "error": self._error,
            }

    def _start_rescan(self, full: bool = False) -> None:
        if self._scanning:
            return
        self._scanning, self._error = True, None
        self.progress.begin(0)
        threading.Thread(target=self._rescan, args=(full,), daemon=True).start()

    def _rescan(self, full: bool) -> None:
        try:
            result = run_scan(progress=self.progress, full=full)
        except Exception as exc:  # noqa: BLE001 - a crashed rescan keeps the old result
            with self._lock:
                self._scanning, self._error = False, f"{type(exc).__name__}: {exc}"
            return
        self._save(result)
        with self._lock:
            self._result, self._scanning = result, False

    def _save(self, result: dict[str, Any]) -> None:
        if self._store is None:
            return
        try:
            save_atomic(self._store, result)
        except OSError as exc:
            sys.stderr.write(f"foss-audit: could not save {self._store}: {exc}\n")


CACHE = ScanCache()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path == "/api/health":
            self._send(HTTPStatus.OK, {"ok": True})
        elif url.path == "/api/scan":
            mode = parse_qs(url.query).get("refresh", ["0"])[0]
            body = CACHE.get(refresh=mode in REFRESH_MODES, full=mode == "full")
            if body is None:
                self._send(HTTPStatus.ACCEPTED, {"scanning": True})
            else:
                self._send(HTTPStatus.OK, body)
        elif url.path == "/api/scan/progress":
            self._send(HTTPStatus.OK, CACHE.snapshot())
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
    """Parse --port / --scan-file, start the cache and serve forever."""
    global CACHE  # noqa: PLW0603 - the handler reads the module-level cache
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--scan-file", type=Path, help="serve this saved scan instead of scanning live")
    args = parser.parse_args()
    CACHE = ScanCache(scan_file=args.scan_file, store=DEFAULT_STORE)
    try:
        CACHE.start()
    except (OSError, ValueError) as err:
        parser.error(f"--scan-file {args.scan_file}: {err}")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    sys.stdout.write(f"foss-audit API on http://127.0.0.1:{args.port}/api/scan\n")
    sys.stdout.flush()
    server.serve_forever()


if __name__ == "__main__":
    main()
