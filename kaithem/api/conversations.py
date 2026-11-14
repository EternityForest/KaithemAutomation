# SPDX-License-Identifier: GPL-3.0-or-later
"""Public API for Pydantic agentic conversations.

Conversations are provided by the ``CorePluginPydanticConversation``
plugin.  This module is a thin, stable facade so other plugins and user
code can create conversations, attach tools, and reach an existing
conversation without importing plugin internals::

    from kaithem.api import conversations

    config = conversations.ConversationConfig(
        id="reviewer", model="chat", workspace="/srv/site"
    )
    conversations.register_config(config)
    conversations.register_capabilities("reviewer", [my_toolset])
    conversation = conversations.get_conversation("reviewer")

A conversation with a ``workspace`` gets the file system harness pointed
at that folder, so the model can read and edit files there.  Extra tools
and capabilities are attached with :func:`register_capabilities`.  They
are live objects, so they are kept out of the config, which is written to
disk.

Imports of the plugin happen lazily inside the functions so that this
module can be imported even if the plugin is not present.

Conversation threads are namespaced per user.  Every listing and sending
method takes an optional ``user`` argument that defaults to
:data:`DEFAULT_USER` (``__system__``), so programmatic callers keep a
private namespace while the web UI passes the authenticated user.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kaithem.src.plugins.CorePluginPydanticConversation.conversation import (  # noqa: E501
        Conversation,
    )
    from kaithem.src.plugins.CorePluginPydanticConversation.models import (
        DEFAULT_USER,
        ConversationConfig,
        ThreadInfo,
        Usage,
    )

__all__ = [
    "DEFAULT_USER",
    "Conversation",
    "ConversationConfig",
    "ThreadInfo",
    "Usage",
    "clear_capabilities",
    "delete_conversation",
    "get_capabilities",
    "get_config",
    "get_conversation",
    "list_configs",
    "peek_conversation",
    "register_capabilities",
    "register_config",
    "unload",
    "unregister_config",
]


def _models() -> Any:
    from kaithem.src.plugins.CorePluginPydanticConversation import models

    return models


def _registry() -> Any:
    from kaithem.src.plugins.CorePluginPydanticConversation import (
        conversation,
    )

    return conversation


def __getattr__(name: str) -> Any:
    """Expose the plugin's model classes lazily as attributes."""
    if name in ("ConversationConfig", "ThreadInfo", "Usage", "DEFAULT_USER"):
        return getattr(_models(), name)
    if name == "Conversation":
        return _registry().Conversation
    raise AttributeError(name)


def register_capabilities(
    conversation_id: str, capabilities: Sequence[Any]
) -> None:
    """Attach live pydantic-ai tools/capabilities to a conversation.

    They are used by every later run of the conversation until replaced.
    Pass an empty sequence to clear them.
    """
    _registry().register_capabilities(conversation_id, capabilities)


def get_capabilities(conversation_id: str) -> list[Any]:
    """The capabilities currently attached to a conversation."""
    return _registry().get_capabilities(conversation_id)


def clear_capabilities(conversation_id: str) -> None:
    """Forget any capabilities attached to a conversation."""
    _registry().clear_capabilities(conversation_id)


def register_config(config: ConversationConfig) -> None:
    """Register a conversation config, making it reachable by id."""
    _registry().register_config(config)


def unregister_config(conversation_id: str) -> None:
    _registry().unregister_config(conversation_id)


def get_config(conversation_id: str) -> ConversationConfig | None:
    return _registry().get_config(conversation_id)


def get_conversation(conversation_id: str) -> Conversation:
    return _registry().get_conversation(conversation_id)


def peek_conversation(conversation_id: str) -> Conversation | None:
    return _registry().peek_conversation(conversation_id)


def unload(conversation_id: str) -> None:
    _registry().unload(conversation_id)


def delete_conversation(conversation_id: str) -> None:
    _registry().delete_conversation(conversation_id)


def list_configs() -> list[ConversationConfig]:
    return _registry().list_configs()
