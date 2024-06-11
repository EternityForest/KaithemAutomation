from typing import Any, Callable

from kaithem.src.chandler import global_actions as _global_actions
from kaithem.src.chandler import scenes as _scenes


def add_command(name: str, f: Callable):
    """Add a command which will be available in the
    Logic Editor.  Params should be strings.  Defaults and
    docstrings will be used.
    """
    _scenes.rootContext.commands[name] = f


def trigger_event(event: str, value: Any = None):
    "Trigger an event in all scenes"
    _global_actions.event(event, value)


def shortcut(s: str):
    """Trigger a shortcut code.  All matching cues will be jumped to."""
    _global_actions.shortcutCode(s)
