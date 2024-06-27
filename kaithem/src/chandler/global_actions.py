from __future__ import annotations

# This file provides the shortcut code and event functions
import traceback
from typing import TYPE_CHECKING, Any

from . import core

if TYPE_CHECKING:
    from .cue import Cue
    from .groups import Group

# Index Cues by codes that we use to jump to them. This is a dict of lists of cues with that short code,
shortcut_codes: dict[str, list[Cue]] = {}


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

    return str(code)


def trigger_shortcut_code(code: str, limitGroup: Group | None = None, exclude: Group | None = None):
    "API to activate a cue by it's shortcut code"

    code = normalize_shortcut(code)

    if not limitGroup:
        event("shortcut." + str(code)[:64], None)

    go_list = []
    event_list = []

    # Do as little as possible under the lock
    with core.lock:
        if code in shortcut_codes:
            for i in shortcut_codes[code]:
                try:
                    x = i.group()
                    if not x:
                        continue

                    if limitGroup:
                        if (x is not limitGroup) and not (x.name == limitGroup):
                            print("skip " + x.name, limitGroup)
                            continue
                        if x is not exclude:
                            # x.event("shortcut." + str(code)[:64])
                            event_list.append((x, str(code)[:64]))
                    else:
                        if x and x is not exclude:
                            # x.go()
                            # x.goto_cue(i.name, cause="manual")
                            go_list.append((x, i.name))
                except Exception:
                    print(traceback.format_exc())

    for i in go_list:
        i[0].goto_cue(i[1], cause="manual")

    for i in event_list:
        i[0].event("shortcut." + i[1], None)


def event(s: str, value: Any = None, info: str = "") -> None:
    "THIS IS THE ONLY TIME THE INFO THING DOES ANYTHING"
    # disallow_special(s, allow=".")
    event_list = []
    with core.lock:
        for board in core.iter_boards():
            for i in board.active_groups:
                event_list.append(i)

    for i in event_list:
        i._event(s, value=value, info=info)
