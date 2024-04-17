from kaithem.src import settings_overrides


def list_keys() -> list[str]:
    return settings_overrides.list_keys()


def get_val(key: str) -> str:
    "Returns the highest priority setting for the key"
    return settings_overrides.get_val(key)


def add_val(key: str, value: str, source: str = "<code>", priority: float | int = 0):
    return settings_overrides.add_val(key, value, source, priority)
