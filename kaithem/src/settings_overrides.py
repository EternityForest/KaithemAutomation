import threading

import beartype

from . import config

# This is a dict that indexes the setting name
# and the values are more dicts.  The keys of those are tuples: priority, source
# and the values are the actual values
settings: dict[str, dict[tuple[float, str], str]] = {}
lock = threading.RLock()


def list_keys() -> list[str]:
    """List all known setting keys"""
    with lock:
        return list(settings.keys())


def get_cfg_val(key: str) -> str:
    "Returns the highest priority setting for the key"
    with lock:
        if key in settings:
            p = sorted(list(settings[key].keys()))
            if p:
                return settings[key][p[-1]]
    return ""


@beartype.beartype
def add_cfg_val(key: str, value: str, source: str = "<code>", priority: float | int = 0):
    """Add a value for the given key.   If empty string, remove it instead.
    The one with the highest priority is the one that is returned.
    Note that this does not save anything to disk.

    Priorities:
    0= Default
    50= Config File
    """

    value = value.strip()

    with lock:
        if key not in settings:
            settings[key] = {}

        if value:
            settings[key][priority, source] = value
        else:
            try:
                del settings[key][priority, source]
            except KeyError:
                pass


with lock:
    for i in config.config:
        if isinstance(config.config[i], str) and "_" in i or "." in i:
            add_cfg_val(f"core.{i}", config.config[i], "<Config file>", 10)
