# SPDX-License-Identifier: GPL-3.0-or-later
"""A loopback fake of the OpenRouter chat completion API.

The test suite points ``core/ai/openrouter_api_base`` at this server so
nothing ever reaches a paid provider.  It streams a completion that
echoes the last user (or tool) message, whatever model is requested, and
reports a small token count and cost so the usage display is exercised.

It is a plain threaded HTTP server, deliberately independent of the
Kaithem event loop, so it can run beside the real server without being
part of it.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

#: When the last user message contains ``[[tool:name]]`` (optionally
#: followed by a JSON object), the mock asks for that tool call instead
#: of answering directly.  That lets tests drive the action log.
TOOL_TRIGGER = "[[tool:"

#: Cost reported for every completion, in US dollars.
MOCK_COST = 0.00042

#: Prefix the mock prepends to the echoed text.
ECHO_PREFIX = "Echo: "


def _last_reply_target(
    messages: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """The last user or tool message, which the mock echoes."""
    for message in reversed(messages):
        if message.get("role") in ("user", "tool"):
            return message
    return None


def _parse_tool_trigger(text: str) -> dict[str, str] | None:
    """Parse ``[[tool:name {json}]]`` into a tool call description."""
    index = text.find(TOOL_TRIGGER)
    if index == -1:
        return None
    body = text[index + len(TOOL_TRIGGER) :]
    end = body.find("]]")
    if end == -1:
        return None
    spec = body[:end].strip()
    name, _, raw = spec.partition(" ")
    name = name.strip()
    if not name:
        return None
    arguments = raw.strip() or "{}"
    try:
        json.loads(arguments)
    except ValueError:
        arguments = json.dumps({"value": raw.strip()})
    return {"name": name, "arguments": arguments}


def _reply_for(request: dict[str, Any]) -> dict[str, Any]:
    """Decide what the mock should stream back for one request."""
    messages = request.get("messages") or []
    target = _last_reply_target(messages)
    text = str((target or {}).get("content") or "")
    if target is not None and target.get("role") == "user":
        trigger = _parse_tool_trigger(text)
        if trigger is not None:
            return {"tool_calls": [trigger]}
    return {
        "content": ECHO_PREFIX + text,
        "reasoning": "Considering: " + text[:200],
    }


def _usage_for(request: dict[str, Any], reply_text: str) -> dict[str, Any]:
    prompt = sum(
        len(str(message.get("content") or "")) // 4
        for message in request.get("messages") or []
    )
    completion = max(len(reply_text) // 4, 1)
    total = prompt + completion
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "cost": MOCK_COST,
    }


class _MockServer(ThreadingHTTPServer):
    """A threaded server that counts how many completions it served.

    The count lets tests prove that a conversation makes no request until
    something actually needs one.
    """

    daemon_threads = True

    def __init__(self, address: tuple[str, int], handler: type) -> None:
        super().__init__(address, handler)
        self.request_count = 0
        self._count_lock = threading.Lock()

    def record_request(self) -> None:
        with self._count_lock:
            self.request_count += 1


class _Handler(BaseHTTPRequestHandler):
    # HTTP/1.0 makes the server close the connection after each response,
    # so the client can stream until end of file without chunked encoding.
    protocol_version = "HTTP/1.0"

    def log_message(self, *args: Any) -> None:  # noqa: ARG002
        # Keep the test console quiet.
        pass

    def do_POST(self) -> None:  # noqa: N802
        server = self.server
        if isinstance(server, _MockServer):
            server.record_request()
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            request = json.loads(raw or b"{}")
        except ValueError:
            request = {}
        self._respond(request)

    def _respond(self, request: dict[str, Any]) -> None:
        model = str(request.get("model") or "mock")
        reply = _reply_for(request)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        for event in _events(model, request, reply):
            self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def _events(
    model: str, request: dict[str, Any], reply: dict[str, Any]
) -> list[dict[str, Any]]:
    reply_text = str(reply.get("content") or "")
    events: list[dict[str, Any]] = []
    reasoning = reply.get("reasoning")
    if reasoning:
        events.append(_delta(model, {"reasoning": reasoning}))
    tool_calls = reply.get("tool_calls")
    if tool_calls:
        events.append(
            _delta(
                model,
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_0",
                            "type": "function",
                            "function": {
                                "name": tool_calls[0]["name"],
                                "arguments": tool_calls[0]["arguments"],
                            },
                        }
                    ]
                },
            )
        )
        events.append(_finish(model, "tool_calls"))
    else:
        events.extend(_chunked_content(model, reply_text))
        events.append(_finish(model, "stop"))
    events.append(
        {
            "model": model,
            "choices": [],
            "usage": _usage_for(request, reply_text),
        }
    )
    return events


def _delta(model: str, delta: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": model,
        "choices": [{"delta": delta, "finish_reason": None}],
    }


def _finish(model: str, reason: str) -> dict[str, Any]:
    return {
        "model": model,
        "choices": [{"delta": {}, "finish_reason": reason}],
    }


def _chunked_content(model: str, text: str) -> list[dict[str, Any]]:
    """Split text into a couple of deltas so streaming is observable."""
    if not text:
        return []
    midpoint = max(len(text) // 2, 1)
    return [
        _delta(model, {"content": text[:midpoint]}),
        _delta(model, {"content": text[midpoint:]}),
    ]


class AiMock:
    """A running fake OpenRouter server."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self._server = _MockServer((host, port), _Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="ai-mock",
        )

    @property
    def api_base(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/v1"

    @property
    def request_count(self) -> int:
        """How many completions this mock has served."""
        return self._server.request_count

    def start(self) -> AiMock:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def start_ai_mock(host: str = "127.0.0.1", port: int = 0) -> AiMock:
    """Start a fake OpenRouter server on a loopback port."""
    return AiMock(host, port).start()
