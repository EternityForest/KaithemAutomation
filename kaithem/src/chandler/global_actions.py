from __future__ import annotations

# This file provides the shortcut code and event functions
import traceback
from typing import TYPE_CHECKING, Any

from . import core

if TYPE_CHECKING:
    from .cue import Cue
    from .scenes import Scene

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


def shortcutCode(code: str, limitScene: Scene | None = None, exclude: Scene | None = None):
    "API to activate a cue by it's shortcut code"

    code = normalize_shortcut(code)

    if not limitScene:
        event("shortcut." + str(code)[:64], None)

    with core.lock:
        if code in shortcut_codes:
            for i in shortcut_codes[code]:
                try:
                    x = i.scene()
                    if not x:
                        continue

                    if limitScene:
                        if (x is not limitScene) and not (x.name == limitScene):
                            print("skip " + x.name, limitScene)
                            continue
                        if x is not exclude:
                            x.event("shortcut." + str(code)[:64])
                    else:
                        if x and x is not exclude:
                            x.go()
                            x.goto_cue(i.name, cause="manual")
                except Exception:
                    print(traceback.format_exc())


def event(s: str, value: Any = None, info: str = "") -> None:
    "THIS IS THE ONLY TIME THE INFO THING DOES ANYTHING"
    # disallow_special(s, allow=".")
    with core.lock:
        for board in core.iter_boards():
            for i in board.active_scenes:
                i._event(s, value=value, info=info)
