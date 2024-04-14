import threading

# This is a dict that indexes the setting name
# and the values are more dicts.  The keys of those are tuples: priority, source
# and the values are the actual values
settings: dict[str, dict[tuple[float, str], str]] = {}
lock = threading.RLock()


def get_cfg_val(key: str):
    "Returns the highest priority setting for the key"
    with lock:
        if key in settings:
            p = sorted(list(settings[key].keys()))
            if p:
                return p[-1]


def add_cfg_val(key: str, value: str, source: str = "<code>", priority: float | int = 0):
    """Add a value for the given key.   If empty string, remove it instead.
    The one with the highest priority is the one that is returned.
    Note that this does not save anything to disk.
    """

    value = value.strip()

    with lock:
        if key not in settings:
            settings[key] = {}

        if value:
            settings[key][priority, source] = value
        else:
            try:
                settings[key][priority, source]
            except KeyError:
                pass
