"""Headless Chromium over the DevTools protocol, standard library only.

Modelled on ~/.claude/scripts/cdp_shot.py, but with no websocket-client
dependency (the repo's Python is stdlib-only and freshness-gated) and with a
throwaway profile plus `--remote-debugging-port=0`, so parallel runs and a
live browser never collide. One browser websocket carries every command;
page commands go through a flattened target session.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# The real binaries: /usr/bin/chromium is Arch's launcher (it reads
# chromium-flags.conf, which loads the Claude extension) and
# /usr/local/bin/{chromium,google-chrome-stable} run a hosts-blocker installer.
CANDIDATES = ("/usr/lib/chromium/chromium", "/opt/google/chrome/chrome")
WINDOW = (1400, 1000)


class WebSocket:
    """Just enough RFC 6455 for CDP: masked text out, unmasked frames in."""

    def __init__(self, url: str, timeout: float) -> None:
        parts = urlparse(url)
        self.sock = socket.create_connection((parts.hostname or "127.0.0.1", parts.port or 80), timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            f"GET {parts.path} HTTP/1.1\r\nHost: {parts.netloc}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode()
        )
        head = b""
        while b"\r\n\r\n" not in head:
            head += self._read(1)
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"websocket handshake refused: {head[:80]!r}")

    def _read(self, size: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                raise ConnectionError("devtools websocket closed")
            data += chunk
        return bytes(data)

    def _frame(self, opcode: int, payload: bytes) -> None:
        size = len(payload)
        if size < 126:
            header = struct.pack("!BB", 0x80 | opcode, 0x80 | size)
        elif size < 1 << 16:
            header = struct.pack("!BBH", 0x80 | opcode, 0x80 | 126, size)
        else:
            header = struct.pack("!BBQ", 0x80 | opcode, 0x80 | 127, size)
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        self.sock.sendall(header + mask + masked)

    def send(self, text: str) -> None:
        self._frame(0x1, text.encode())

    def recv(self) -> str:
        message = b""
        while True:
            first, second = self._read(2)
            size = second & 0x7F
            if size == 126:
                (size,) = struct.unpack("!H", self._read(2))
            elif size == 127:
                (size,) = struct.unpack("!Q", self._read(8))
            payload = self._read(size)
            opcode = first & 0x0F
            if opcode == 0x8:
                raise ConnectionError("devtools websocket closed by the browser")
            if opcode == 0x9:
                self._frame(0xA, payload)
                continue
            message += payload
            if first & 0x80:
                return message.decode()


class Browser:
    """A throwaway headless Chromium with one page attached."""

    def __init__(self, timeout: float = 20.0) -> None:
        binary = os.environ.get("CHROME_BIN") or next((c for c in CANDIDATES if Path(c).exists()), "")
        if not binary:
            raise RuntimeError(f"no Chromium/Chrome binary at {CANDIDATES}; set CHROME_BIN")
        self.profile = Path(tempfile.mkdtemp(prefix="fa-e2e-chrome-"))
        self.proc = subprocess.Popen(
            [
                binary,
                "--headless=new",
                "--remote-debugging-port=0",
                f"--user-data-dir={self.profile}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                f"--window-size={WINDOW[0]},{WINDOW[1]}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.ws = WebSocket(self._browser_ws(timeout), timeout)
        self.next_id = 0
        self.session = ""
        target = self.call("Target.createTarget", url="about:blank")["targetId"]
        self.session = self.call("Target.attachToTarget", targetId=target, flatten=True)["sessionId"]

    def _browser_ws(self, timeout: float) -> str:
        port_file = self.profile / "DevToolsActivePort"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if port_file.exists() and len(lines := port_file.read_text().split()) == 2:
                return f"ws://127.0.0.1:{lines[0]}{lines[1]}"
            time.sleep(0.05)
        raise RuntimeError("Chromium never opened its DevTools port")

    def call(self, method: str, *, browser: bool = False, **params: Any) -> dict[str, Any]:
        """Send one command (to the page unless `browser`) and wait for its reply."""
        self.next_id += 1
        message: dict[str, Any] = {"id": self.next_id, "method": method, "params": params}
        if self.session and not browser:
            message["sessionId"] = self.session
        self.ws.send(json.dumps(message))
        while True:
            reply = json.loads(self.ws.recv())
            if reply.get("id") == self.next_id:
                if "error" in reply:
                    raise RuntimeError(f"{method}: {reply['error']}")
                result: dict[str, Any] = reply.get("result", {})
                return result

    def js(self, expression: str) -> Any:
        """Evaluate in the page (promises awaited) and return the value."""
        result = self.call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in result:
            raise RuntimeError(f"page error in {expression[:60]!r}: {result['exceptionDetails'].get('text')}")
        return result.get("result", {}).get("value")

    def wait(self, expression: str, what: str, timeout: float = 10.0) -> Any:
        """Poll `expression` until truthy; raise naming `what` on timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = self.js(expression)
            if value:
                return value
            time.sleep(0.05)
        raise AssertionError(f"timed out after {timeout:.0f} s waiting for {what}")

    def click(self, x: float, y: float, *, shift: bool = False) -> None:
        """A real mouse click (press + release) at viewport coordinates."""
        for kind in ("mousePressed", "mouseReleased"):
            self.call(
                "Input.dispatchMouseEvent",
                type=kind,
                x=x,
                y=y,
                button="left",
                clickCount=1,
                modifiers=8 if shift else 0,
            )

    def screenshot(self, path: str, clip: dict[str, float] | None = None) -> None:
        params: dict[str, Any] = {"format": "png"}
        if clip is not None:
            params["clip"] = {**clip, "scale": 1}
        Path(path).write_bytes(base64.b64decode(self.call("Page.captureScreenshot", **params)["data"]))

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)
