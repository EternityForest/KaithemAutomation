from kaithem.src import settings_overrides


def list_keys() -> list[str]:
    """List all known setting keys"""
    return settings_overrides.list_keys()


def get_val(key: str) -> str:
    "Returns the highest priority setting for the key"
    return settings_overrides.get_val(key)


def add_val(
    key: str, value: str, source: str = "<code>", priority: float | int = 0
):
    """Add a config option.   If value is empty string, remove it instead."""
    return settings_overrides.add_val(key, value, source, priority)
