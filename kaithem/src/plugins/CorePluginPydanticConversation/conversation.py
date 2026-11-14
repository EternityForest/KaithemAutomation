# SPDX-License-Identifier: GPL-3.0-or-later
"""Agentic conversation runtime and global registry.

A :class:`Conversation` owns the persistent history, the lazily built
pydantic-ai agent for each run, and a queue that guarantees a single
agentic loop runs at a time even when several threads are active.

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
from collections.abc import Callable, Sequence
from typing import Any

import structlog
from pydantic_ai import CancellationToken, UsageLimits
from pydantic_ai.exceptions import RunCancelled
from pydantic_ai.messages import ModelMessage

from kaithem.api import ai

from .agent import (
    EventBridge,
    MissingApiKeyError,
    build_agent,
    to_entries,
    to_model_messages,
)
from .models import (
    DEFAULT_USER,
    ChatEntry,
    ChatMessage,
    ConversationConfig,
    Entry,
    ThreadInfo,
)
from .storage import (
    ConversationStorage,
    delete_conversation_dir,
    load_conversation_config,
    write_conversation_config,
)
from .tools import ToolContext, build_tools

logger = structlog.get_logger(__name__)

#: Hard limit on tool call rounds in a single agentic run.
MAX_ROUNDS = 25

#: Most queued runs before new messages are rejected.
MAX_QUEUE = 100

#: A listener receives plain dict events meant to be JSON encoded.
Listener = Callable[[dict[str, Any]], None]


class Conversation:
    """One agentic conversation, possibly with several threads.

    Threads are namespaced per user, so a conversation shared between an
    admin and several users keeps their chats apart.  There is still only
    one agentic loop at a time, shared across every thread and every user,
    so the queue serialises them all.
    """

    def __init__(
        self,
        config: ConversationConfig,
        base_dir: str | None,
    ):
        self.config = config
        self.base_dir = base_dir
        self._stores: dict[str, ConversationStorage] = {}
        self._listeners: dict[str, set[Listener]] = {}
        self._queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._cancel: CancellationToken | None = None
        self._status = "idle"

    @property
    def id(self) -> str:
        return self.config.id

    @property
    def status(self) -> str:
        return self._status

    def storage(self, user: str = DEFAULT_USER) -> ConversationStorage:
        """The storage for one user's threads, created on first use."""
        store = self._stores.get(user)
        if store is None:
            store = ConversationStorage(self.base_dir, self.id, user)
            self._stores[user] = store
        return store

    # -- listeners --------------------------------------------------------

    def add_listener(self, user: str, listener: Listener) -> None:
        self._listeners.setdefault(user, set()).add(listener)

    def remove_listener(self, user: str, listener: Listener) -> None:
        listeners = self._listeners.get(user)
        if listeners is None:
            return
        listeners.discard(listener)
        if not listeners:
            self._listeners.pop(user, None)

    def _emit(self, event: dict[str, Any], user: str | None = None) -> None:
        """Deliver an event to one user, or to every user when None."""
        if user is None:
            targets = [
                listener
                for listeners in self._listeners.values()
                for listener in listeners
            ]
        else:
            targets = list(self._listeners.get(user, ()))
        for listener in targets:
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
            self.base_dir = conversation_base_dir(config)
            self._stores.clear()
        self.config = config

    def snapshot(self, user: str = DEFAULT_USER) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.config.title,
            "model": self.config.model,
            "status": self._status,
            "threads": [t.model_dump() for t in self.list_threads(user)],
        }

    # -- threads ----------------------------------------------------------

    def list_threads(self, user: str = DEFAULT_USER) -> list[ThreadInfo]:
        """Every thread this user has, oldest first."""
        return self.storage(user).list_threads()

    def create_thread(self, title: str, user: str = DEFAULT_USER) -> ThreadInfo:
        info = self.storage(user).create_thread(title)
        self._emit(
            {
                "type": "threads",
                "threads": [t.model_dump() for t in self.list_threads(user)],
            },
            user,
        )
        return info

    def get_entries(
        self, slug: str, user: str = DEFAULT_USER
    ) -> list[dict[str, Any]]:
        return [entry.model_dump() for entry in self.storage(user).read(slug)]

    # -- sending ----------------------------------------------------------

    async def send(
        self,
        slug: str,
        text: str,
        author: str = "",
        user: str = DEFAULT_USER,
    ) -> None:
        """Queue a user message and start the loop if it is idle."""
        text = text.strip()
        if not text:
            raise ValueError("Cannot send an empty message")
        if not self.storage(user).has_thread(slug):
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
        self._append(user, entry)
        self._queue.put_nowait((user, slug))
        self._ensure_worker()

    def interrupt(self) -> None:
        """Ask the running loop to stop as soon as it can."""
        if self._cancel is not None:
            self._cancel.cancel()

    def _append(self, user: str, entry: Entry) -> None:
        self.storage(user).append(entry.thread, entry)
        self._emit({"type": "entry", "entry": entry.model_dump()}, user)

    def _ensure_worker(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._worker_loop())

    async def _worker_loop(self) -> None:
        try:
            while True:
                try:
                    user, slug = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                try:
                    await self._run_loop(user, slug)
                except Exception:
                    logger.exception("Agentic loop failed")
                    self._set_status("error")
        finally:
            self._worker = None
            self.maybe_unload()

    # -- the agentic loop -------------------------------------------------

    async def _run_loop(self, user: str, slug: str) -> None:
        """Run one turn of a thread with a fresh pydantic-ai agent.

        Nothing is written until the run finishes, so every model reply
        and tool call the run caused lands in the history together, and
        the UI can always rebuild the thread from disk.
        """
        self._set_status("thinking")
        token = CancellationToken()
        self._cancel = token
        bridge = EventBridge(
            slug,
            on_delta=lambda kind, text: self._emit_delta(
                user, slug, kind, text
            ),
            on_action=lambda entry: self._emit(
                {"type": "action", "action": entry.model_dump()}, user
            ),
        )
        try:
            agent = self._build_agent()
            history = to_model_messages(self.storage(user).read(slug))
            result = await agent.run(
                message_history=history,
                event_stream_handler=bridge,
                usage_limits=UsageLimits(request_limit=MAX_ROUNDS),
                cancellation_token=token,
            )
        except RunCancelled as exc:
            # A user stop still keeps whatever the model already wrote.
            self._persist(user, slug, exc.new_messages(), bridge.action_ids)
            self._set_status("idle")
            return
        except MissingApiKeyError as exc:
            self._fail(user, slug, "missing_api_key", str(exc))
            return
        except Exception as exc:
            logger.exception("Agent run failed")
            self._fail(user, slug, "agent_error", str(exc))
            return
        finally:
            self._cancel = None
        self._persist(user, slug, result.new_messages(), bridge.action_ids)
        self._set_status("idle")

    def _build_agent(self):
        """Build the pydantic-ai agent for the next turn of this thread."""
        api_base = ai.get_api_base()
        api_key = ai.get_api_key()
        workspace = self.config.workspace
        context = ToolContext(
            api_base=api_base, api_key=api_key, workspace=workspace
        )
        extras = build_tools(self.config.tools, context)
        extras.extend(get_capabilities(self.id))
        return build_agent(
            model_id=ai.resolve_model(self.config.model),
            api_base=api_base,
            api_key=api_key,
            system_prompt=self.config.system_prompt,
            workspace=workspace,
            extras=extras,
        )

    def _emit_delta(self, user: str, slug: str, kind: str, text: str) -> None:
        self._emit(
            {"type": "delta", "thread": slug, "kind": kind, "text": text},
            user,
        )

    def _persist(
        self,
        user: str,
        slug: str,
        messages: Sequence[ModelMessage],
        action_ids: dict[str, str],
    ) -> None:
        """Append the entries a run produced to the thread's history."""
        for entry in to_entries(messages, slug, action_ids):
            self._append(user, entry)

    def _fail(self, user: str, slug: str, code: str, message: str) -> None:
        logger.warning("Conversation %s failed: %s", self.id, message)
        self._emit(
            {
                "type": "error",
                "thread": slug,
                "error": code,
                "message": message,
            },
            user,
        )
        self._set_status("error")

    # -- lifetime ---------------------------------------------------------

    def maybe_unload(self) -> None:
        """Drop from the registry once idle, if the setting allows it."""
        if any(self._listeners.values()):
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
        self._stores.clear()
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

#: Live pydantic-ai capabilities attached to a conversation by the code
#: that created it.  These are objects, not data, so they are kept out of
#: ConversationConfig, which is serialized to disk.
_capabilities: dict[str, list[Any]] = {}


def register_capabilities(
    conversation_id: str, capabilities: Sequence[Any]
) -> None:
    """Attach live pydantic-ai tools/capabilities to a conversation.

    They are used by every run of the conversation until replaced, so an
    embedding app can hand a conversation its own tools without a config
    change.  Pass an empty sequence to clear them.
    """
    if capabilities:
        _capabilities[conversation_id] = list(capabilities)
    else:
        _capabilities.pop(conversation_id, None)


def get_capabilities(conversation_id: str) -> list[Any]:
    """The live capabilities attached to a conversation, if any."""
    return list(_capabilities.get(conversation_id, ()))


def clear_capabilities(conversation_id: str) -> None:
    """Forget any capabilities attached to a conversation."""
    _capabilities.pop(conversation_id, None)


def conversation_base_dir(config: ConversationConfig) -> str | None:
    """Where a conversation's history lives, or None when not persistent."""
    return ai.get_conversations_dir() if config.persistent else None


def register_config(config: ConversationConfig) -> None:
    """Remember a conversation's config and update a live instance."""
    with _registry_lock:
        _configs[config.id] = config
        live = _conversations.get(config.id)
    if live is not None:
        live.update_config(config)
    if config.persistent:
        write_conversation_config(
            ai.get_conversations_dir(), config.id, config.model_dump()
        )


def unregister_config(conversation_id: str) -> None:
    """Forget a config and drop any live instance (history is kept)."""
    with _registry_lock:
        _configs.pop(conversation_id, None)
        live = _conversations.pop(conversation_id, None)
    clear_capabilities(conversation_id)
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
            live = Conversation(config, conversation_base_dir(config))
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
    """Delete a conversation's config and the history of every user."""
    with _registry_lock:
        _configs.pop(conversation_id, None)
        live = _conversations.pop(conversation_id, None)
    clear_capabilities(conversation_id)
    if live is not None:
        live.close()
    delete_conversation_dir(ai.get_conversations_dir(), conversation_id)


def list_configs() -> list[ConversationConfig]:
    """Configs of every conversation registered from a loaded module."""
    return list(_configs.values())


def live_count() -> int:
    """Number of conversations currently held in memory (for tests)."""
    return len(_conversations)
