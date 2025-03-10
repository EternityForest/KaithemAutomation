import functools
import threading
from typing import Any

import beartype
from scullery import messagebus

from . import config

# This is a dict that indexes the setting name
# and the values are more dicts.  The keys of those are tuples: priority, source
# and the values are the actual values
settings: dict[str, dict[tuple[float, str], str]] = {}
lock = threading.RLock()


settings_meta: dict[str, dict[str, Any]] = {}

config_loaded_from_resources = False

suggestions_by_key: dict[str, list[tuple[str, str]]] = {}


def add_suggestion(key: str, value: str, description: str = ""):
    """Add a suggestion for the given key"""
    key = normalize_key(key)
    with lock:
        if key not in suggestions_by_key:
            suggestions_by_key[key] = []

        suggestions_by_key[key].append((value, description))


def clear_suggestions(key: str):
    key = normalize_key(key)
    if key in suggestions_by_key:
        del suggestions_by_key[key]


def set_description(key: str, description: str):
    key = normalize_key(key)
    set_meta(key, "description", description)


@functools.lru_cache(256)
def normalize_key(key: str) -> str:
    if key.startswith("/"):
        key = key[1:]
    key = key.lower()
    key = key.replace("  ", " ")
    key = key.replace("  ", " ")
    key = key.replace(" ", "_")
    key = key.replace("-", "_")

    return key


def set_meta(key: str, metakey: str, val: Any):
    key = normalize_key(key)
    with lock:
        settings_meta[key] = settings_meta.get(key, {})
        settings_meta[key][metakey] = val


def get_meta(key: str):
    key = normalize_key(key)
    try:
        return settings_meta[key]
    except KeyError:
        return {}


def list_keys() -> list[str]:
    """List all known setting keys"""
    with lock:
        added = set()
        r = []
        for i in settings:
            if i not in added:
                added.add(i)
                r.append(i)
        for i in settings_meta:
            if i not in added:
                r.append(i)
                added.add(i)
        for i in suggestions_by_key:
            if i not in added:
                r.append(i)
                added.add(i)
        return r


@functools.lru_cache(32)
def get_by_prefix(prefix: str) -> dict[str, str]:
    r = {}
    prefix = normalize_key(prefix)
    with lock:
        lst = list_keys()
        for i in lst:
            if i.startswith(prefix):
                v = get_val(i)
                if v:
                    r[i] = v
        return r


@functools.lru_cache(256)
def get_val(key: str) -> str:
    "Returns the highest priority setting for the key"
    key = normalize_key(key)
    with lock:
        if key in settings:
            p = sorted(list(settings[key].keys()))
            if p:
                return settings[key][p[-1]]
    return ""


@beartype.beartype
def add_val(
    key: str, value: str, source: str = "<code>", priority: float | int = 0
):
    """Add a value for the given key.   If empty string, remove it instead.
    The one with the highest priority is the one that is returned.
    Note that this does not save anything to disk.

    Priorities:
    0= Default
    50= Config File
    """

    key = normalize_key(key)
    value = value.strip()

    old = get_val(key)

    with lock:
        if key not in settings:
            settings[key] = {}

        for i in list(settings[key]):
            if i[1] == source:
                settings[key].pop(i, None)

        if value:
            settings[key][priority, source] = value

        if len(settings[key]) == 0:
            del settings[key]

        get_val.cache_clear()
        get_by_prefix.cache_clear()

    if old != get_val(key):
        messagebus.post_message("/system/config/changed", key)


with lock:
    for i in config.config:
        if isinstance(config.config[i], (str, int, float)) and "/" in i:
            add_val(i, str(config.config[i]), "<Config file>", 10)
