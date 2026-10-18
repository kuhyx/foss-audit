"""http_fetch: each host resolved once per process (single-flight), transient
resolver failures retried, every resolved address tried. No real DNS: the
resolver is faked and the only server is a loopback one."""

from __future__ import annotations

import http.server
import socket
import threading
import time
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from foss_audit import http_fetch

REAL_GETADDRINFO = socket.getaddrinfo
Lookup = Callable[..., Any]


@pytest.fixture(autouse=True)
def fresh_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_fetch, "_resolved", {})
    monkeypatch.setattr(http_fetch, "_host_locks", {})
    monkeypatch.setattr(http_fetch, "RESOLVE_BACKOFF_S", 0.0)


def fake_dns(monkeypatch: pytest.MonkeyPatch, answer: Lookup) -> list[str]:
    """Route lookups of *.test names to `answer`; numeric hosts resolve as usual."""
    calls: list[str] = []

    def getaddrinfo(host: str, port: int, *args: Any, **kwargs: Any) -> Any:
        if not host.endswith(".test"):
            return REAL_GETADDRINFO(host, port, *args, **kwargs)
        calls.append(host)
        return answer(host, port)

    monkeypatch.setattr(http_fetch.socket, "getaddrinfo", getaddrinfo)
    return calls


def loopback(port: int) -> Any:
    return REAL_GETADDRINFO("127.0.0.1", port, type=socket.SOCK_STREAM)


@pytest.fixture
def server() -> Iterator[int]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = f"{self.path} {self.headers['Host']}".encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, args=(0.05,), daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def test_parallel_fetches_resolve_each_host_once(monkeypatch: pytest.MonkeyPatch, server: int) -> None:
    def slow(host: str, port: int) -> Any:
        time.sleep(0.05)  # long enough that every worker arrives during the lookup
        return loopback(port)

    calls = fake_dns(monkeypatch, slow)
    start = threading.Barrier(6)
    got: list[bytes] = []

    def worker(n: int) -> None:
        start.wait()
        got.append(http_fetch.get(f"http://{'ab'[n % 2]}.test:{server}/p{n}", timeout=5))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(calls) == ["a.test", "b.test"]
    # The request still names the real host, so virtual hosting (and TLS SNI) is unchanged.
    assert f"/p0 a.test:{server}".encode() in got
    assert len(got) == 6


def test_a_transient_failure_is_retried(monkeypatch: pytest.MonkeyPatch, server: int) -> None:
    answers: list[Any] = [socket.gaierror(socket.EAI_AGAIN, "Temporary failure"), None]

    def flaky(host: str, port: int) -> Any:
        answer = answers.pop(0)
        if answer:
            raise answer
        return loopback(port)

    calls = fake_dns(monkeypatch, flaky)
    assert http_fetch.get(f"http://x.test:{server}/a", timeout=5).startswith(b"/a ")
    assert calls == ["x.test", "x.test"]


@pytest.mark.parametrize(
    ("errno", "lookups"), [(socket.EAI_AGAIN, http_fetch.RESOLVE_ATTEMPTS), (socket.EAI_NONAME, 1)]
)
def test_a_failed_lookup_is_kept_and_raised_again_without_asking(
    monkeypatch: pytest.MonkeyPatch, errno: int, lookups: int
) -> None:
    def failing(host: str, port: int) -> Any:
        raise socket.gaierror(errno, "no")

    calls = fake_dns(monkeypatch, failing)
    for _ in range(2):
        with pytest.raises(socket.gaierror) as caught:
            http_fetch.resolve("gone.test", 443)
        assert caught.value.errno == errno
    assert len(calls) == lookups


def test_every_resolved_address_is_tried_in_order(monkeypatch: pytest.MonkeyPatch, server: int) -> None:
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    dead = closed.getsockname()[1]
    closed.close()
    fake_dns(monkeypatch, lambda host, port: [*loopback(dead), *loopback(server)])
    assert http_fetch.get(f"http://two.test:{server}/b", timeout=5).startswith(b"/b ")


def test_when_no_address_connects_the_last_error_is_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    dead = closed.getsockname()[1]
    closed.close()
    fake_dns(monkeypatch, lambda host, port: loopback(dead))
    with pytest.raises(ConnectionRefusedError):
        http_fetch.connect(("one.test", dead), 5)
    fake_dns(monkeypatch, lambda host, port: [])
    with pytest.raises(OSError, match="no address for none.test"):
        http_fetch.connect(("none.test", 80), 5)


def test_https_goes_through_the_resolving_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[type] = []

    def do_open(self: object, conn: type, req: object, **kwargs: object) -> None:
        opened.append(conn)

    monkeypatch.setattr(urllib.request.AbstractHTTPHandler, "do_open", do_open)
    http_fetch.HTTPSHandler().https_open(urllib.request.Request("https://x.test/"))
    assert opened == [http_fetch.HTTPSConnection]
    assert http_fetch.HTTPSConnection("x.test")._create_connection is http_fetch.connect


@pytest.fixture
def hung() -> Iterator[threading.Event]:
    """Released at teardown, so a lookup thread left waiting on it can finish."""
    release = threading.Event()
    yield release
    release.set()


def test_a_hung_lookup_is_given_up_and_retried(
    monkeypatch: pytest.MonkeyPatch, hung: threading.Event, server: int
) -> None:
    monkeypatch.setattr(http_fetch, "LOOKUP_TIMEOUT_S", 0.05)
    answers = [hung, None]

    def first_hangs(host: str, port: int) -> Any:
        if answers.pop(0):
            hung.wait()
        return loopback(port)

    calls = fake_dns(monkeypatch, first_hangs)
    assert http_fetch.get(f"http://slow.test:{server}/c", timeout=5).startswith(b"/c ")
    assert calls == ["slow.test", "slow.test"]


def test_a_lookup_that_always_hangs_is_a_transient_failure(
    monkeypatch: pytest.MonkeyPatch, hung: threading.Event
) -> None:
    monkeypatch.setattr(http_fetch, "LOOKUP_TIMEOUT_S", 0.01)
    calls = fake_dns(monkeypatch, lambda host, port: hung.wait())
    with pytest.raises(socket.gaierror, match="lookup of dead.test timed out") as caught:
        http_fetch.resolve("dead.test", 443)
    assert (caught.value.errno, len(calls)) == (socket.EAI_AGAIN, http_fetch.RESOLVE_ATTEMPTS)


def test_an_error_other_than_a_lookup_failure_is_raised_as_is(monkeypatch: pytest.MonkeyPatch) -> None:
    def bad_name(host: str, port: int) -> Any:
        raise UnicodeError("label too long")

    fake_dns(monkeypatch, bad_name)
    with pytest.raises(UnicodeError, match="label too long"):
        http_fetch.resolve("bad.test", 443)


def test_answers_expire_so_a_long_running_server_looks_again(monkeypatch: pytest.MonkeyPatch) -> None:
    # The API server scans in-process: one transient failure must not poison a host for good.
    clock = [0.0]
    monkeypatch.setattr(http_fetch, "_now", lambda: clock[0])
    answers: list[Any] = [socket.gaierror(socket.EAI_NONAME, "no"), loopback(80)]

    def changing(host: str, port: int) -> Any:
        answer = answers[0] if len(answers) == 1 else answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    calls = fake_dns(monkeypatch, changing)
    with pytest.raises(socket.gaierror):
        http_fetch.resolve("h.test", 80)
    clock[0] = http_fetch.FAILED_TTL_S - 1
    with pytest.raises(socket.gaierror):
        http_fetch.resolve("h.test", 80)
    clock[0] = http_fetch.FAILED_TTL_S
    assert http_fetch.resolve("h.test", 80) == loopback(80)
    clock[0] += http_fetch.RESOLVED_TTL_S - 1
    http_fetch.resolve("h.test", 80)
    assert len(calls) == 2
    clock[0] += 1
    http_fetch.resolve("h.test", 80)
    assert len(calls) == 3
