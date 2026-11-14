# SPDX-License-Identifier: GPL-3.0-or-later
"""Server level settings shared by every AI provider integration.

Values are stored in ``<vardir>/core.settings/ai_settings.toml`` and
published through :mod:`kaithem.src.settings_overrides`.  That means code
reads them with the ordinary settings API (``get_val``/``subscribe_to_changes``)
and a config file entry or config resource can still override them.

Editing happens through the Kaithem settings page.  Changing a value takes
effect immediately, with no server restart, because the file is reloaded by
writing the new value into ``settings_overrides`` at the same priority.

The API key is the only secret here.  It is written with mode 600 and never
logged.
"""

from __future__ import annotations

import os

import structlog
from scullery import persist

from . import directories, settings_overrides

logger = structlog.get_logger(__name__)

#: Priority for values stored in the AI settings file.  It sits above the
#: shipped config file (10) but below config resources (50), so a module can
#: still pin a value deliberately.
FILE_PRIORITY = 20

#: Setting keys owned by this module, with their default values.  Defaults
#: are published at priority 0 so a config file entry or a config resource
#: can still override them.
DEFAULTS: dict[str, str] = {
    "core/ai/openrouter_api_key": "",
    "core/ai/openrouter_api_base": "https://openrouter.ai/api/v1",
    "core/ai/model_code": "z-ai/glm-5.3-flash",
    "core/ai/model_chat": "google/gemini-3.1-flash-lite",
    "core/ai/model_image": "meta/muse-image",
    "core/ai/model_speech": "bytedance-seed/seed-audio-1-0",
    "core/ai/model_sound_effects": "bytedance-seed/seed-audio-1-0",
    "core/ai/conversations_dir": "~/.local/kaithem/conversations",
    "core/ai/unload_conversations_when_idle": "true",
}

#: Short labels for the settings page.
LABELS: dict[str, str] = {
    "core/ai/openrouter_api_key": "OpenRouter API Key",
    "core/ai/openrouter_api_base": "OpenRouter API Base URL",
    "core/ai/model_code": 'Default "code" model',
    "core/ai/model_chat": 'Default "chat" model',
    "core/ai/model_image": 'Default "image" model',
    "core/ai/model_speech": 'Default "speech" model',
    "core/ai/model_sound_effects": 'Default "sound_effects" model',
    "core/ai/conversations_dir": "Conversation storage folder",
    "core/ai/unload_conversations_when_idle": "Unload idle conversations",
}

#: Help text for the settings page.
DESCRIPTIONS: dict[str, str] = {
    "core/ai/openrouter_api_key": (
        "Secret key used to talk to OpenRouter.  Leave empty to disable AI "
        "features.  Stored in the Kaithem var dir with owner only access."
    ),
    "core/ai/openrouter_api_base": (
        "Base URL of the OpenAI compatible API.  Point this at a local mock "
        "to test without the paid service."
    ),
    "core/ai/model_code": (
        'Model id used when a conversation asks for the "code" tag.'
    ),
    "core/ai/model_chat": (
        'Model id used when a conversation asks for the "chat" tag.'
    ),
    "core/ai/model_image": (
        'Image generation model used when a tool asks for the "image" tag.'
    ),
    "core/ai/model_speech": (
        'Text to speech model used when a tool asks for the "speech" tag.'
    ),
    "core/ai/model_sound_effects": (
        "Model used for the sound_effects mode of the audio generation tool."
    ),
    "core/ai/conversations_dir": (
        "Where append only conversation history lives.  Defaults to the "
        "user's home folder, deliberately outside the Kaithem var dir."
    ),
    "core/ai/unload_conversations_when_idle": (
        "Drop conversations from memory once the last client disconnects and "
        "any background work has finished.  History is never deleted."
    ),
}

#: Tags that stand in for a provider specific model id.  Setting a
#: conversation's model to one of these resolves through the setting on the
#: right.  "image", "speech", and "sound_effects" are used by the media
#: generation tools rather than by the chat model itself.
MODEL_TAGS: dict[str, str] = {
    "code": "core/ai/model_code",
    "chat": "core/ai/model_chat",
    "image": "core/ai/model_image",
    "speech": "core/ai/model_speech",
    "sound_effects": "core/ai/model_sound_effects",
}

#: Boolean settings that read as true.
_TRUE_VALUES = ("1", "true", "yes", "on")

FILE = os.path.join(directories.vardir, "core.settings", "ai_settings.toml")


def _load_file() -> dict[str, str]:
    """Read the AI settings file, tolerating a missing or broken file."""
    if not os.path.exists(FILE):
        return {}
    try:
        data = persist.load(FILE)
    except Exception:
        logger.exception("Could not read AI settings file %s", FILE)
        return {}
    if not isinstance(data, dict):
        logger.error("AI settings file %s was not a mapping", FILE)
        return {}
    return {str(key): str(value) for key, value in data.items()}


def _register_defaults() -> None:
    for key, value in DEFAULTS.items():
        settings_overrides.add_val(key, value, "<ai defaults>", 0)
    for key, description in DESCRIPTIONS.items():
        settings_overrides.set_description(key, description)


_file_values = _load_file()
_register_defaults()
for _key, _value in _file_values.items():
    settings_overrides.add_val(
        _key, _value, "<ai settings file>", FILE_PRIORITY
    )


def get_value(key: str) -> str:
    """Return the effective value of an AI setting."""
    if key not in DEFAULTS:
        raise KeyError(f"Unknown AI setting {key!r}")
    return settings_overrides.get_val(key) or DEFAULTS[key]


def set_value(key: str, value: str) -> None:
    """Persist an AI setting and publish it immediately."""
    if key not in DEFAULTS:
        raise KeyError(f"Unknown AI setting {key!r}")
    value = value.strip()
    _file_values[key] = value
    _save_file()
    settings_overrides.add_val(key, value, "<ai settings file>", FILE_PRIORITY)
    logger.info("Updated AI setting %s", key)


def _save_file() -> None:
    data = {key: value for key, value in _file_values.items() if value}
    try:
        persist.save(data, FILE, private=True)
    except Exception:
        logger.exception("Could not write AI settings file %s", FILE)
        raise


def get_api_key() -> str:
    return get_value("core/ai/openrouter_api_key")


def get_api_base() -> str:
    """OpenRouter base URL without a trailing slash."""
    return get_value("core/ai/openrouter_api_base").rstrip("/")


def get_conversations_dir() -> str:
    return os.path.expanduser(get_value("core/ai/conversations_dir"))


def unload_when_idle() -> bool:
    value = get_value("core/ai/unload_conversations_when_idle").lower()
    return value in _TRUE_VALUES


def resolve_model(name: str) -> str:
    """Turn a model tag into a concrete model id.

    A name that matches a tag ("code", "chat") resolves through the matching
    setting.  Anything else is treated as a literal model id.  An empty name
    falls back to the chat model.
    """
    name = name.strip()
    key = MODEL_TAGS.get(name)
    if key is not None:
        return get_value(key)
    if not name:
        return get_value(MODEL_TAGS["chat"])
    return name
