# SPDX-License-Identifier: GPL-3.0-or-later
"""Agentic conversation runtime and global registry.

A :class:`Conversation` owns the persistent history, the lazily built
OpenRouter client, and a queue that guarantees a single agentic loop
runs at a time even when several threads are active.

The registry in this module is the single owner of live conversations.
Resource runtime objects only remember the conversation id and its
config, so there is exactly one loop and one set of listeners per
conversation, and a conversation can be dropped from memory and rebuilt
later without losing anything on disk.
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

import structlog

from kaithem.api import ai

from . import tools
from .models import (
    ActionEntry,
    ChatEntry,
    ChatMessage,
    CompletionResult,
    ConversationConfig,
    Entry,
    ThreadInfo,
    ToolCall,
)
from .openrouter import (
    MissingApiKeyError,
    OpenRouterClient,
    OpenRouterError,
)
from .storage import (
    ConversationStorage,
    load_conversation_config,
)

logger = structlog.get_logger(__name__)

#: Hard limit on tool call rounds in a single agentic run.
MAX_ROUNDS = 25

#: Most queued runs before new messages are rejected.
MAX_QUEUE = 100

#: A listener receives plain dict events meant to be JSON encoded.
Listener = Callable[[dict[str, Any]], None]


class Interrupted(Exception):
    """Raised inside the delta callback to abort a streaming run."""


class Conversation:
    """One agentic conversation, possibly with several threads."""

    def __init__(
        self,
        config: ConversationConfig,
        storage: ConversationStorage,
    ):
        self.config = config
        self.storage = storage
        self._listeners: set[Listener] = set()
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._interrupt = asyncio.Event()
        self._status = "idle"
        self._client: OpenRouterClient | None = None

    @property
    def id(self) -> str:
        return self.config.id

    @property
    def status(self) -> str:
        return self._status

    # -- listeners --------------------------------------------------------

    def add_listener(self, listener: Listener) -> None:
        self._listeners.add(listener)

    def remove_listener(self, listener: Listener) -> None:
        self._listeners.discard(listener)

    def _emit(self, event: dict[str, Any]) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                logger.exception("Conversation listener raised")

    def _set_status(self, status: str) -> None:
        self._status = status
        self._emit({"type": "status", "status": status})

    # -- config -----------------------------------------------------------

    def update_config(self, config: ConversationConfig) -> None:
        if config.id != self.id:
            raise ValueError("Cannot change a conversation's id")
        if config.persistent != self.config.persistent:
            self.storage = build_storage(config)
        self.config = config

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.config.title,
            "model": self.config.model,
            "status": self._status,
            "threads": [t.model_dump() for t in self.list_threads()],
        }

    # -- threads ----------------------------------------------------------

    def list_threads(self) -> list[ThreadInfo]:
        """Every thread of this conversation, oldest first."""
        return self.storage.list_threads()

    def create_thread(self, title: str) -> ThreadInfo:
        info = self.storage.create_thread(title)
        self._emit(
            {
                "type": "threads",
                "threads": [t.model_dump() for t in self.list_threads()],
            }
        )
        return info

    def get_entries(self, slug: str) -> list[dict[str, Any]]:
        return [entry.model_dump() for entry in self.storage.read(slug)]

    # -- sending ----------------------------------------------------------

    async def send(self, slug: str, text: str, author: str = "") -> None:
        """Queue a user message and start the loop if it is idle."""
        text = text.strip()
        if not text:
            raise ValueError("Cannot send an empty message")
        if not self.storage.has_thread(slug):
            raise KeyError(f"Unknown thread {slug!r}")
        if self._queue.qsize() >= MAX_QUEUE:
            raise RuntimeError("Conversation queue is full")
        entry = ChatEntry(
            id=uuid.uuid4().hex,
            timestamp=time.time(),
            thread=slug,
            author=author,
            message=ChatMessage(role="user", content=text),
        )
        self._append(entry)
        self._queue.put_nowait(slug)
        self._ensure_worker()

    def interrupt(self) -> None:
        """Ask the running loop to stop after the current chunk."""
        self._interrupt.set()

    def _append(self, entry: Entry) -> None:
        self.storage.append(entry.thread, entry)
        self._emit({"type": "entry", "entry": entry.model_dump()})

    def _ensure_worker(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._worker_loop())

    async def _worker_loop(self) -> None:
        try:
            while True:
                try:
                    slug = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                try:
                    await self._run_loop(slug)
                except Exception:
                    logger.exception("Agentic loop failed")
                    self._set_status("error")
        finally:
            self._worker = None
            self.maybe_unload()

    # -- the agentic loop -------------------------------------------------

    async def _run_loop(self, slug: str) -> None:
        self._interrupt = asyncio.Event()
        self._set_status("thinking")
        partial = {"content": "", "reasoning": ""}

        def on_delta(kind: str, text: str) -> None:
            if self._interrupt.is_set():
                raise Interrupted()
            partial[kind] += text
            self._emit(
                {
                    "type": "delta",
                    "thread": slug,
                    "kind": kind,
                    "text": text,
                }
            )

        try:
            messages = self._build_messages(self.storage.read(slug))
            await self._rounds(slug, messages, partial, on_delta)
        except MissingApiKeyError as exc:
            self._fail(slug, "missing_api_key", str(exc))
            return
        except OpenRouterError as exc:
            self._fail(slug, "openrouter_error", str(exc))
            return
        self._set_status("idle")

    async def _rounds(
        self,
        slug: str,
        messages: list[ChatMessage],
        partial: dict[str, str],
        on_delta: Callable[[str, str], None],
    ) -> None:
        model = ai.resolve_model(self.config.model)
        tool_specs = tools.openai_tools() or None
        rounds = 0
        while rounds < MAX_ROUNDS:
            rounds += 1
            client = self._get_client()
            try:
                result = await client.stream_chat(
                    model, messages, tools=tool_specs, on_delta=on_delta
                )
            except Interrupted:
                result = CompletionResult(
                    content=partial["content"],
                    reasoning=partial["reasoning"],
                    model=model,
                    finish_reason="interrupted",
                )
            assistant = ChatMessage(
                role="assistant",
                content=result.content,
                reasoning=result.reasoning,
                tool_calls=result.tool_calls,
            )
            self._append(
                ChatEntry(
                    id=uuid.uuid4().hex,
                    timestamp=time.time(),
                    thread=slug,
                    message=assistant,
                    model=result.model or model,
                    usage=result.usage,
                )
            )
            messages.append(assistant)
            if result.finish_reason == "interrupted":
                break
            if self._interrupt.is_set():
                break
            if not result.tool_calls:
                break
            for call in result.tool_calls:
                await self._run_tool(slug, call, messages)
            partial["content"] = ""
            partial["reasoning"] = ""

    async def _run_tool(
        self, slug: str, call: ToolCall, messages: list[ChatMessage]
    ) -> None:
        arguments = call.parsed_arguments()
        started = time.time()
        action_id = uuid.uuid4().hex
        self._emit(
            {
                "type": "action",
                "action": ActionEntry(
                    id=action_id,
                    timestamp=started,
                    thread=slug,
                    name=call.name,
                    arguments=arguments,
                    status="running",
                ).model_dump(),
            }
        )
        try:
            output = await tools.call_tool(call.name, arguments)
            status = "ok"
        except Exception as exc:
            output = f"Error: {exc}"
            status = "error"
        self._append(
            ActionEntry(
                id=action_id,
                timestamp=started,
                thread=slug,
                name=call.name,
                arguments=arguments,
                status=status,
                result=output,
                duration=time.time() - started,
            )
        )
        messages.append(
            ChatMessage(
                role="tool",
                content=output,
                tool_call_id=call.id,
            )
        )

    def _build_messages(self, history: list[Entry]) -> list[ChatMessage]:
        messages: list[ChatMessage] = []
        prompt = self.config.system_prompt.strip()
        if prompt:
            messages.append(ChatMessage(role="system", content=prompt))
        for entry in history:
            if isinstance(entry, ChatEntry):
                messages.append(entry.message)
        return messages

    def _get_client(self) -> OpenRouterClient:
        api_base = ai.get_api_base()
        api_key = ai.get_api_key()
        if (
            self._client is None
            or self._client.api_base != api_base
            or self._client.api_key != api_key
        ):
            self._client = OpenRouterClient(api_base=api_base, api_key=api_key)
        return self._client

    def _fail(self, slug: str, code: str, message: str) -> None:
        logger.warning("Conversation %s failed: %s", self.id, message)
        self._emit(
            {
                "type": "error",
                "thread": slug,
                "error": code,
                "message": message,
            }
        )
        self._set_status("error")

    # -- lifetime ---------------------------------------------------------

    def maybe_unload(self) -> None:
        """Drop from the registry once idle, if the setting allows it."""
        if self._listeners:
            return
        if self._queue.qsize():
            return
        if self._worker is not None and not self._worker.done():
            return
        if not ai.unload_when_idle():
            return
        unload(self.id)

    def close(self) -> None:
        self._listeners.clear()
        task = self._worker
        self._worker = None
        if task is None or task.done():
            return
        try:
            loop = task.get_loop()
        except RuntimeError:
            return
        if not loop.is_closed():
            loop.call_soon_threadsafe(task.cancel)


# -- registry -------------------------------------------------------------

_configs: dict[str, ConversationConfig] = {}
_conversations: dict[str, Conversation] = {}
_registry_lock = threading.Lock()


def build_storage(config: ConversationConfig) -> ConversationStorage:
    base_dir = ai.get_conversations_dir() if config.persistent else None
    return ConversationStorage(base_dir, config.id)


def register_config(config: ConversationConfig) -> None:
    """Remember a conversation's config and update a live instance."""
    with _registry_lock:
        _configs[config.id] = config
        live = _conversations.get(config.id)
    if live is not None:
        live.update_config(config)
    if config.persistent:
        build_storage(config).write_config(config.model_dump())


def unregister_config(conversation_id: str) -> None:
    """Forget a config and drop any live instance (history is kept)."""
    with _registry_lock:
        _configs.pop(conversation_id, None)
        live = _conversations.pop(conversation_id, None)
    if live is not None:
        live.close()


def get_config(conversation_id: str) -> ConversationConfig | None:
    """Return a config without building a live conversation."""
    config = _configs.get(conversation_id)
    if config is not None:
        return config
    config = _load_config(conversation_id)
    if config is not None:
        _configs[conversation_id] = config
    return config


def _load_config(conversation_id: str) -> ConversationConfig | None:
    base_dir = ai.get_conversations_dir()
    data = load_conversation_config(base_dir, conversation_id)
    if data is None:
        return None
    data = {**data, "id": conversation_id}
    try:
        return ConversationConfig.model_validate(data)
    except Exception:
        logger.exception("Invalid conversation config for %s", conversation_id)
        return None


def get_conversation(conversation_id: str) -> Conversation:
    """Return the live conversation, building it on first use."""
    config = get_config(conversation_id)
    if config is None:
        raise KeyError(f"Unknown conversation {conversation_id!r}")
    with _registry_lock:
        live = _conversations.get(conversation_id)
        if live is None:
            live = Conversation(config, build_storage(config))
            _conversations[conversation_id] = live
        else:
            live.update_config(config)
        return live


def peek_conversation(conversation_id: str) -> Conversation | None:
    """Return the live conversation if there is one, else None."""
    with _registry_lock:
        return _conversations.get(conversation_id)


def unload(conversation_id: str) -> None:
    """Drop a conversation from memory without touching its history."""
    with _registry_lock:
        live = _conversations.pop(conversation_id, None)
    if live is not None:
        live.close()


def delete_conversation(conversation_id: str) -> None:
    """Delete a conversation's config and its entire history."""
    with _registry_lock:
        config = _configs.pop(conversation_id, None)
        live = _conversations.pop(conversation_id, None)
    if live is not None:
        live.close()
        storage = live.storage
    elif config is not None:
        storage = build_storage(config)
    else:
        config = _load_config(conversation_id)
        storage = build_storage(config) if config else None
    if storage is not None:
        storage.delete()


def list_configs() -> list[ConversationConfig]:
    """Configs of every conversation registered from a loaded module."""
    return list(_configs.values())


def live_count() -> int:
    """Number of conversations currently held in memory (for tests)."""
    return len(_conversations)
