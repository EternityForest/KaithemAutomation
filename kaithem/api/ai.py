# SPDX-License-Identifier: GPL-3.0-or-later
"""Public API for the server level AI provider settings.

Plugins read the configured API key, base URL, storage folder, and model
tags through here rather than poking at internals::

    from kaithem.api import ai

    ai.get_api_key()
    ai.resolve_model("chat")  # -> "google/gemini-3.1-flash-lite"

The same module also exposes one shot agent queries.  :func:`agent_query`
asks a configured ``conversation`` resource one question on a throwaway
agent, with none of the chat history::

    from kaithem.api import ai

    answer = ai.agent_query("reviewer", "Summarize the changelog")
    ai.agent_query("reviewer", "Draft a reply", callback=on_reply)

``agent_query`` is provided by the ``CorePluginPydanticConversation``
plugin and imported lazily, so this module still imports when the plugin
is absent.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from kaithem.src.ai_settings import (
    DEFAULTS,
    DESCRIPTIONS,
    LABELS,
    MODEL_TAGS,
    get_api_base,
    get_api_key,
    get_conversations_dir,
    get_value,
    resolve_model,
    set_value,
    unload_when_idle,
)

if TYPE_CHECKING:
    from kaithem.src.plugins.CorePluginPydanticConversation.agent_api import (
        AgentRunInfo,
    )

__all__ = [
    "DEFAULTS",
    "DESCRIPTIONS",
    "LABELS",
    "MODEL_TAGS",
    "AgentRunInfo",
    "agent_query",
    "get_api_base",
    "get_api_key",
    "get_conversations_dir",
    "get_value",
    "resolve_model",
    "set_value",
    "unload_when_idle",
]


def _agent_api() -> Any:
    from kaithem.src.plugins.CorePluginPydanticConversation import agent_api

    return agent_api


def __getattr__(name: str) -> Any:
    """Expose the plugin's ``AgentRunInfo`` lazily as an attribute."""
    if name == "AgentRunInfo":
        return _agent_api().AgentRunInfo
    raise AttributeError(name)


def agent_query(
    agent_id: str,
    prompt: str,
    output_type: Any = None,
    callback: Callable[[Any, AgentRunInfo], None] | None = None,
) -> Any:
    """Ask a configured agent one question, with no persisted history.

    ``agent_id`` names a ``conversation`` resource.  The query runs on an
    ephemeral agent built from that resource's settings and writes
    nothing to disk.  ``output_type`` accepts anything pydantic-ai does.
    With no ``callback`` it runs synchronously and returns the output;
    with one it runs in the background and calls
    ``callback(output, AgentRunInfo)``.
    """
    return _agent_api().agent_query(agent_id, prompt, output_type, callback)
