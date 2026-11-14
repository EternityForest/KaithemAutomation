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
import shutil
import tempfile
import time
import uuid
from urllib.parse import quote, unquote

import pytest
from pydantic_ai import Tool
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from kaithem.api import ai, settings
from kaithem.src.plugins import CorePluginPydanticConversation as plugin
from kaithem.src.plugins.CorePluginPydanticConversation import (
    agent as agent_module,
)
from kaithem.src.plugins.CorePluginPydanticConversation import (
    conversation as registry,
)
from kaithem.src.plugins.CorePluginPydanticConversation.models import (
    DEFAULT_USER,
    ActionEntry,
    ChatEntry,
    ChatMessage,
    ConversationConfig,
    ThreadHeader,
    ToolCall,
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
from kaithem.src.tests.ai_mock import start_ai_mock

from .helpers import make_client

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


def _wire_messages(request: dict) -> list[dict]:
    """The messages of one provider request, without any system prompt."""
    return [
        message
        for message in request["messages"]
        if message.get("role") != "system"
    ]


def _register_tool(conversation_id: str, function, name: str) -> None:
    """Attach one callable tool to a conversation for its next run."""
    registry.register_capabilities(
        conversation_id,
        [
            Tool(
                function,
                name=name,
                description="Echo a value back for the test",
            )
        ],
    )


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


def test_safe_user_rejects_traversal():
    for bad in ("", ".", "..", "a/b", "a\\b", "a\x00b"):
        with pytest.raises(ValueError):
            ConversationStorage(CONV_DIR, uuid.uuid4().hex, bad)


def test_storage_defaults_to_the_system_user():
    storage = ConversationStorage(CONV_DIR, uuid.uuid4().hex)
    assert storage.user == DEFAULT_USER


def test_storage_isolates_users():
    conversation_id = uuid.uuid4().hex
    alice = ConversationStorage(CONV_DIR, conversation_id, "alice")
    thread = alice.create_thread("Chat")
    assert alice.user == "alice"

    bob = ConversationStorage(CONV_DIR, conversation_id, "bob")
    assert bob.list_threads() == []
    assert not bob.has_thread(thread.slug)

    # Each user gets a directory of their own under the conversation.
    assert alice.directory != bob.directory
    assert alice.directory == os.path.join(CONV_DIR, conversation_id, "alice")
    assert os.path.isfile(
        os.path.join(alice.directory, thread.slug + ".ldjson")
    )
    assert os.path.isdir(bob.directory) is False


def test_deleting_one_user_leaves_the_other():
    conversation_id = uuid.uuid4().hex
    alice = ConversationStorage(CONV_DIR, conversation_id, "alice")
    alice.create_thread("Chat")
    bob = ConversationStorage(CONV_DIR, conversation_id, "bob")
    bob.create_thread("Chat")

    alice.delete()
    assert not os.path.exists(alice.directory)
    assert os.path.isdir(bob.directory)
    assert [t.slug for t in bob.list_threads()] == ["chat"]


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


# -- message replay -------------------------------------------------------


def _unit_conversation(**kwargs) -> registry.Conversation:
    config = ConversationConfig(id="unit", model="chat", **kwargs)
    return registry.Conversation(config, None)


def test_to_model_messages_maps_roles():
    history = [
        ChatEntry(
            id="1",
            timestamp=1.0,
            thread="t",
            message=ChatMessage(role="user", content="hi"),
        ),
        ChatEntry(
            id="2",
            timestamp=2.0,
            thread="t",
            message=ChatMessage(
                role="assistant", content="hello", reasoning="why"
            ),
        ),
    ]
    messages = agent_module.to_model_messages(history)
    assert isinstance(messages[0], ModelRequest)
    assert isinstance(messages[0].parts[0], UserPromptPart)
    assert messages[0].parts[0].content == "hi"
    assert isinstance(messages[1], ModelResponse)
    # Reasoning is kept on disk but is never replayed to the provider.
    assert [type(part) for part in messages[1].parts] == [TextPart]
    assert messages[1].parts[0].content == "hello"


def test_to_model_messages_replays_tool_results():
    call = ToolCall(id="call_1", name="lookup", arguments='{"key": "a"}')
    history = [
        ChatEntry(
            id="1",
            timestamp=1.0,
            thread="t",
            message=ChatMessage(role="user", content="look it up"),
        ),
        ChatEntry(
            id="2",
            timestamp=2.0,
            thread="t",
            message=ChatMessage(
                role="assistant", content="", tool_calls=[call]
            ),
        ),
        ActionEntry(
            id="3",
            timestamp=3.0,
            thread="t",
            name="lookup",
            tool_call_id="call_1",
            status="ok",
            result="42",
        ),
    ]
    messages = agent_module.to_model_messages(history)
    assert [type(message) for message in messages] == [
        ModelRequest,
        ModelResponse,
        ModelRequest,
    ]
    call_part = messages[1].parts[0]
    assert isinstance(call_part, ToolCallPart)
    assert call_part.tool_name == "lookup"
    assert call_part.args == '{"key": "a"}'
    result_part = messages[2].parts[0]
    assert isinstance(result_part, ToolReturnPart)
    assert result_part.tool_name == "lookup"
    assert result_part.tool_call_id == "call_1"
    assert result_part.content == "42"
    assert result_part.outcome == "success"


def test_to_model_messages_marks_failed_tools():
    call = ToolCall(id="call_2", name="lookup", arguments="{}")
    history = [
        ChatEntry(
            id="1",
            timestamp=1.0,
            thread="t",
            message=ChatMessage(
                role="assistant", content="", tool_calls=[call]
            ),
        ),
        ActionEntry(
            id="2",
            timestamp=2.0,
            thread="t",
            name="lookup",
            tool_call_id="call_2",
            status="error",
            result="boom",
        ),
    ]
    messages = agent_module.to_model_messages(history)
    result_part = messages[1].parts[0]
    assert isinstance(result_part, ToolReturnPart)
    assert result_part.outcome == "failed"


def test_build_agent_without_api_key_raises():
    with pytest.raises(agent_module.MissingApiKeyError):
        agent_module.build_agent(
            model_id="chat", api_base="http://x/v1", api_key=""
        )


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
        lambda: _assistant_messages(conversation.storage(), thread.slug)
    )

    assert ai_mock.request_count >= 1
    assistant = _assistant_messages(conversation.storage(), thread.slug)[0]
    assert assistant.message.content == "Echo: hello world"
    assert assistant.usage is not None
    assert assistant.usage.total_tokens > 0
    assert conversation.status == "idle"

    registry.delete_conversation(conversation_id)


async def test_tool_call_is_logged(ai_mock):
    def echo(value: str) -> str:
        return "got:" + value

    conversation_id = uuid.uuid4().hex
    registry.register_config(
        ConversationConfig(id=conversation_id, model="chat")
    )
    _register_tool(conversation_id, echo, "test_echo")
    conversation = registry.get_conversation(conversation_id)
    thread = conversation.create_thread("Chat")

    await conversation.send(thread.slug, '[[tool:test_echo {"value": "hi"}]]')

    def actions_ready():
        return any(
            isinstance(entry, ActionEntry)
            for entry in conversation.storage().read(thread.slug)
        )

    def replies_ready():
        return (
            len(_assistant_messages(conversation.storage(), thread.slug)) >= 2
        )

    await _wait_for(actions_ready)
    await _wait_for(replies_ready)

    actions = [
        entry
        for entry in conversation.storage().read(thread.slug)
        if isinstance(entry, ActionEntry)
    ]
    assert len(actions) == 1
    assert actions[0].name == "test_echo"
    assert actions[0].arguments == {"value": "hi"}
    assert actions[0].status == "ok"
    assert actions[0].result == "got:hi"

    assistant = _assistant_messages(conversation.storage(), thread.slug)
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
        lambda: _assistant_messages(conversation.storage(), first.slug)
        and _assistant_messages(conversation.storage(), second.slug)
    )
    first_reply = _assistant_messages(conversation.storage(), first.slug)
    second_reply = _assistant_messages(conversation.storage(), second.slug)
    assert first_reply[0].message.content == "Echo: alpha"
    assert second_reply[0].message.content == "Echo: beta"
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


# -- per user behaviour ---------------------------------------------------


async def test_users_do_not_share_threads(ai_mock):
    conversation_id = uuid.uuid4().hex
    registry.register_config(
        ConversationConfig(id=conversation_id, model="chat")
    )
    conversation = registry.get_conversation(conversation_id)

    alice = conversation.create_thread("Alice Chat", user="alice")
    bob = conversation.create_thread("Bob Chat", user="bob")
    assert alice.slug == "alice-chat"
    assert bob.slug == "bob-chat"

    assert [t.slug for t in conversation.list_threads("alice")] == [
        "alice-chat"
    ]
    assert [t.slug for t in conversation.list_threads("bob")] == ["bob-chat"]
    # Web users never see, or write to, the internal namespace.
    assert conversation.list_threads() == []
    with pytest.raises(KeyError):
        conversation.get_entries(alice.slug, user="bob")
    with pytest.raises(KeyError):
        await conversation.send(alice.slug, "sneaky", user="bob")

    await conversation.send(
        alice.slug, "hello alice", author="alice", user="alice"
    )
    await _wait_for(
        lambda: _assistant_messages(conversation.storage("alice"), alice.slug)
    )
    assert conversation.storage("alice").list_threads()[0].message_count == 2
    assert conversation.storage("bob").list_threads()[0].message_count == 0

    # The talking user is recorded on their own message.
    entries = conversation.get_entries(alice.slug, user="alice")
    user_messages = [
        e
        for e in entries
        if e["type"] == "message" and e["message"]["role"] == "user"
    ]
    assert user_messages[0]["author"] == "alice"

    registry.delete_conversation(conversation_id)


def test_listeners_are_scoped_to_users():
    conversation = _unit_conversation()
    events: dict[str, list[dict]] = {"alice": [], "bob": []}

    def alice_event(event: dict) -> None:
        events["alice"].append(event)

    def bob_event(event: dict) -> None:
        events["bob"].append(event)

    conversation.add_listener("alice", alice_event)
    conversation.add_listener("bob", bob_event)

    conversation.create_thread("Chat", user="alice")
    assert len(events["alice"]) == 1
    assert events["bob"] == []

    # Status changes are broadcasts, they reach every user.
    conversation._set_status("thinking")
    assert len(events["bob"]) == 1
    assert len(events["alice"]) == 2

    # Removing a listener stops further deliveries to that user.
    conversation.remove_listener("alice", alice_event)
    conversation.create_thread("Second", user="alice")
    assert len(events["alice"]) == 2


async def test_multi_turn_replays_history(ai_mock):
    conversation_id = uuid.uuid4().hex
    registry.register_config(
        ConversationConfig(id=conversation_id, model="chat")
    )
    conversation = registry.get_conversation(conversation_id)
    thread = conversation.create_thread("Chat")

    await conversation.send(thread.slug, "first")
    await _wait_for(
        lambda: len(_assistant_messages(conversation.storage(), thread.slug))
        == 1
    )

    await conversation.send(thread.slug, "second")
    await _wait_for(
        lambda: len(_assistant_messages(conversation.storage(), thread.slug))
        == 2
    )

    request = ai_mock.last_request
    assert request is not None
    replay = _wire_messages(request)
    assert [m["role"] for m in replay] == ["user", "assistant", "user"]
    assert replay[0]["content"] == "first"
    assert replay[1]["content"] == "Echo: first"
    assert replay[2]["content"] == "second"

    registry.delete_conversation(conversation_id)


async def test_tool_result_is_replayed_to_provider(ai_mock):
    def echo(value: str) -> str:
        return "got:" + value

    conversation_id = uuid.uuid4().hex
    registry.register_config(
        ConversationConfig(id=conversation_id, model="chat")
    )
    _register_tool(conversation_id, echo, "replay_echo")
    conversation = registry.get_conversation(conversation_id)
    thread = conversation.create_thread("Chat")

    await conversation.send(thread.slug, '[[tool:replay_echo {"value": "hi"}]]')
    await _wait_for(
        lambda: len(_assistant_messages(conversation.storage(), thread.slug))
        >= 2
    )

    # The second request of the run has to carry the assistant tool call
    # and its matching tool result, otherwise the provider would reject a
    # later turn.
    request = ai_mock.last_request
    assert request is not None
    replay = _wire_messages(request)
    assert [m["role"] for m in replay] == ["user", "assistant", "tool"]
    call = replay[1]["tool_calls"][0]
    assert call["function"]["name"] == "replay_echo"
    assert replay[2]["tool_call_id"] == call["id"]
    assert replay[2]["content"] == "got:hi"

    registry.delete_conversation(conversation_id)


def test_delete_conversation_removes_every_users_history(ai_mock):
    conversation_id = uuid.uuid4().hex
    registry.register_config(
        ConversationConfig(id=conversation_id, model="chat")
    )
    conversation = registry.get_conversation(conversation_id)
    conversation.create_thread("Chat", user="alice")
    conversation.create_thread("Chat", user="bob")
    directory = os.path.join(CONV_DIR, conversation_id)
    assert os.path.isdir(os.path.join(directory, "alice"))
    assert os.path.isdir(os.path.join(directory, "bob"))

    registry.delete_conversation(conversation_id)
    assert not os.path.exists(directory)
    assert registry.get_config(conversation_id) is None


# -- workspace conversations ----------------------------------------------


def test_workspace_conversation_id_encodes_the_whole_path():
    conversation_id = plugin.workspace_conversation_id("/srv/site")
    assert conversation_id == "admin.%2Fsrv%2Fsite"
    assert conversation_id.startswith(plugin.WORKSPACE_ID_PREFIX)
    assert "/" not in conversation_id
    # The same folder always maps to the same id.
    assert conversation_id == plugin.workspace_conversation_id("/srv/site")
    # The id travels in URLs as an opaque token, so quoting it once more
    # and unquoting must land back on the very same id.
    assert unquote(quote(conversation_id, safe="")) == conversation_id


@pytest.fixture
def workspace():
    """A throwaway server folder under the /dev/shm test sandbox."""
    path = tempfile.mkdtemp(dir="/dev/shm/kaithem_tests")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


async def test_workspace_route_rejects_guests(workspace):
    from kaithem.src import quart_app

    client = quart_app.app.test_client(use_cookies=True)
    response = await client.get(
        "/conversations", query_string={"workspace": workspace}
    )
    assert response.status_code == 403


async def test_workspace_route_requires_a_folder(ai_mock):
    client = await make_client()
    missing = "/dev/shm/kaithem_tests/this-folder-does-not-exist"
    response = await client.get(
        "/conversations", query_string={"workspace": missing}
    )
    assert response.status_code == 400


async def test_workspace_route_creates_the_conversation(ai_mock, workspace):
    client = await make_client()
    response = await client.get(
        "/conversations", query_string={"workspace": workspace}
    )
    assert response.status_code == 302
    path = os.path.realpath(workspace)
    conversation_id = plugin.workspace_conversation_id(path)
    try:
        config = registry.get_config(conversation_id)
        assert config is not None
        assert config.workspace == path
        assert config.permissions == ["system_admin"]
        # The redirect points the chat page at the auto-created id.
        assert quote(conversation_id, safe="") in response.headers["location"]
        # Asking again reuses the same conversation.
        again = await client.get(
            "/conversations", query_string={"workspace": workspace}
        )
        assert again.status_code == 302
        assert registry.get_config(conversation_id) is config
    finally:
        registry.delete_conversation(conversation_id)
