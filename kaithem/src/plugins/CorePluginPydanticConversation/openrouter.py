# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal async OpenRouter (OpenAI compatible) chat client.

Deliberately small: one streaming completion call, SSE parsing, and just
enough error handling to give the UI a useful message.  Nothing here is
imported or called until a conversation actually sends a message, which
keeps idle conversations from touching the possibly paid API.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import structlog

from .models import ChatMessage, CompletionResult, ToolCall, Usage

logger = structlog.get_logger(__name__)

#: Called with ("content"|"reasoning", text) for every streamed delta.
DeltaCallback = Callable[[str, str], None]

#: Number of times to (re)try a completion.  A retry only happens when
#: nothing has been streamed yet, so the user never sees duplicated text.
MAX_ATTEMPTS = 3

#: Streaming reads can be slow, so the read timeout is generous.
_TIMEOUT = httpx.Timeout(connect=20.0, read=300.0, write=60.0, pool=20.0)


class OpenRouterError(Exception):
    """Raised when a completion could not be produced."""


class MissingApiKeyError(OpenRouterError):
    """Raised when no OpenRouter API key has been configured."""


def _parse_usage(raw: dict[str, Any]) -> Usage:
    cost = raw.get("cost", raw.get("total_cost"))
    try:
        cost_value = float(cost) if cost is not None else None
    except (TypeError, ValueError):
        cost_value = None
    return Usage(
        prompt_tokens=int(raw.get("prompt_tokens") or 0),
        completion_tokens=int(raw.get("completion_tokens") or 0),
        total_tokens=int(raw.get("total_tokens") or 0),
        cost=cost_value,
    )


def message_to_wire(message: ChatMessage) -> dict[str, Any]:
    """Convert a :class:`ChatMessage` to the OpenAI message shape."""
    wire: dict[str, Any] = {
        "role": message.role,
        "content": message.content,
    }
    if message.name:
        wire["name"] = message.name
    if message.tool_call_id:
        wire["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        wire["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": call.arguments,
                },
            }
            for call in message.tool_calls
        ]
    return wire


class OpenRouterClient:
    """A thin streaming wrapper around an OpenAI compatible endpoint."""

    def __init__(self, api_base: str, api_key: str):
        if not api_base:
            raise ValueError("api_base is required")
        self.api_base = api_base
        self.api_key = api_key

    def _url(self) -> str:
        return self.api_base.rstrip("/") + "/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://kaithem.com",
            "X-Title": "Kaithem",
        }

    async def stream_chat(
        self,
        model: str,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        on_delta: DeltaCallback | None = None,
    ) -> CompletionResult:
        """Run one streaming completion and return the assembled result."""
        if not self.api_key:
            raise MissingApiKeyError(
                "No OpenRouter API key is configured.  Set it in "
                "Settings -> AI Settings."
            )

        payload: dict[str, Any] = {
            "model": model,
            "messages": [message_to_wire(m) for m in messages],
            "stream": True,
            "stream_options": {"include_usage": True},
            "usage": {"include": True},
        }
        if tools:
            payload["tools"] = tools

        emitted = {"any": False}

        def track(kind: str, text: str) -> None:
            emitted["any"] = True
            if on_delta is not None:
                on_delta(kind, text)

        attempt = 0
        while True:
            attempt += 1
            try:
                return await self._stream_once(model, payload, track, emitted)
            except (httpx.HTTPError, OpenRouterError) as exc:
                if emitted["any"] or attempt >= MAX_ATTEMPTS:
                    raise
                logger.warning(
                    "OpenRouter attempt %s failed, retrying: %s",
                    attempt,
                    exc,
                )

    async def _stream_once(
        self,
        model: str,
        payload: dict[str, Any],
        on_delta: DeltaCallback,
        emitted: dict[str, bool],
    ) -> CompletionResult:
        result = CompletionResult(model=model)
        buffers: dict[int, dict[str, str]] = {}

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            async with client.stream(
                "POST",
                self._url(),
                json=payload,
                headers=self._headers(),
            ) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", "replace")
                    raise OpenRouterError(
                        f"API returned {response.status_code}: {body[:500]}"
                    )
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except ValueError:
                        continue
                    self._apply_event(event, result, buffers, on_delta, emitted)

        result.tool_calls = _finish_tool_calls(buffers)
        return result

    def _apply_event(
        self,
        event: dict[str, Any],
        result: CompletionResult,
        buffers: dict[int, dict[str, str]],
        on_delta: DeltaCallback,
        emitted: dict[str, bool],
    ) -> None:
        for choice in event.get("choices") or []:
            delta = choice.get("delta") or {}
            reasoning = delta.get("reasoning") or delta.get("reasoning_content")
            if reasoning:
                result.reasoning += reasoning
                on_delta("reasoning", reasoning)
            content = delta.get("content")
            if content:
                result.content += content
                on_delta("content", content)
            for call in delta.get("tool_calls") or []:
                _accumulate_tool_call(buffers, call)
            finish = choice.get("finish_reason")
            if finish:
                result.finish_reason = finish

        usage = event.get("usage")
        if usage:
            result.usage = _parse_usage(usage)
        if event.get("model"):
            result.model = event["model"]


def _accumulate_tool_call(
    buffers: dict[int, dict[str, str]], call: dict[str, Any]
) -> None:
    index = call.get("index", 0)
    buffer = buffers.setdefault(index, {"id": "", "name": "", "arguments": ""})
    if call.get("id"):
        buffer["id"] = call["id"]
    function = call.get("function") or {}
    if function.get("name"):
        buffer["name"] += function["name"]
    if function.get("arguments"):
        buffer["arguments"] += function["arguments"]


def _finish_tool_calls(buffers: dict[int, dict[str, str]]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for index in sorted(buffers):
        buffer = buffers[index]
        if not buffer["name"]:
            continue
        calls.append(
            ToolCall(
                id=buffer["id"] or f"call_{index}",
                name=buffer["name"],
                arguments=buffer["arguments"] or "{}",
            )
        )
    return calls
