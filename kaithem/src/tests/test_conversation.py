# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the CorePluginPydanticConversation plugin.

Two layers are covered.  The pure logic tests exercise the LDJSON storage
and the small helpers directly.  The integration tests drive a real
``Conversation`` against the loopback OpenRouter mock in
``kaithem.src.tests.ai_mock``, so the streaming client, the agentic loop,
the tool log, and the lazy client are all run for real.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid

import pytest

from kaithem.api import ai, settings
from kaithem.src.plugins.CorePluginPydanticConversation import (
    conversation as registry,
)
from kaithem.src.plugins.CorePluginPydanticConversation import tools
from kaithem.src.plugins.CorePluginPydanticConversation.models import (
    ActionEntry,
    ChatEntry,
    ChatMessage,
    ConversationConfig,
    ThreadHeader,
    dump_entry,
    parse_entry,
)
from kaithem.src.plugins.CorePluginPydanticConversation.resource_type import (
    parse_permissions,
)
from kaithem.src.plugins.CorePluginPydanticConversation.storage import (
    ConversationStorage,
    slugify,
)
from kaithem.src.tests.ai_mock import MOCK_COST, start_ai_mock

#: Where the test conversations are written.  Must be under /dev/shm so
#: the pytest sandbox in conftest.py allows it.
CONV_DIR = "/dev/shm/kaithem_tests/conversations"


@pytest.fixture
def ai_mock():
    """Point the AI settings at a fresh loopback mock for one test."""
    mock = start_ai_mock()
    overrides = {
        "core/ai/openrouter_api_base": mock.api_base,
        "core/ai/openrouter_api_key": "test-key",
        "core/ai/conversations_dir": CONV_DIR,
    }
    for key, value in overrides.items():
        settings.add_val(key, value, "<conversation test>", 100)
    try:
        yield mock
    finally:
        for key in overrides:
            settings.add_val(key, "", "<conversation test>", 100)
        mock.stop()


def _new_storage() -> ConversationStorage:
    return ConversationStorage(CONV_DIR, uuid.uuid4().hex)


async def _wait_for(predicate, timeout: float = 10.0) -> None:
    """Poll a predicate on the event loop until it is true."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("Condition was not met before the timeout")


def _assistant_messages(storage: ConversationStorage, slug: str):
    return [
        entry
        for entry in storage.read(slug)
        if isinstance(entry, ChatEntry) and entry.message.role == "assistant"
    ]


# -- models and storage ---------------------------------------------------


def test_entry_roundtrip_and_malformed_lines():
    message = ChatEntry(
        id="a",
        timestamp=1.0,
        thread="chat",
        message=ChatMessage(role="user", content="hi"),
    )
    assert parse_entry(dump_entry(message)) == message

    header = ThreadHeader(id="b", timestamp=2.0, slug="chat", title="Chat")
    assert parse_entry(dump_entry(header)) == header

    action = ActionEntry(id="c", timestamp=3.0, thread="chat", name="do_thing")
    assert parse_entry(dump_entry(action)) == action


def test_parse_entry_rejects_junk():
    assert parse_entry("") is None
    assert parse_entry("   \n") is None
    assert parse_entry("not json at all") is None
    assert parse_entry("{") is None
    assert parse_entry('{"type": "unknown"}') is None
    assert parse_entry('{"type": "message"}') is None


def test_slugify():
    assert slugify("Hello World") == "hello-world"
    assert slugify("  spaced  out  ") == "spaced-out"
    assert slugify("///") == "thread"
    assert slugify("") == "thread"
    assert len(slugify("x" * 200)) <= 60


def test_read_ignores_malformed_lines():
    storage = _new_storage()
    thread = storage.create_thread("Chat")
    path = os.path.join(storage.directory, thread.slug + ".ldjson")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("this is not json\n")
        handle.write("\n")
        handle.write('{"type": "nope"}\n')
    storage.append(
        thread.slug,
        ChatEntry(
            id="1",
            timestamp=time.time(),
            thread=thread.slug,
            message=ChatMessage(role="user", content="hello"),
        ),
    )
    entries = storage.read(thread.slug)
    assert len(entries) == 2
    assert isinstance(entries[0], ThreadHeader)
    assert isinstance(entries[1], ChatEntry)


def test_create_thread_makes_unique_slugs():
    storage = _new_storage()
    first = storage.create_thread("Chat")
    second = storage.create_thread("Chat")
    assert first.slug == "chat"
    assert second.slug == "chat-2"
    assert {info.slug for info in storage.list_threads()} == {
        "chat",
        "chat-2",
    }


def test_list_threads_counts_and_orders():
    storage = _new_storage()
    thread = storage.create_thread("Alpha")
    storage.append(
        thread.slug,
        ChatEntry(
            id="1",
            timestamp=time.time(),
            thread=thread.slug,
            message=ChatMessage(role="user", content="one"),
        ),
    )
    later = storage.create_thread("Beta")
    infos = {info.slug: info for info in storage.list_threads()}
    assert infos["alpha"].message_count == 1
    assert infos["beta"].message_count == 0
    # Oldest first.
    assert storage.list_threads()[0].slug == "alpha"
    assert later.slug == "beta"


def test_delete_thread_and_conversation():
    storage = _new_storage()
    thread = storage.create_thread("Chat")
    assert storage.has_thread(thread.slug)
    storage.delete_thread(thread.slug)
    assert not storage.has_thread(thread.slug)
    with pytest.raises(KeyError):
        storage.read(thread.slug)
    storage.create_thread("Again")
    storage.delete()
    assert not os.path.exists(storage.directory)


def test_non_persistent_storage_stays_in_memory():
    storage = ConversationStorage(None, uuid.uuid4().hex)
    assert storage.persistent is False
    assert storage.directory is None
    thread = storage.create_thread("Chat")
    storage.append(
        thread.slug,
        ChatEntry(
            id="1",
            timestamp=time.time(),
            thread=thread.slug,
            message=ChatMessage(role="user", content="hi"),
        ),
    )
    assert len(storage.read(thread.slug)) == 2
    assert storage.list_threads()[0].message_count == 1
    storage.delete()
    assert storage.list_threads() == []


def test_safe_slug_rejects_traversal():
    storage = _new_storage()
    with pytest.raises(ValueError):
        storage.read("../evil")
    with pytest.raises(ValueError):
        storage.append("..", ThreadHeader(id="x", timestamp=0.0, slug=".."))


# -- helpers --------------------------------------------------------------


def test_parse_permissions():
    assert parse_permissions(None) == ["system_admin"]
    assert parse_permissions("") == ["system_admin"]
    assert parse_permissions("a, b") == ["a", "b"]
    assert parse_permissions(["a", "b c"]) == ["a", "b", "c"]
    assert parse_permissions("a  a") == ["a"]


def test_resolve_model_tags():
    assert ai.resolve_model("code") == "z-ai/glm-5.3-flash"
    assert ai.resolve_model("chat") == "google/gemini-3.1-flash-lite"
    assert ai.resolve_model("") == "google/gemini-3.1-flash-lite"
    assert ai.resolve_model("vendor/model") == "vendor/model"


# -- registry -------------------------------------------------------------


def test_registry_load_unload_delete(ai_mock):
    conversation_id = uuid.uuid4().hex
    config = ConversationConfig(
        id=conversation_id, title="Unit", model="chat", persistent=True
    )
    registry.register_config(config)
    assert registry.get_config(conversation_id) is not None

    conversation = registry.get_conversation(conversation_id)
    assert conversation.id == conversation_id
    assert conversation.status == "idle"
    # Nothing should have touched the API just by loading.
    assert ai_mock.request_count == 0

    assert registry.peek_conversation(conversation_id) is conversation
    registry.unload(conversation_id)
    assert registry.peek_conversation(conversation_id) is None

    registry.delete_conversation(conversation_id)
    assert registry.get_config(conversation_id) is None
    assert not os.path.exists(os.path.join(CONV_DIR, conversation_id))


def test_config_reloads_from_disk(ai_mock):
    """A config written to disk can be reloaded after being forgotten."""
    conversation_id = uuid.uuid4().hex
    registry.register_config(
        ConversationConfig(id=conversation_id, title="Persisted", model="code")
    )
    registry.unregister_config(conversation_id)
    # The config is dropped from memory but reloads from its disk file.
    reloaded = registry.get_config(conversation_id)
    assert reloaded is not None
    assert reloaded.model == "code"
    assert reloaded.title == "Persisted"
    registry.delete_conversation(conversation_id)
    assert registry.get_config(conversation_id) is None


# -- the agentic loop -----------------------------------------------------


async def test_send_echoes_and_records_usage(ai_mock):
    conversation_id = uuid.uuid4().hex
    registry.register_config(
        ConversationConfig(id=conversation_id, model="chat")
    )
    conversation = registry.get_conversation(conversation_id)
    thread = conversation.create_thread("Chat")
    # Loading a conversation and creating a thread touches nothing.
    assert ai_mock.request_count == 0

    await conversation.send(thread.slug, "hello world")
    await _wait_for(
        lambda: _assistant_messages(conversation.storage, thread.slug)
    )

    assert ai_mock.request_count >= 1
    assistant = _assistant_messages(conversation.storage, thread.slug)[0]
    assert assistant.message.content == "Echo: hello world"
    assert assistant.message.reasoning
    assert assistant.usage is not None
    assert assistant.usage.cost == MOCK_COST
    assert assistant.usage.total_tokens > 0
    assert conversation.status == "idle"

    registry.delete_conversation(conversation_id)


async def test_tool_call_is_logged(ai_mock):
    def echo(arguments):
        return "got:" + str(arguments.get("value"))

    tools.register_tool(
        tools.Tool(
            name="test_echo",
            description="Echo a value back",
            function=echo,
        )
    )

    conversation_id = uuid.uuid4().hex
    registry.register_config(
        ConversationConfig(id=conversation_id, model="chat")
    )
    conversation = registry.get_conversation(conversation_id)
    thread = conversation.create_thread("Chat")

    await conversation.send(thread.slug, '[[tool:test_echo {"value": "hi"}]]')

    def actions_ready():
        return any(
            isinstance(entry, ActionEntry)
            for entry in conversation.storage.read(thread.slug)
        )

    await _wait_for(actions_ready)
    await _wait_for(
        lambda: len(_assistant_messages(conversation.storage, thread.slug)) >= 2
    )

    actions = [
        entry
        for entry in conversation.storage.read(thread.slug)
        if isinstance(entry, ActionEntry)
    ]
    assert len(actions) == 1
    assert actions[0].name == "test_echo"
    assert actions[0].arguments == {"value": "hi"}
    assert actions[0].status == "ok"
    assert actions[0].result == "got:hi"

    assistant = _assistant_messages(conversation.storage, thread.slug)
    assert assistant[-1].message.content == "Echo: got:hi"

    registry.delete_conversation(conversation_id)


async def test_two_threads_are_both_processed(ai_mock):
    conversation_id = uuid.uuid4().hex
    registry.register_config(
        ConversationConfig(id=conversation_id, model="chat")
    )
    conversation = registry.get_conversation(conversation_id)
    first = conversation.create_thread("First")
    second = conversation.create_thread("Second")

    await conversation.send(first.slug, "alpha")
    await conversation.send(second.slug, "beta")

    await _wait_for(
        lambda: _assistant_messages(conversation.storage, first.slug)
        and _assistant_messages(conversation.storage, second.slug)
    )
    assert (
        _assistant_messages(conversation.storage, first.slug)[0].message.content
        == "Echo: alpha"
    )
    assert (
        _assistant_messages(conversation.storage, second.slug)[
            0
        ].message.content
        == "Echo: beta"
    )
    registry.delete_conversation(conversation_id)


async def test_empty_and_unknown_threads_are_rejected(ai_mock):
    conversation_id = uuid.uuid4().hex
    registry.register_config(
        ConversationConfig(id=conversation_id, model="chat")
    )
    conversation = registry.get_conversation(conversation_id)
    thread = conversation.create_thread("Chat")

    with pytest.raises(ValueError):
        await conversation.send(thread.slug, "   ")
    with pytest.raises(KeyError):
        await conversation.send("does-not-exist", "hi")
    registry.delete_conversation(conversation_id)


async def test_maybe_unload_drops_idle_conversation(ai_mock):
    conversation_id = uuid.uuid4().hex
    registry.register_config(
        ConversationConfig(id=conversation_id, model="chat")
    )
    conversation = registry.get_conversation(conversation_id)
    assert registry.peek_conversation(conversation_id) is conversation
    conversation.maybe_unload()
    if ai.unload_when_idle():
        assert registry.peek_conversation(conversation_id) is None
    registry.delete_conversation(conversation_id)
