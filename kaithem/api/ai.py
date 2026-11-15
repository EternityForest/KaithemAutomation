# SPDX-License-Identifier: GPL-3.0-or-later
"""Public API for the server level AI provider settings.

Plugins read the configured API key, base URL, storage folder, and model
tags through here rather than poking at internals::

    from kaithem.api import ai

    ai.get_api_key()
    ai.resolve_model("chat")  # -> "google/gemini-3.1-flash-lite"
"""

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

__all__ = [
    "DEFAULTS",
    "DESCRIPTIONS",
    "LABELS",
    "MODEL_TAGS",
    "get_api_base",
    "get_api_key",
    "get_conversations_dir",
    "get_value",
    "resolve_model",
    "set_value",
    "unload_when_idle",
]
