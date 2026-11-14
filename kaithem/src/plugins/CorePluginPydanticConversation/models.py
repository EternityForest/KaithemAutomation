# SPDX-License-Identifier: GPL-3.0-or-later
"""Pydantic models for agentic conversations.

Everything written to a conversation's LDJSON history, and everything the
web API hands back to the browser, is defined here so there is a single
source of truth for the shape of the data.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    Field,
    TypeAdapter,
    ValidationError,
)

#: The user namespace used for programmatic, non web callers.  Threads of a
#: conversation are stored per user, and callers that do not name a user
#: keep working against this namespace.
DEFAULT_USER = "__system__"


class Usage(BaseModel):
    """Token counts and the reported cost of one completion."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    #: Cost in US dollars as reported by the provider, when available.
    cost: float | None = None


class ToolCall(BaseModel):
    """A tool invocation requested by the model."""

    id: str
    name: str
    arguments: str = "{}"

    def parsed_arguments(self) -> dict[str, Any]:
        """The tool arguments as a dict, tolerating malformed JSON."""
        import json

        try:
            value = json.loads(self.arguments or "{}")
        except ValueError:
            return {}
        if isinstance(value, dict):
            return value
        return {"value": value}


class ChatMessage(BaseModel):
    """One message in the OpenAI compatible message list."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    reasoning: str = ""
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)


class CompletionResult(BaseModel):
    """The assembled result of one streaming completion."""

    content: str = ""
    reasoning: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: Usage | None = None
    model: str = ""
    finish_reason: str = ""


class ChatEntry(BaseModel):
    """A persisted chat message with its provider metadata."""

    type: Literal["message"] = "message"
    id: str
    timestamp: float
    thread: str
    message: ChatMessage
    #: The authenticated user who sent a user message, if any.
    author: str = ""
    model: str = ""
    usage: Usage | None = None


class ActionEntry(BaseModel):
    """A persisted record of one tool call and its outcome.

    This is both the action log entry the UI shows and the ``role: "tool"``
    message replayed to the model on later turns, so the tool call id is
    kept to pair each result with the assistant message that asked for it.
    """

    type: Literal["action"] = "action"
    id: str
    timestamp: float
    thread: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    #: The tool call id of the assistant message this result answers.
    tool_call_id: str = ""
    status: Literal["running", "ok", "error"] = "running"
    result: str = ""
    duration: float = 0.0


class ThreadHeader(BaseModel):
    """The first line of a thread file, describing the thread."""

    type: Literal["thread"] = "thread"
    id: str
    timestamp: float
    slug: str
    title: str = ""


#: Every kind of line that can appear in a thread file.
Entry = Annotated[
    ChatEntry | ActionEntry | ThreadHeader,
    Field(discriminator="type"),
]

entry_adapter: TypeAdapter[Entry] = TypeAdapter(Entry)


def dump_entry(entry: Entry) -> str:
    """Serialize one entry to a single LDJSON line (without newline)."""
    return entry_adapter.dump_json(entry).decode("utf-8")


def parse_entry(line: str) -> Entry | None:
    """Parse one LDJSON line, returning None for a malformed line."""
    line = line.strip()
    if not line:
        return None
    try:
        return entry_adapter.validate_json(line)
    except ValidationError:
        return None


class ThreadInfo(BaseModel):
    """Summary of one thread, as returned by ``list_threads()``."""

    slug: str
    title: str = ""
    message_count: int = 0
    updated: float = 0.0


class ConversationConfig(BaseModel):
    """The user facing configuration of a conversation.

    This is what the ``conversation`` resource stores and what the chat
    UI reads.  It never contains the API key or any other secret.
    """

    id: str
    title: str = ""
    #: A model tag ("code", "chat") or a literal provider model id.
    model: str = "chat"
    #: Permissions a user must hold to read and write the conversation.
    permissions: list[str] = Field(default_factory=lambda: ["system_admin"])
    #: When true, history is written to append only LDJSON files.
    persistent: bool = True
    system_prompt: str = ""
    #: Absolute path of the folder the model may read and edit.  When
    #: empty, the conversation has no file tools and only chats.
    workspace: str = ""
