# SPDX-License-Identifier: GPL-3.0-or-later
"""The pydantic-ai agent runtime behind a conversation.

A conversation does not run its own agentic loop.  Instead each run is
handed to a ``pydantic_ai.Agent`` built here, which brings the trusted
harness: file reading and editing tools scoped to the conversation's
workspace, argument repair, retries, and the whole multi-round tool loop.

Two conversions keep the stored history in the loop.  :func:`to_model_messages`
replays a thread as the model message list for the next turn, and
:func:`to_entries` turns the messages a run produced back into the chat
entries the UI reads.  Both directions are lossless enough that a thread
saved by an old run is a valid request for the next one.

The harness ``Shell`` capability is deliberately never added, so the
model can read and edit files but not run commands.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import AsyncIterable, Callable, Sequence
from datetime import datetime
from typing import Any

from openai import AsyncOpenAI
from pydantic_ai import Agent, Tool
from pydantic_ai.capabilities import LocalWorkspace
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterProvider
from pydantic_ai_harness.filesystem import FileSystem

from .models import ActionEntry, ChatEntry, ChatMessage, Entry, ToolCall, Usage

# pydantic-ai prints a one time banner to stdout, which would pollute the
# server's log the first time a conversation runs.  Ask it not to.
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")


class MissingApiKeyError(Exception):
    """No OpenRouter API key is configured for this server."""


def workspace_context_capabilities() -> list[Any]:
    """Capabilities that read a workspace's own context for the model.

    ``Skills`` offers any ``.agents/skills/<name>/SKILL.md`` libraries the
    workspace holds.  ``RepoContext`` loads the workspace's own
    ``AGENTS.md`` into the system prompt; with the default ``home_dir`` of
    ``None`` it reads the workspace root only, never a nested or parent
    file.  Both are optional: a harness build without them still runs,
    just without the extra context.
    """
    try:
        from pydantic_ai_harness import RepoContext, Skills
    except ImportError:  # pragma: no cover - harness without these
        return []
    return [
        Skills(".agents/skills", missing_directories="skip"),
        RepoContext(filenames=("AGENTS.md",)),
    ]


def build_agent(
    *,
    model_id: str,
    api_base: str,
    api_key: str,
    system_prompt: str = "",
    workspace: str = "",
    extras: Sequence[Any] = (),
    output_type: Any = None,
) -> Agent[Any, Any]:
    """Build one pydantic-ai agent for a single run of a conversation.

    When the conversation has a ``workspace``, the file system harness is
    pointed at it so the model can read and edit files there, and the
    workspace's own ``AGENTS.md`` and ``.agents/skills`` libraries are
    offered to the model.  ``extras`` is what the embedding code attached
    with ``register_capabilities``: a pydantic-ai ``Tool`` is handed to
    the agent as a tool, and anything else is treated as a capability.

    ``output_type`` is passed straight through to pydantic-ai, so any
    output spec its ``Agent`` accepts works; ``None`` keeps the default
    of plain text.
    """
    if not api_key:
        raise MissingApiKeyError(
            "No OpenRouter API key is configured for this server."
        )
    provider = OpenRouterProvider(
        openai_client=AsyncOpenAI(base_url=api_base, api_key=api_key)
    )
    model = OpenRouterModel(model_id, provider=provider)
    tools: list[Any] = []
    capabilities: list[Any] = []
    if workspace:
        # A workspace the user configured relative to a resource may not
        # exist yet, and both capabilities below want a real directory.
        os.makedirs(workspace, exist_ok=True)
        capabilities.append(LocalWorkspace(workspace))
        capabilities.append(FileSystem(root_dir=workspace))
        capabilities.extend(workspace_context_capabilities())
    for extra in extras:
        if isinstance(extra, Tool):
            tools.append(extra)
        else:
            capabilities.append(extra)
    options: dict[str, Any] = {}
    if output_type is not None:
        options["output_type"] = output_type
    return Agent(
        model,
        system_prompt=system_prompt.strip(),
        tools=tools,
        capabilities=capabilities,
        **options,
    )


def _wire_args(arguments: str) -> str | dict[str, Any]:
    """Tool arguments as the wire form wants them, tolerating junk."""
    if not arguments:
        return {}
    try:
        json.loads(arguments)
    except ValueError:
        return {}
    return arguments


def _arguments_to_dict(value: str | dict[str, Any] | None) -> dict[str, Any]:
    """The tool arguments as a dict, for the action log."""
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except ValueError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {"value": parsed}


def to_model_messages(history: Sequence[Entry]) -> list[ModelMessage]:
    """Replay a stored thread as the model message list for the next turn.

    Reasoning is kept on disk for display but is not replayed: it carries
    no meaning for the provider on a later turn.  Tool results are replayed
    as their own request right after the assistant message that asked for
    them, so a thread that used tools stays a valid request.
    """
    messages: list[ModelMessage] = []
    for entry in history:
        if isinstance(entry, ChatEntry):
            message = entry.message
            if message.role == "user":
                messages.append(
                    ModelRequest(
                        parts=[UserPromptPart(content=message.content)]
                    )
                )
            elif message.role == "assistant":
                parts: list[Any] = []
                if message.content:
                    parts.append(TextPart(content=message.content))
                for call in message.tool_calls:
                    parts.append(
                        ToolCallPart(
                            tool_name=call.name,
                            args=_wire_args(call.arguments),
                            tool_call_id=call.id,
                        )
                    )
                if not parts:
                    continue
                messages.append(
                    ModelResponse(parts=parts, model_name=entry.model or None)
                )
        elif isinstance(entry, ActionEntry):
            messages.append(
                ModelRequest(
                    parts=[
                        ToolReturnPart(
                            tool_name=entry.name,
                            content=entry.result,
                            tool_call_id=entry.tool_call_id,
                            outcome=(
                                "success" if entry.status == "ok" else "failed"
                            ),
                        )
                    ]
                )
            )
    return messages


def _timestamp(moment: datetime) -> float:
    return moment.timestamp()


def _content_to_str(content: Any) -> str:
    if isinstance(content, str):
        return content
    return str(content)


def usage_from(usage: Any) -> Usage | None:
    """Map a pydantic-ai usage object onto our persisted usage model."""
    if usage is None:
        return None
    cost = usage.cost
    return Usage(
        prompt_tokens=usage.input_tokens,
        completion_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        cost=float(cost) if cost is not None else None,
    )


def to_entries(
    messages: Sequence[ModelMessage],
    thread: str,
    action_ids: dict[str, str] | None = None,
) -> list[ChatEntry | ActionEntry]:
    """Turn the messages a run produced into persisted chat entries.

    ``action_ids`` lets a caller pin the id of each tool call's action
    entry, so the entry written on completion replaces the "running" one
    the UI was already shown instead of appearing twice.
    """
    action_ids = action_ids or {}
    calls: dict[str, ToolCall] = {}
    started: dict[str, float] = {}
    entries: list[ChatEntry | ActionEntry] = []
    for message in messages:
        if isinstance(message, ModelResponse):
            text = "".join(
                part.content
                for part in message.parts
                if isinstance(part, TextPart)
            )
            reasoning = "".join(
                part.content
                for part in message.parts
                if isinstance(part, ThinkingPart)
            )
            moment = _timestamp(message.timestamp)
            tool_calls: list[ToolCall] = []
            for part in message.parts:
                if isinstance(part, ToolCallPart):
                    call = ToolCall(
                        id=part.tool_call_id,
                        name=part.tool_name,
                        arguments=json.dumps(_arguments_to_dict(part.args)),
                    )
                    calls[call.id] = call
                    started[call.id] = moment
                    tool_calls.append(call)
            if not text and not reasoning and not tool_calls:
                continue
            entries.append(
                ChatEntry(
                    id=uuid.uuid4().hex,
                    timestamp=moment,
                    thread=thread,
                    message=ChatMessage(
                        role="assistant",
                        content=text,
                        reasoning=reasoning,
                        tool_calls=tool_calls,
                    ),
                    model=message.model_name or "",
                    usage=usage_from(message.usage),
                )
            )
        elif isinstance(message, ModelRequest):
            for part in message.parts:
                if not isinstance(part, ToolReturnPart):
                    continue
                call = calls.get(part.tool_call_id)
                begin = started.get(part.tool_call_id, 0.0)
                entries.append(
                    ActionEntry(
                        id=action_ids.get(part.tool_call_id)
                        or uuid.uuid4().hex,
                        timestamp=begin or _timestamp(part.timestamp),
                        thread=thread,
                        name=call.name if call else part.tool_name,
                        arguments=(
                            _arguments_to_dict(call.arguments) if call else {}
                        ),
                        tool_call_id=part.tool_call_id,
                        status=("ok" if part.outcome == "success" else "error"),
                        result=_content_to_str(part.content),
                        duration=max(_timestamp(part.timestamp) - begin, 0.0),
                    )
                )
    return entries


class EventBridge:
    """Bridges pydantic-ai stream events to the chat UI's callbacks.

    ``on_delta(kind, text)`` fires for every streamed text or reasoning
    chunk and ``on_action(entry)`` for every tool call the moment it
    starts, so the UI can show live progress.  The action ids it assigns
    are kept for :func:`to_entries`, so the entry written on completion
    updates the placeholder in place.
    """

    def __init__(
        self,
        thread: str,
        on_delta: Callable[[str, str], None],
        on_action: Callable[[ActionEntry], None],
    ) -> None:
        self.thread = thread
        self._on_delta = on_delta
        self._on_action = on_action
        self.action_ids: dict[str, str] = {}

    async def __call__(self, ctx: Any, events: AsyncIterable[Any]) -> None:
        async for event in events:
            self._handle(event)

    def _handle(self, event: Any) -> None:
        if isinstance(event, PartDeltaEvent):
            delta = event.delta
            if isinstance(delta, TextPartDelta) and delta.content_delta:
                self._on_delta("content", delta.content_delta)
            elif isinstance(delta, ThinkingPartDelta) and delta.content_delta:
                self._on_delta("reasoning", delta.content_delta)
        elif isinstance(event, FunctionToolCallEvent):
            part = event.part
            action_id = uuid.uuid4().hex
            self.action_ids[part.tool_call_id] = action_id
            self._on_action(
                ActionEntry(
                    id=action_id,
                    timestamp=time.time(),
                    thread=self.thread,
                    name=part.tool_name,
                    arguments=_arguments_to_dict(part.args),
                    tool_call_id=part.tool_call_id,
                    status="running",
                )
            )
