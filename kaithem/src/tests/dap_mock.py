# SPDX-License-Identifier: GPL-3.0-or-later
"""A minimal mock Debug Adapter Protocol server for the test suite.

The text editor's debugger sidebar talks DAP over a websocket, one raw
JSON message per frame (no Content-Length framing).  This mock speaks
just enough of the protocol to exercise that sidebar end to end: the
initialize handshake, setBreakpoints, launch/continue/step, per-thread
stack traces, a virtual source reachable only through the ``source``
request, a frame in a real file outside the workspace, and a console
``evaluate``.

The fake program it pretends to run is a loop that calls a function which
increments a global and copies it into a local.  Every continue or step
advances that loop by one iteration and stops again, so the sidebar can
show a changing counter.

The mock runs its own asyncio loop in a background thread, deliberately
independent of the Kaithem event loop, so it can sit beside the real
server without being part of it.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from dataclasses import dataclass
from typing import Any

import websockets
from websockets.asyncio.server import Server, ServerConnection
from websockets.exceptions import ConnectionClosed

#: Name of the virtual source file the mock serves through ``source``.
PSEUDOCODE_NAME = "pseudocode.dap"

#: The ``sourceReference`` that identifies the virtual file.
PSEUDOCODE_SOURCE_REFERENCE = 1

#: The virtual pseudocode.  Line 5 is inside ``increment`` and line 11 is
#: the call site in ``main``, which is where the mock's frames point.
PSEUDOCODE = (
    "\n".join(
        [
            "# pseudocode.dap - a virtual file served only by the DAP mock",
            "global counter = 0",
            "",
            "function increment(x):",
            "    local y = x + 1",
            "    counter = y",
            "    return y",
            "",
            "function main():",
            "    while true:",
            "        increment(counter)",
            "        print(counter)",
            "",
            "main()",
        ]
    )
    + "\n"
)

#: A real file the mock writes and serves a frame from, so the editor has
#: to open a file that is outside its workspace, read-only.
DISK_SOURCE_PATH = "/dev/shm/kaithem_test_env/dap_disk_source.txt"

#: Contents of ``DISK_SOURCE_PATH``.  Line 3 is the frame it reports.
DISK_SOURCE = (
    "\n".join(
        [
            "# A real file outside the editor workspace.",
            "function worker():",
            "    increment(counter)",
        ]
    )
    + "\n"
)

#: Text in ``DISK_SOURCE`` that a test can assert was loaded.
DISK_SOURCE_MARKER = "A real file outside the editor workspace."

#: The virtual source, as a DAP ``source`` object.
_VIRTUAL_SOURCE: dict[str, Any] = {
    "name": PSEUDOCODE_NAME,
    "sourceReference": PSEUDOCODE_SOURCE_REFERENCE,
}

#: The on-disk source, as a DAP ``source`` object.
_DISK_SOURCE: dict[str, Any] = {
    "name": os.path.basename(DISK_SOURCE_PATH),
    "path": DISK_SOURCE_PATH,
}

#: The port the mock listens on by default.  The Playwright container
#: shares the host network namespace but not ``/dev/shm``, so a test
#: cannot read a dynamically chosen port from a file the server wrote.
#: Both sides agree on this fixed port instead, overridable with
#: ``KAITHEM_TEST_DAP_PORT``.
DEFAULT_DAP_MOCK_PORT = 8003


@dataclass
class _Thread:
    """A thread the mock's fake program is made of."""

    id: int
    name: str


#: The threads reported by the ``threads`` request.  Two threads make the
#: sidebar's "call stack per stopped thread" rendering observable.
THREADS: list[_Thread] = [
    _Thread(1, "main"),
    _Thread(2, "worker"),
]


def _frames_for(thread_id: int) -> list[dict[str, Any]]:
    """The call stack the mock reports for one thread."""
    if thread_id == 2:
        return [
            {
                "id": 21,
                "name": "increment",
                "line": 5,
                "column": 1,
                "source": _VIRTUAL_SOURCE,
            },
            {
                "id": 22,
                "name": "worker",
                "line": 3,
                "column": 1,
                "source": _DISK_SOURCE,
            },
        ]
    return [
        {
            "id": 11,
            "name": "increment",
            "line": 5,
            "column": 1,
            "source": _VIRTUAL_SOURCE,
        },
        {
            "id": 12,
            "name": "main",
            "line": 11,
            "column": 1,
            "source": _VIRTUAL_SOURCE,
        },
    ]


def _parse(raw: str | bytes) -> dict[str, Any] | None:
    """Parse one websocket frame into a DAP message, or None."""
    try:
        message = json.loads(raw)
    except ValueError:
        return None
    return message if isinstance(message, dict) else None


class _Session:
    """One connected debug client.

    The mock only ever runs one fake program, so a session just tracks
    the sequence number and the loop counter that ``evaluate`` reports.
    """

    def __init__(self, websocket: ServerConnection) -> None:
        self._ws = websocket
        self._seq = 0
        self._counter = 0

    async def run(self) -> None:
        async for raw in self._ws:
            message = _parse(raw)
            if message is None or message.get("type") != "request":
                continue
            await self._on_request(message)

    async def _send(self, message: dict[str, Any]) -> None:
        await self._ws.send(json.dumps(message))

    async def _respond(
        self, request: dict[str, Any], body: dict[str, Any] | None = None
    ) -> None:
        self._seq += 1
        await self._send(
            {
                "seq": self._seq,
                "type": "response",
                "request_seq": request["seq"],
                "success": True,
                "command": request["command"],
                "body": body or {},
            }
        )

    async def _error(self, request: dict[str, Any], message: str) -> None:
        self._seq += 1
        await self._send(
            {
                "seq": self._seq,
                "type": "response",
                "request_seq": request["seq"],
                "success": False,
                "command": request["command"],
                "message": message,
            }
        )

    async def _event(
        self, event: str, body: dict[str, Any] | None = None
    ) -> None:
        self._seq += 1
        await self._send(
            {
                "seq": self._seq,
                "type": "event",
                "event": event,
                "body": body or {},
            }
        )

    async def _on_request(self, request: dict[str, Any]) -> None:
        command = request.get("command")
        if command == "initialize":
            await self._respond(
                request, {"supportsConfigurationDoneRequest": True}
            )
            await self._event("initialized")
        elif command == "setBreakpoints":
            await self._cmd_set_breakpoints(request)
        elif command == "configurationDone":
            await self._respond(request)
        elif command == "launch":
            await self._respond(request)
            await self._step_program()
        elif command == "continue":
            await self._respond(request, {"allThreadsContinued": True})
            await self._step_program()
        elif command in ("next", "stepIn", "stepOut"):
            await self._respond(request)
            await self._step_program()
        elif command == "threads":
            await self._respond(
                request,
                {
                    "threads": [
                        {"id": thread.id, "name": thread.name}
                        for thread in THREADS
                    ]
                },
            )
        elif command == "stackTrace":
            await self._cmd_stack_trace(request)
        elif command == "source":
            await self._cmd_source(request)
        elif command == "evaluate":
            await self._cmd_evaluate(request)
        elif command == "disconnect":
            await self._respond(request)
            await self._event("terminated")
        else:
            await self._respond(request)

    async def _step_program(self) -> None:
        """Advance the fake loop one iteration and stop again."""
        self._counter += 1
        await self._event(
            "output",
            {"category": "stdout", "output": f"counter = {self._counter}\n"},
        )
        await self._event(
            "stopped",
            {
                "reason": "breakpoint",
                "threadId": 1,
                "allThreadsStopped": True,
            },
        )

    async def _cmd_set_breakpoints(self, request: dict[str, Any]) -> None:
        args = request.get("arguments") or {}
        requested = args.get("breakpoints") or []
        verified = [
            {"verified": True, "line": bp.get("line", 1), "id": index + 1}
            for index, bp in enumerate(requested)
        ]
        await self._respond(request, {"breakpoints": verified})

    async def _cmd_stack_trace(self, request: dict[str, Any]) -> None:
        args = request.get("arguments") or {}
        thread_id = int(args.get("threadId", 1))
        await self._respond(request, {"stackFrames": _frames_for(thread_id)})

    async def _cmd_source(self, request: dict[str, Any]) -> None:
        args = request.get("arguments") or {}
        if args.get("sourceReference") == PSEUDOCODE_SOURCE_REFERENCE:
            await self._respond(request, {"content": PSEUDOCODE})
        else:
            await self._error(request, "Unknown source reference")

    async def _cmd_evaluate(self, request: dict[str, Any]) -> None:
        args = request.get("arguments") or {}
        expression = str(args.get("expression", "")).strip()
        if expression == "counter":
            result = str(self._counter)
        else:
            result = f"<mock: {expression}>"
        await self._respond(
            request, {"result": result, "variablesReference": 0}
        )


class DapMock:
    """A running mock debug adapter."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self._host = host
        self._port = port
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: Server | None = None
        self._stop: asyncio.Event | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()

    @property
    def url(self) -> str:
        """The ``ws://`` address clients should connect to."""
        if self._server is None:
            raise RuntimeError("DAP mock is not running")
        sockets = self._server.sockets
        if not sockets:
            raise RuntimeError("DAP mock has no listening socket")
        host, port = sockets[0].getsockname()[:2]
        return f"ws://{host}:{port}"

    @property
    def info(self) -> dict[str, Any]:
        """Everything a test needs to drive the debugger sidebar."""
        return {
            "url": self.url,
            "pseudocodeName": PSEUDOCODE_NAME,
            "pseudocodeSourceReference": PSEUDOCODE_SOURCE_REFERENCE,
            "diskSourcePath": DISK_SOURCE_PATH,
            "diskSourceMarker": DISK_SOURCE_MARKER,
        }

    def start(self) -> DapMock:
        self._write_disk_source()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="dap-mock"
        )
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("DAP mock failed to start")
        return self

    def stop(self) -> None:
        if self._loop is not None and self._stop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _write_disk_source(self) -> None:
        os.makedirs(os.path.dirname(DISK_SOURCE_PATH), exist_ok=True)
        with open(DISK_SOURCE_PATH, "w", encoding="utf-8") as f:
            f.write(DISK_SOURCE)

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main())
        finally:
            loop.close()

    async def _main(self) -> None:
        async with websockets.serve(
            self._handler, self._host, self._port
        ) as server:
            self._server = server
            self._stop = asyncio.Event()
            self._ready.set()
            await self._stop.wait()

    async def _handler(self, websocket: ServerConnection) -> None:
        session = _Session(websocket)
        try:
            await session.run()
        except ConnectionClosed:
            # The client went away, which is the normal way a session
            # ends; there is nothing to recover from.
            return


def start_dap_mock(host: str = "127.0.0.1", port: int = 0) -> DapMock:
    """Start a mock debug adapter on a loopback port."""
    return DapMock(host, port).start()
