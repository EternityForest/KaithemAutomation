# SPDX-License-Identifier: GPL-3.0-or-later
"""Public API for Pydantic agentic conversations.

Conversations are provided by the ``CorePluginPydanticConversation``
plugin.  This module is a thin, stable facade so other plugins and user
code can create conversations, register tools, and reach an existing
conversation without importing plugin internals::

    from kaithem.api import conversations

    config = conversations.ConversationConfig(id="...", model="chat")
    conversations.register_config(config)
    conversation = conversations.get_conversation(config.id)

Imports of the plugin happen lazily inside the functions so that this
module can be imported even if the plugin is not present.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kaithem.src.plugins.CorePluginPydanticConversation.conversation import (  # noqa: E501
        Conversation,
    )
    from kaithem.src.plugins.CorePluginPydanticConversation.models import (
        ConversationConfig,
        ThreadInfo,
        Usage,
    )
    from kaithem.src.plugins.CorePluginPydanticConversation.tools import Tool

__all__ = [
    "Conversation",
    "ConversationConfig",
    "ThreadInfo",
    "Tool",
    "Usage",
    "all_tools",
    "delete_conversation",
    "get_config",
    "get_conversation",
    "list_configs",
    "peek_conversation",
    "register_config",
    "register_tool",
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
    if name in ("ConversationConfig", "ThreadInfo", "Usage"):
        return getattr(_models(), name)
    if name == "Conversation":
        return _registry().Conversation
    if name == "Tool":
        from kaithem.src.plugins.CorePluginPydanticConversation.tools import (
            Tool,
        )

        return Tool
    raise AttributeError(name)


def register_tool(tool: Tool) -> None:
    """Add a tool that agentic loops may call."""
    from kaithem.src.plugins.CorePluginPydanticConversation import tools

    tools.register_tool(tool)


def all_tools() -> list[Tool]:
    from kaithem.src.plugins.CorePluginPydanticConversation import tools

    return tools.all_tools()


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
