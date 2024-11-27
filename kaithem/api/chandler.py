from typing import Any, Callable

from kaithem.src.chandler import global_actions as _global_actions
from kaithem.src.chandler import groups as _groups
from kaithem.src.chandler.core import serialized_async_with_core_lock


def add_command(name: str, f: Callable):
    """Add a command which will be available in the
    Logic Editor.  Params should be strings.  Defaults and
    docstrings will be used.
    """
    _groups.rootContext.commands[name] = f


def trigger_event(event: str, value: Any = None):
    "Trigger an event in all groups"

    def f():
        _global_actions.cl_event(event, value)

    serialized_async_with_core_lock(f)


def shortcut(s: str):
    """Trigger a shortcut code.  All matching cues will be jumped to."""

    def f():
        _global_actions.cl_trigger_shortcut_code(s)

    serialized_async_with_core_lock(f)
