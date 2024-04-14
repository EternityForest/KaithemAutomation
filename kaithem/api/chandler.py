from typing import Any, Callable

from kaithem.src import chandler as _chandler


def add_command(name: str, f: Callable):
    """Add a command which will be available in the
    Logic Editor.  Params should be strings.  Defaults and
    docstrings will be used.
    """
    _chandler.rootContext.commands[name] = f


def trigger_event(event: str, value: Any = None):
    "Trigger an event in all scenes"
    _chandler.event(event, value)


def shortcut(s: str):
    """Trigger a shortcut code.  All matching cues will be jumped to."""
    _chandler.shortcutCode(s)