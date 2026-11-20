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

* rewrites the client's ``pause`` into a pause of a single non-main
  thread, because a plain pause suspends *every* thread including the
  event loop, which would wedge the server;
* turns the client's ``launch`` into an ``attach`` with
  ``stopAllThreadsOnSuspend`` false, so a breakpoint suspends only the
  thread that hit it;
* buffers ``setBreakpoints`` until the attach happens (pydevd rejects
  breakpoints before then) and replays them afterwards.

On top of that, the websocket handler disables tracing on the main thread,
so breakpoints can never stop the event loop and wedge the whole server.

Lifecycle
---------
The pydevd link is not permanent.  ``detach`` ends the session (resuming
any suspended threads, disposing pydevd and restoring tracing) so a later
``arm`` can start a fresh one, and the websocket handler detaches when the
browser disconnects.  ``arm`` is idempotent while armed and retryable after
a failure, so a reload or a second visit just works.

We connect with ``wait_for_ready_to_run=False`` on purpose.  The default
(``True``) blocks inside pydevd's global settrace lock until the client
sends ``configurationDone``; a client that never does would hold that lock
for the life of the process and deadlock every later attach.

Caveats
-------
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

#: Breakpoint requests are held back until the attach has happened, because
#: pydevd refuses them before then.
_BREAKPOINT_COMMANDS = {"setBreakpoints", "setFunctionBreakpoints"}

_ACCEPT_TIMEOUT_S = 20.0
_VERIFY_TIMEOUT_S = 10.0

#: Longest we wait for pydevd to acknowledge a DAP ``disconnect`` (it
#: resumes any suspended threads first) before closing the socket anyway.
_DISCONNECT_WAIT_S = 0.5


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


def _load_pydevd():
    """Return the vendored pydevd module that debugpy ships with.

    Importing ``force_pydevd`` is what puts pydevd on ``sys.path`` and
    configures it for the DAP protocol; it is idempotent.
    """
    import debugpy._vendored.force_pydevd  # noqa: F401
    import pydevd

    return pydevd


class SelfDebugProxy:
    """Process-wide reverse-connect proxy for debugging Kaithem itself.

    A single instance lives for the whole process (see ``get_proxy``) and
    holds at most one pydevd link at a time; ``detach`` tears that link down
    so a later ``arm`` can start a new one.  At most one browser is bridged
    at a time; a second connection is refused by the route.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._listener: socket.socket | None = None
        self._sock: socket.socket | None = None
        self._file = None
        self._port: int | None = None
        #: True while an arm() is in flight, so a concurrent arm is refused.
        self._arming = False
        self._reader: threading.Thread | None = None
        self._connect_error: BaseException | None = None
        #: Set while arm() waits for the pydevdSystemInfo response.
        self._verify_event = threading.Event()
        self._verify_pid: int | None = None
        #: Sequence numbers for internal requests we make to pydevd whose
        #: responses the read loop must consume instead of forwarding, keyed
        #: by request seq.  Starts above the browser's range and the fixed
        #: system-info seq so nothing can collide.
        self._internal_seq = _INTERNAL_SEQ
        self._internal_handlers: dict[int, Any] = {}
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

        Blocking; call it off the event loop.  Idempotent while armed, and
        retryable after a failure or a ``detach``.  Binds and verifies an
        exclusive loopback listener *before* telling pydevd to connect, so we
        never point the debugger at a port we do not own.
        """
        with self._lock:
            if self._sock is not None:
                return self._port  # type: ignore[return-value]
            if self._arming:
                raise RuntimeError("self-debug is already being armed")
            self._arming = True
            self._connect_error = None
        try:
            return self._arm_impl()
        except BaseException:
            # Never leave a half-open link or a stuck pydevd behind: a later
            # arm() must be able to try again.
            self.detach()
            raise
        finally:
            with self._lock:
                self._arming = False

    def _arm_impl(self) -> int:
        try:
            _load_pydevd()
        except ImportError as e:
            raise RuntimeError(
                "debugpy is not installed; self-debug is unavailable"
            ) from e

        # The event loop runs on the main thread.  Mark it before pydevd
        # enables tracing everywhere, so a breakpoint can never suspend it.
        try:
            threading.main_thread().pydev_do_not_trace = True
        except Exception:
            logger.exception("self-debug: could not mark the main thread")

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

        # The listener's accept timeout would otherwise become an idle
        # timeout here and drop a link that is merely quiet (for example
        # while the editor page is still loading).
        conn.settimeout(None)

        with self._lock:
            self._sock = conn
            self._file = conn.makefile("rb")

        self._reader = threading.Thread(
            target=self._read_loop, name="self-debug-read", daemon=True
        )
        self._reader.start()

        pid = self._verify_connection()
        if pid != os.getpid():
            raise RuntimeError(
                f"self-debug peer pid {pid!r} is not ours ({os.getpid()})"
            )
        logger.warning(
            "Self-debug proxy armed on 127.0.0.1:%s; tracing is now "
            "process-wide until the debugger detaches",
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

        ``settrace`` blocks until the TCP connection is up, which is why this
        must not run on the thread that then calls ``accept``.

        ``wait_for_ready_to_run`` is False on purpose: the default blocks
        inside pydevd's global settrace lock until the client sends
        ``configurationDone``, so a client that never does would hold that
        lock for the life of the process and deadlock every later attach.
        """
        try:
            _load_pydevd().settrace(
                host="127.0.0.1",
                port=port,
                suspend=False,
                patch_multiprocessing=False,
                block_until_connected=True,
                wait_for_ready_to_run=False,
            )
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
            with self._lock:
                handler = self._internal_handlers.pop(
                    msg.get("request_seq"), None
                )
            if handler is not None:
                try:
                    handler(msg)
                except Exception:
                    logger.exception("self-debug internal response handler")
                continue
            self._to_browser(json.dumps(msg))
        self._on_disconnected()

    def _on_disconnected(self) -> None:
        with self._lock:
            self._sock = None
            self._file = None
            self._internal_handlers.clear()
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

        if command == "pause":
            # A pause the adapter carries out suspends *every* thread,
            # including the event loop, so it must never be forwarded as-is.
            # Acknowledge the client and pause a worker thread instead.
            self._to_browser(json.dumps(_synthetic_response(msg)))
            self._request_pause()
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

    def _request_pause(self) -> None:
        """Pause the program on a worker thread, never the event loop.

        pydevd has no "pause only this thread" request: a pause with a
        ``"*"`` thread id (which is what a plain pause becomes) suspends
        every thread, and suspending the main thread would re-enable its
        tracing and wedge the server.  So we ask for the thread list and
        pause the first thread that is not the main thread.
        """
        with self._lock:
            self._internal_seq += 1
            seq = self._internal_seq
            self._internal_handlers[seq] = self._on_threads_for_pause
        self._write(
            {
                "seq": seq,
                "type": "request",
                "command": "threads",
                "arguments": {},
            }
        )

    def _on_threads_for_pause(self, msg: dict[str, Any]) -> None:
        """Pause a non-main thread once we know the thread list."""
        threads = (msg.get("body") or {}).get("threads") or []
        main_name = threading.main_thread().name
        for thread in threads:
            if thread.get("name") != main_name:
                with self._lock:
                    self._internal_seq += 1
                    seq = self._internal_seq
                self._write(
                    {
                        "seq": seq,
                        "type": "request",
                        "command": "pause",
                        "arguments": {"threadId": thread.get("id")},
                    }
                )
                return
        logger.warning("self-debug: no non-main thread available to pause")

    # -- teardown --

    def detach(self) -> None:
        """End the pydevd session and reset state so we can arm again.

        Resumes any suspended threads (via a DAP ``disconnect``), then
        disposes pydevd and restores tracing, which clears the global
        debugger.  Safe to call when not armed, and blocking, so call it off
        the event loop.
        """
        with self._lock:
            sock = self._sock
            self._sock = None
            self._file = None
            self._internal_handlers.clear()
            self._attached = False
            self._buffered = []
            ack = threading.Event()
            seq = 0
            if sock is not None:
                # Register a handler for the disconnect response, so we can
                # wait for pydevd to resume suspended threads rather than
                # guessing with a fixed delay.
                self._internal_seq += 1
                seq = self._internal_seq
                self._internal_handlers[seq] = lambda _msg: ack.set()
        self._close_listener()

        if sock is not None:
            try:
                with self._send_lock:
                    _write_dap_message(
                        sock,
                        {
                            "seq": seq,
                            "type": "request",
                            "command": "disconnect",
                            "arguments": {},
                        },
                    )
            except OSError:
                ack.set()
            # pydevd resumes any suspended threads before it acknowledges, so
            # wait for that; fall back to the timeout if it never arrives.
            ack.wait(_DISCONNECT_WAIT_S)
            try:
                sock.close()
            except Exception:
                pass

        try:
            _load_pydevd().stoptrace()
        except Exception:
            logger.exception("Self-debug: failed to stop tracing")
        self._verify_event.set()

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
