from __future__ import annotations
import threading
from kaithem.src.chandler import thread

from structlog import get_logger

# This file provides the shortcut code and event functions
import traceback
from typing import TYPE_CHECKING, Any
from collections.abc import Callable
from weakref import ref
import time

from . import core

if TYPE_CHECKING:
    from .cue import Cue
    from .groups import Group

_logger = get_logger()
_sc_code_lock = threading.Lock()
# Index Cues by codes that we use to jump to them. This is a dict of lists of cues with that short code,
_shortcut_codes: dict[str, list[ref[ShortcutCodeListener]]] = {}


class ShortcutCodeListener:
    def __init__(
        self, code: str, 
        callback: Callable[[str, float, dict[str, Any]], None],
        description:str=""
    ):
        self.closed = False
        self.code = code
        self.description = description
        self._callback = callback
        with _sc_code_lock:
            if code in _shortcut_codes:
                _shortcut_codes[code].append(ref(self))
            else:
                _shortcut_codes[code] = [ref(self)]

            self._callback = callback

    def close(self):
        self.closed = True
        with _sc_code_lock:
            try:
                _shortcut_codes[self.code].remove(ref(self))
            except ValueError:
                pass

            if not _shortcut_codes[self.code]:
                del _shortcut_codes[self.code]
    
    def go(self, t: float|None=None, props: dict[str, Any]|None=None):
        self._callback(self.code, t or time.time(), props or {})

    def __del__(self):
        if not self.closed:  # coverage: ignore
            _logger.warning("Shortcut code listener not closed", code=self.code)
            self.close()


def normalize_shortcut(code: str | int | float) -> str:
    # Normalize away any trailing zeroes if it's a float
    try:
        code = round(float(code), 4)
        c2 = int(code)

        if code == c2:
            code = c2
        code = str(code)
    except Exception:
        pass

    x =  str(code)
    if len(x)>64:
        raise ValueError("Shortcut code too long")
    return x


@core.cl_context.entry_point
def cl_trigger_shortcut_code(
    code: str, props: dict[str, Any] = {})
    "API to activate a cue by it's shortcut code"

    code = normalize_shortcut(code)

    cl_event("shortcut." + code, None)

    go_list = []
    event_list = []

    with _sc_code_lock:
        if code in _shortcut_codes:
            handlers = list(_shortcut_codes[code])
        else:
            handlers: list[ref[ShortcutCodeListener]] = []

    for i in handlers:
        try:
            x = i()
            if x:
                x.go()
                
        except Exception:
            print(traceback.format_exc())

    for i in go_list:
        i[0].goto_cue(i[1], cause="shortcut")

    for i in event_list:
        i[0].event("shortcut." + i[1], None)


@core.cl_context.entry_point
def cl_event(s: str, value: Any = None, info: str = "", ts=None) -> None:
    "THIS IS THE ONLY TIME THE INFO THING DOES ANYTHING"
    # disallow_special(s, allow=".")
    event_list = []
    for board in core.iter_boards():
        for i in board.active_groups:
            event_list.append(i)

    for i in event_list:
        i._event(s, value=value, info=info, ts=ts)


def async_event(s: str, value: Any = None, info: str = "") -> None:
    def f():
        cl_event(s, value, info)

    core.serialized_async_with_core_lock(f)
