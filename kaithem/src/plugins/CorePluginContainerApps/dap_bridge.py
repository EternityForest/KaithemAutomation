# SPDX-License-Identifier: GPL-3.0-or-later
"""Bridge a DAP debug adapter's stdio to a websocket.

A script command step marked ``dap = true`` is a debug entry point.  Its
``command`` is the complete debugger invocation (adapter and all) and is
run verbatim in the container.  This bridge proxies the adapter's
Content-Length framed DAP messages to and from a raw-JSON websocket that
the text editor speaks.

The text editor sends an empty ``launch`` request.  If the step supplies a
free-form ``launch`` table, the bridge merges those arguments into the
browser's launch request so the debugger knows what to debug (for example
``program``/``args`` for ``debugpy.adapter``).  The bridge also answers a
repeated ``initialize`` itself, since debugpy refuses to be initialized
twice.

The adapter is not killed when the browser detaches; it stays running so
another browser can attach.  Only ``stop()`` sends ``disconnect`` and
kills the adapter.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import subprocess
import threading
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

#: Longest we wait for the adapter to acknowledge a DAP ``disconnect``.
_DISCONNECT_WAIT_S = 0.5

def _read_dap_message(f) -> bytes | None:
    """Read one Content-Length framed DAP message body from ``f``.

    Returns ``None`` at end of stream.  debugpy frames messages the same
    way as the DAP spec: header lines, a blank line, then exactly
    ``Content-Length`` bytes of UTF-8 JSON.
    """
    length = None
    while True:
        line = f.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        key, _, value = line.partition(b":")
        if key.strip().lower() == b"content-length":
            try:
                length = int(value.strip())
            except ValueError:
                return None
    if not length:
        return None
    body = f.read(length)
    if len(body) < length:
        return None
    return body


def _write_dap_message(stream, obj: Any) -> None:
    """Send ``obj`` as one Content-Length framed DAP message."""
    body = json.dumps(obj).encode("utf-8")
    stream.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
    stream.flush()


def _synthetic_response(
    request: dict[str, Any], body: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build a DAP response for a request the bridge answers itself."""
    return {
        "seq": 0,
        "type": "response",
        "request_seq": request.get("seq"),
        "success": True,
        "command": request.get("command"),
        "body": body or {},
    }


class DapBridge:
    """Proxy one debug adapter's stdio to a raw-JSON websocket.

    The adapter is started on first use and stays running across browser
    detaches.  At most one browser is bridged at a time; attaching a new
    one silently detaches the previous one.
    """

    def __init__(
        self,
        session: Any,
        command: list[str],
        env: dict[str, str],
        workdir: str = "/app",
        launch: dict[str, Any] | None = None,
    ):
        self.session = session
        self.command = command
        self.env = env
        self.workdir = workdir
        self.launch = launch
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None
        self._reader: threading.Thread | None = None
        self._browser_loop: asyncio.AbstractEventLoop | None = None
        self._browser_queue: asyncio.Queue[str | None] | None = None
        self._browser_busy = False
        self._initialized = False
        self._launched = False
        self._configuration_done = False
        self._pending_configuration_done: dict[str, Any] | None = None

    # -- lifecycle --

    def start(self) -> None:
        """Start the debug adapter subprocess."""
        with self._lock:
            if self._proc is not None:
                return
            self._initialized = False
            self._launched = False
            self._configuration_done = False
            self._pending_configuration_done = None
            proc = self.session.exec(
                list(self.command),
                env=self.env,
                workdir=self.workdir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                tty=False,
            )
            self._proc = proc
            self._reader = threading.Thread(
                target=self._read_loop,
                name="capp-dap-read",
                daemon=True,
            )
            self._reader.start()

    def stop(self) -> None:
        """Send ``disconnect`` and kill the adapter subprocess."""
        with self._lock:
            proc = self._proc
            self._proc = None
            self._initialized = False
            self._launched = False
            self._configuration_done = False
            self._pending_configuration_done = None
        if proc is None:
            return
        # Try a graceful disconnect first.
        try:
            _write_dap_message(
                proc.stdin,
                {
                    "seq": 1,
                    "type": "request",
                    "command": "disconnect",
                    "arguments": {},
                },
            )
        except Exception:
            pass
        try:
            proc.wait(timeout=_DISCONNECT_WAIT_S)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        self._to_browser(None)

    def detach(self) -> None:
        """Release the browser slot without killing the adapter.

        The adapter stays running so another browser can attach.  The
        ``initialize``/``launch`` state belongs to the adapter, not the
        browser, so it is deliberately left alone here.
        """
        with self._lock:
            self._browser_busy = False
            self._browser_loop = None
            self._browser_queue = None

    def is_running(self) -> bool:
        """Whether the adapter subprocess is still alive."""
        with self._lock:
            return self._proc is not None

    # -- adapter side --

    def _read_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        f = proc.stdout
        while True:
            try:
                body = _read_dap_message(f)
            except Exception:
                break
            if body is None:
                break
            try:
                msg = json.loads(body)
            except ValueError:
                continue
            self._to_browser(json.dumps(msg))
        try:
            proc.wait(timeout=1.0)
        except Exception:
            pass
        self._on_disconnected()

    def _on_disconnected(self) -> None:
        with self._lock:
            self._proc = None
        self._to_browser(None)

    def _write(self, obj: Any) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            return
        try:
            with self._send_lock:
                _write_dap_message(proc.stdin, obj)
        except OSError:
            self._on_disconnected()

    # -- browser side --

    def acquire_browser(
        self,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue[str | None],
    ) -> None:
        """Claim the browser slot, detaching any previous browser."""
        with self._lock:
            self._browser_busy = True
            self._browser_loop = loop
            self._browser_queue = queue

    def release_browser(self) -> None:
        self.detach()

    def from_browser(self, text: str) -> None:
        """Filter and forward one raw DAP message from the browser."""
        try:
            msg = json.loads(text)
        except ValueError:
            return
        if not isinstance(msg, dict) or msg.get("type") != "request":
            return
        command = msg.get("command")

        if command == "initialize":
            if self._initialized:
                # debugpy refuses a second initialize; answer it ourselves.
                self._to_browser(json.dumps(_synthetic_response(msg)))
                # Re-attach: the adapter already sent its "initialized"
                # event to the previous browser.  Replay it so this one
                # proceeds to configurationDone.
                self._to_browser(
                    json.dumps(
                        {
                            "seq": 0,
                            "type": "event",
                            "event": "initialized",
                            "body": {},
                        }
                    )
                )
                return
            self._initialized = True
            self._write(msg)
            return

        if command == "configurationDone":
            if self._configuration_done:
                # Re-attach: the adapter already finished configuration.
                self._to_browser(json.dumps(_synthetic_response(msg)))
                return
            if not self._launched:
                # The adapter needs a launch before configurationDone.
                # Buffer it until the browser sends launch.
                self._pending_configuration_done = msg
                return
            self._configuration_done = True
            self._write(msg)
            return

        if command == "launch":
            if self._launched:
                self._to_browser(json.dumps(_synthetic_response(msg)))
                return
            self._launched = True
            # The text editor sends an empty launch.  If the step supplies
            # a free-form launch table, merge it in so the debugger knows
            # what to debug; browser-supplied values win.
            forwarded = dict(msg)
            arguments = dict(msg.get("arguments") or {})
            if self.launch:
                merged = dict(self.launch)
                merged.update(arguments)
                merged.setdefault("cwd", self.workdir)
                arguments = merged
            forwarded["arguments"] = arguments
            self._write(forwarded)
            pending = self._pending_configuration_done
            if pending is not None:
                self._pending_configuration_done = None
                self._configuration_done = True
                self._write(pending)
            return

        self._write(msg)

    def _to_browser(self, text: str | None) -> None:
        loop = self._browser_loop
        queue = self._browser_queue
        if loop is None or queue is None:
            return
        try:
            loop.call_soon_threadsafe(queue.put_nowait, text)
        except Exception:
            pass


# -- Access id registry -------------------------------------------------

_bridges: dict[str, DapBridge] = {}
_bridges_lock = threading.Lock()


def register(bridge: DapBridge) -> str:
    """Register a bridge and return its access id."""
    bridge_id = secrets.token_urlsafe(16)
    with _bridges_lock:
        _bridges[bridge_id] = bridge
    return bridge_id


def get(bridge_id: str) -> DapBridge | None:
    with _bridges_lock:
        return _bridges.get(bridge_id)


def unregister(bridge_id: str) -> None:
    with _bridges_lock:
        _bridges.pop(bridge_id, None)
