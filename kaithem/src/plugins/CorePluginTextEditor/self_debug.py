# SPDX-License-Identifier: GPL-3.0-or-later
"""Attach a DAP debugger to Kaithem's own process.

This is an unsafe, last-resort tool for investigating a live system that is
misbehaving in a way logs cannot explain.  It is off unless ``self_debug`` is
enabled in the configuration file.

How it works
------------
``debugpy`` is started from *inside* the running process and told to *reverse
connect* to a proxy we control.  The proxy owns an exclusive loopback
listener on an ephemeral high port; only after we are sure we own that port
do we let pydevd connect out to it.  The proxy then verifies the single
accepted connection really is our own process (by asking pydevd for its pid)
and refuses anything else.

The proxy stands in for the debug adapter.  pydevd speaks the same DAP
messages, Content-Length framed, and expects the adapter to talk first, so
the proxy asks for ``pydevdSystemInfo`` on connect.  The browser editor,
meanwhile, speaks raw JSON DAP over a websocket (no framing); the proxy
bridges the two and:

* drops ``pause`` requests, which would suspend every thread;
* turns the client's ``launch`` into an ``attach`` with
  ``stopAllThreadsOnSuspend`` false, so a breakpoint suspends only the
  thread that hit it;
* buffers ``setBreakpoints`` until the attach happens (pydevd rejects
  breakpoints before then) and replays them afterwards.

On top of that, the websocket handler disables tracing on the main thread,
so breakpoints can never stop the event loop and wedge the whole server.

Caveats
-------
* ``debugpy.connect`` can only be called once per process, so the pydevd
  link is permanent: the debugger cannot be detached without restarting
  Kaithem, and tracing stays enabled process-wide.
* Enabling tracing slows the whole process down.  That is acceptable for a
  last-resort tool, which is why it is off by default.
"""

import asyncio
import json
import os
import socket
import threading
from typing import Any

import structlog

from kaithem.api import lifespan
from kaithem.src import config

logger = structlog.get_logger(__name__)

#: Our own requests to pydevd use sequence numbers far above what the browser
#: client uses, so an internal response can never be mistaken for one the
#: browser is waiting for.
_INTERNAL_SEQ = 1_000_000

#: Commands that would stop more than the thread they name, and are therefore
#: never forwarded to pydevd.  ``pause`` with a ``"*"`` thread id suspends
#: everything, and the real adapter rewrites a plain pause that way, so the
#: only safe thing to do is drop it.
_DROPPED_COMMANDS = {"pause"}

#: Breakpoint requests are held back until the attach has happened, because
#: pydevd refuses them before then.
_BREAKPOINT_COMMANDS = {"setBreakpoints", "setFunctionBreakpoints"}

_ACCEPT_TIMEOUT_S = 20.0
_VERIFY_TIMEOUT_S = 10.0


def enabled() -> bool:
    """Whether the self-debug tool is allowed by the configuration."""
    return bool(config.config.get("self_debug", False))


def _read_dap_message(f) -> bytes | None:
    """Read one Content-Length framed DAP message body from ``f``.

    Returns ``None`` at end of stream.  pydevd frames messages the same way
    as the DAP spec: header lines, a blank line, then exactly
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


def _write_dap_message(sock: socket.socket, obj: Any) -> None:
    """Send ``obj`` as one Content-Length framed DAP message."""
    body = json.dumps(obj).encode("utf-8")
    sock.sendall(b"Content-Length: %d\r\n\r\n" % len(body) + body)


def _synthetic_response(
    request: dict[str, Any], body: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build a DAP response for a request the proxy answers itself."""
    return {
        "seq": 0,
        "type": "response",
        "request_seq": request.get("seq"),
        "success": True,
        "command": request.get("command"),
        "body": body or {},
    }


class SelfDebugProxy:
    """Process-wide reverse-connect proxy for debugging Kaithem itself.

    A single instance lives for the whole process (see ``get_proxy``) because
    ``debugpy.connect`` can only be called once.  At most one browser is
    bridged at a time; a second connection is refused by the route.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._listener: socket.socket | None = None
        self._sock: socket.socket | None = None
        self._file = None
        self._port: int | None = None
        #: True once debugpy.connect has been called; it can never be undone.
        self._consumed = False
        self._reader: threading.Thread | None = None
        self._connect_error: BaseException | None = None
        #: Set while arm() waits for the pydevdSystemInfo response.
        self._verify_event = threading.Event()
        self._verify_pid: int | None = None
        #: Attach state, reset for each browser session.
        self._attached = False
        self._buffered: list[dict[str, Any]] = []
        #: Browser bridge (one client at a time).
        self._browser_loop: asyncio.AbstractEventLoop | None = None
        self._browser_queue: asyncio.Queue[str | None] | None = None
        self._browser_busy = False

    # -- arming --

    @property
    def armed(self) -> bool:
        with self._lock:
            return self._sock is not None

    @property
    def port(self) -> int | None:
        return self._port

    def arm(self) -> int:
        """Start the debugger and return the proxy's listening port.

        Blocking; call it off the event loop.  Binds and verifies an
        exclusive loopback listener *before* telling pydevd to connect, so we
        never point the debugger at a port we do not own.
        """
        try:
            import debugpy  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "debugpy is not installed; self-debug is unavailable"
            ) from e

        with self._lock:
            if self._sock is not None:
                return self._port  # type: ignore[return-value]
            if self._consumed:
                raise RuntimeError(
                    "debugpy can only be connected once per process; "
                    "restart Kaithem to re-arm the self-debugger"
                )
            self._consumed = True
            self._connect_error = None

        listener = self._bind_exclusive()
        port = listener.getsockname()[1]
        with self._lock:
            self._listener = listener
            self._port = port

        try:
            connector = threading.Thread(
                target=self._connect_pydevd,
                args=(port,),
                name="self-debug-connect",
                daemon=True,
            )
            connector.start()
            listener.settimeout(_ACCEPT_TIMEOUT_S)
            conn, addr = listener.accept()
        except Exception:
            self._close_listener()
            if self._connect_error is not None:
                raise RuntimeError(
                    f"self-debug failed to connect debugpy: "
                    f"{self._connect_error}"
                ) from self._connect_error
            raise

        # Exactly one connection is ever accepted; closing the listener makes
        # sure no other local process can reach the port.
        self._close_listener()

        if addr[0] != "127.0.0.1":
            conn.close()
            raise RuntimeError(f"unexpected self-debug peer {addr[0]!r}")

        with self._lock:
            self._sock = conn
            self._file = conn.makefile("rb")

        self._reader = threading.Thread(
            target=self._read_loop, name="self-debug-read", daemon=True
        )
        self._reader.start()

        pid = self._verify_connection()
        if pid != os.getpid():
            self.close()
            raise RuntimeError(
                f"self-debug peer pid {pid!r} is not ours ({os.getpid()})"
            )
        logger.warning(
            "Self-debug proxy armed on 127.0.0.1:%s; "
            "tracing is now process-wide until restart",
            port,
        )
        return port

    def _bind_exclusive(self) -> socket.socket:
        """Bind an exclusive loopback listener on an ephemeral high port.

        Port 0 lets the OS pick a free port and bind it to us atomically, so
        there is no window in which another process could take it.  We
        deliberately do not set SO_REUSEADDR (POSIX), so the port cannot be
        shared; on Windows SO_EXCLUSIVEADDRUSE is the equivalent.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()[:2]
        if host != "127.0.0.1" or not (1024 <= port < 65536):
            sock.close()
            raise RuntimeError(
                f"self-debug bound unexpected address {host}:{port}"
            )
        sock.listen(1)
        return sock

    def _connect_pydevd(self, port: int) -> None:
        """Reverse-connect pydevd to our listener (runs in its own thread).

        ``debugpy.connect`` blocks until the TCP connection is up, which is
        why this must not run on the thread that then calls ``accept``.
        """
        try:
            import debugpy

            debugpy.configure(subProcess=False)
            debugpy.connect(("127.0.0.1", port))
        except BaseException as e:  # pragma: no cover - env dependent
            self._connect_error = e
            logger.exception("Self-debug failed to connect debugpy")
            # Unblock the accept() in arm().
            self._close_listener()

    def _verify_connection(self) -> int | None:
        """Ask pydevd for its system info and return the reported pid.

        This proves the one connection we accepted really is the debugpy we
        started in this process, not some other local client.
        """
        self._verify_event.clear()
        self._verify_pid = None
        self._write(
            {
                "seq": _INTERNAL_SEQ,
                "type": "request",
                "command": "pydevdSystemInfo",
                "arguments": {},
            }
        )
        if not self._verify_event.wait(_VERIFY_TIMEOUT_S):
            raise RuntimeError(
                "self-debug: pydevd did not answer pydevdSystemInfo"
            )
        return self._verify_pid

    # -- pydevd side --

    def _write(self, obj: Any) -> None:
        sock = self._sock
        if sock is None:
            return
        try:
            with self._send_lock:
                _write_dap_message(sock, obj)
        except OSError:
            self._on_disconnected()

    def _read_loop(self) -> None:
        f = self._file
        if f is None:
            return
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
            if msg.get("request_seq") == _INTERNAL_SEQ:
                # Our own pydevdSystemInfo response, consumed during arm().
                self._verify_pid = (
                    (msg.get("body") or {}).get("process", {}).get("pid")
                )
                self._verify_event.set()
                continue
            self._to_browser(json.dumps(msg))
        self._on_disconnected()

    def _on_disconnected(self) -> None:
        with self._lock:
            self._sock = None
            self._file = None
        # Wake arm() if it is still waiting, and tell the browser to close.
        self._verify_event.set()
        self._to_browser(None)

    def _to_browser(self, text: str | None) -> None:
        loop = self._browser_loop
        queue = self._browser_queue
        if loop is None or queue is None:
            return
        try:
            loop.call_soon_threadsafe(queue.put_nowait, text)
        except Exception:
            pass

    # -- browser side --

    def acquire_browser(
        self,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue[str | None],
    ) -> bool:
        """Claim the single browser slot, or return False if taken."""
        with self._lock:
            if self._browser_busy:
                return False
            self._browser_busy = True
            self._browser_loop = loop
            self._browser_queue = queue
            self._attached = False
            self._buffered = []
            return True

    def release_browser(self) -> None:
        with self._lock:
            self._browser_busy = False
            self._browser_loop = None
            self._browser_queue = None
            self._attached = False
            self._buffered = []

    def from_browser(self, text: str) -> None:
        """Filter and forward one raw DAP message from the browser."""
        try:
            msg = json.loads(text)
        except ValueError:
            return
        if not isinstance(msg, dict) or msg.get("type") != "request":
            return
        command = msg.get("command")

        if command in _DROPPED_COMMANDS:
            # Answer the client so its request does not hang, but never
            # forward: this is the suspend-all we are here to prevent.
            self._to_browser(json.dumps(_synthetic_response(msg)))
            return

        if command == "launch":
            # We always attach to the already-running process.  Forcing
            # stopAllThreadsOnSuspend false means a breakpoint suspends only
            # the thread that hit it, never the whole server.
            self._write(
                {
                    "seq": msg.get("seq"),
                    "type": "request",
                    "command": "attach",
                    "arguments": {"stopAllThreadsOnSuspend": False},
                }
            )
            with self._lock:
                self._attached = True
                buffered = self._buffered
                self._buffered = []
            for req in buffered:
                self._write(req)
            return

        if command in _BREAKPOINT_COMMANDS and not self._attached:
            # pydevd rejects breakpoints before the attach; hold them and
            # answer the client immediately so its request does not time out.
            with self._lock:
                self._buffered.append(msg)
            self._to_browser(
                json.dumps(_synthetic_response(msg, {"breakpoints": []}))
            )
            return

        self._write(msg)

    # -- teardown --

    def close(self) -> None:
        self._close_listener()
        with self._lock:
            sock = self._sock
            self._sock = None
            self._file = None
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

    def _close_listener(self) -> None:
        with self._lock:
            listener = self._listener
            self._listener = None
        if listener is not None:
            try:
                listener.close()
            except Exception:
                pass


def _trace_this_thread_off() -> None:
    """Disable pydevd tracing for the thread this runs on."""
    try:
        import debugpy

        debugpy.trace_this_thread(False)
    except Exception:
        logger.exception("Failed to disable tracing on the main thread")


def disable_main_thread_tracing(loop: asyncio.AbstractEventLoop) -> None:
    """Make sure breakpoints can never stop the event loop's thread.

    Marks the main thread as one pydevd must not trace, and turns tracing off
    for it.  The websocket handler already runs on the main thread; the
    fallback keeps this correct even if that ever changes.
    """
    main = threading.main_thread()
    try:
        main.pydev_do_not_trace = True
    except Exception:
        pass
    if threading.current_thread() is main:
        _trace_this_thread_off()
    else:
        loop.call_soon_threadsafe(_trace_this_thread_off)


_proxy: SelfDebugProxy | None = None
_proxy_lock = threading.Lock()


def get_proxy() -> SelfDebugProxy:
    global _proxy
    with _proxy_lock:
        if _proxy is None:
            _proxy = SelfDebugProxy()
        return _proxy


def _shutdown() -> None:
    if _proxy is not None:
        _proxy.close()


lifespan.at_shutdown(_shutdown)
