"""The one HTTP GET every scanner goes through, resolving each host once, not per request.

The cache scanners fetch hundreds of POMs and JSON documents from a handful of
hosts over thread pools. Left to urllib, every request calls getaddrinfo, and
under that parallel burst the system resolver (Tailscale MagicDNS here) answers
"Temporary failure in name resolution" after 20-25 s, where one lookup takes
0.02 s. So a host is looked up by one thread while the others wait for its
answer (single-flight); a lookup is given up after LOOKUP_TIMEOUT_S, and that or
a transient EAI_AGAIN is retried a couple of times with a short backoff. The
answer is kept RESOLVED_TTL_S, a failure FAILED_TTL_S: the API server scans
in-process, so a failure must not stick to a host for good. Connections then go
straight to the resolved addresses, tried in order; the request and TLS (SNI,
certificate check) still name the real host.

A socket timeout cannot bound getaddrinfo, which is why the bound is here and
the fetch timeout is unchanged.
"""

from __future__ import annotations

import http.client
import socket
import ssl
import threading
import time
import urllib.request
from typing import Any

RESOLVE_ATTEMPTS = 3
# Seconds before retry n (1-based) is RESOLVE_BACKOFF_S * n.
RESOLVE_BACKOFF_S = 0.3
LOOKUP_TIMEOUT_S = 3.0
RESOLVED_TTL_S = 600.0
FAILED_TTL_S = 30.0
AddrInfo = list[tuple[Any, ...]]
Answer = AddrInfo | socket.gaierror

_lock = threading.Lock()
# One lock per (host, port): the first thread resolves, the rest wait for it.
_host_locks: dict[tuple[str, int], threading.Lock] = {}
# (host, port) -> (expiry on the _now clock, answer).
_resolved: dict[tuple[str, int], tuple[float, Answer]] = {}


def _now() -> float:
    return time.monotonic()


def _bounded_getaddrinfo(host: str, port: int) -> AddrInfo:
    """getaddrinfo in a daemon thread, given up after LOOKUP_TIMEOUT_S as EAI_AGAIN.

    A daemon thread, not a pool: a hung lookup is left to finish on its own and
    never holds up interpreter exit.
    """
    box: list[AddrInfo | OSError | UnicodeError] = []

    def run() -> None:
        try:
            box.append(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
        except (OSError, UnicodeError) as exc:
            box.append(exc)

    thread = threading.Thread(target=run, name=f"resolve {host}", daemon=True)
    thread.start()
    thread.join(LOOKUP_TIMEOUT_S)
    if not box:
        raise socket.gaierror(socket.EAI_AGAIN, f"lookup of {host} timed out after {LOOKUP_TIMEOUT_S} s")
    if isinstance(box[0], Exception):
        raise box[0]
    return box[0]


def _lookup(host: str, port: int) -> Answer:
    """A bounded lookup, retrying only a transient failure; that failure is returned, not raised."""
    attempt = 1
    while True:
        try:
            return _bounded_getaddrinfo(host, port)
        except socket.gaierror as exc:
            if exc.errno != socket.EAI_AGAIN or attempt >= RESOLVE_ATTEMPTS:
                return exc
        time.sleep(RESOLVE_BACKOFF_S * attempt)
        attempt += 1


def resolve(host: str, port: int) -> AddrInfo:
    """Addresses of `host`, looked up once per TTL; a kept failure raises again."""
    key = (host, port)
    with _lock:
        host_lock = _host_locks.setdefault(key, threading.Lock())
    with host_lock:
        entry = _resolved.get(key)
        if entry is None or entry[0] <= _now():
            found = _lookup(host, port)
            ttl = FAILED_TTL_S if isinstance(found, socket.gaierror) else RESOLVED_TTL_S
            entry = _resolved[key] = (_now() + ttl, found)
    found = entry[1]
    if isinstance(found, socket.gaierror):
        raise socket.gaierror(found.errno, found.strerror)
    return found


def connect(
    address: tuple[str, int], timeout: float | None = None, source_address: tuple[str, int] | None = None
) -> socket.socket:
    """socket.create_connection over the memoised addresses: the first that connects wins."""
    host, port = address
    error: OSError = OSError(f"no address for {host}")
    for *_, sockaddr in resolve(host, port):
        try:
            return socket.create_connection(sockaddr[:2], timeout, source_address)
        except OSError as exc:
            error = exc
    raise error


class HTTPConnection(http.client.HTTPConnection):
    """An HTTP connection that dials through `connect`."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._create_connection = connect


class HTTPSConnection(http.client.HTTPSConnection):
    """An HTTPS connection that dials through `connect`; TLS still checks the host name."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._create_connection = connect


class HTTPHandler(urllib.request.HTTPHandler):
    """urllib's HTTP handler on `HTTPConnection`."""

    def http_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(HTTPConnection, req)


class HTTPSHandler(urllib.request.HTTPSHandler):
    """urllib's HTTPS handler on `HTTPSConnection` (redirects, proxies as before)."""

    def __init__(self) -> None:
        self.tls = ssl.create_default_context()
        super().__init__(context=self.tls)

    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(HTTPSConnection, req, context=self.tls)


_OPENER = urllib.request.build_opener(HTTPHandler, HTTPSHandler)


def get(url: str, timeout: float) -> bytes:
    """GET `url`'s body. Raises OSError (HTTPError included) on failure."""
    request = urllib.request.Request(url, headers={"User-Agent": "foss-audit"})
    with _OPENER.open(request, timeout=timeout) as response:
        data: bytes = response.read()
    return data
