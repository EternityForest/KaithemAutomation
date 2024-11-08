from __future__ import annotations

import logging
import os
import sys
import threading
import time
import traceback
import unicodedata
import weakref
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import structlog
import textdistance
from icemedia import sound_player
from scullery import workers
from tinytag import TinyTag

from .. import context_restrictions
from ..kaithemobj import kaithem
from . import console_abc

if TYPE_CHECKING:
    from . import ChandlerConsole

# when the last time we logged an error, so we can ratelimit
last_logged_error = 0

started_frame_number = 0
completed_frame_number = 0


# This lock covers the actual compositing of values.
# Use it so you can mark something for rerender but make sure
# it gets the new values.

# It also covers some universe and fixture data, and can be held for any updates
# you want to apply all at once, as long as you do not ever get any other lock under
# It

# It does not cover any other part of rendering
# You have to NEVER get a group lock, or the cl_context
# while holding this.  It should only be held extremely briefly

# When running under a debugger actually enforce the ordering
if "debugpy" in sys.modules:
    render_loop_lock = context_restrictions.Context(
        "RenderLoopLock", exclusive=True, bottom_level=True
    )
else:
    render_loop_lock = threading.RLock()


def is_img_file(path: str):
    if path.endswith(
        (".png", ".jpg", ".webp", ".png", ".heif", ".tiff", ".gif", ".svg")
    ):
        return True


def get_audio_duration(path: str) -> float | None:
    "Get duration of media file"
    # Try with tinytag before dragging in ffmpeg
    try:
        x = TinyTag.get(path).duration or 0
    except Exception:
        x = 0

    if x > 0:
        return x

    import ffmpeg

    try:
        info = ffmpeg.probe(path)
        return float(info["format"]["duration"])
    except Exception:
        print(traceback.format_exc())
    return None


def rl_log_exc(m: str):
    print(m)
    global last_logged_error
    if last_logged_error < time.monotonic() - 5 * 60:
        logging.exception(m)
    last_logged_error = time.monotonic()


cl_context = context_restrictions.Context(
    "ChandlerCoreLock", exclusive=True, timeout=5 * 60
)


logger = structlog.get_logger(__name__)

saveLocation = os.path.join(kaithem.misc.vardir, "chandler")


# Shared info that other modules use, it's here to avoid circular dependencies
# Store the fixtures info


fixtureschanged = {}
controlValues = weakref.WeakValueDictionary()


def disallow_special(
    s: str, allow: str = "", replaceMode: str | None = None
) -> str:
    for i in "[]{}()!@#$%^&*()<>,./;':\"-=+\\|`~?\r\n\t":
        if i in s and i not in allow:
            if replaceMode is None:
                raise ValueError(
                    "Special char "
                    + i
                    + " not allowed in this context(full str starts with "
                    + s[:100]
                    + ")"
                )
            else:
                s = s.replace(i, replaceMode)
    return s


musicLocation = os.path.join(kaithem.misc.vardir, "chandler", "music")


"""Only change this under core.cl_context"""
boards: dict[str, ChandlerConsole.ChandlerConsole] = {}


def iter_boards():
    try:
        for i in boards:
            yield boards[i]
    except RuntimeError:
        # TODO should we actually handle this?
        pass


def add_data_pusher_to_all_boards(
    func: Callable[[console_abc.Console_ABC], Any],
):
    """Add a function to every lightboard, which will be called from within it's
    GUI loop and passed the board as first param"""
    for board in iter_boards():
        if len(board.newDataFunctions) < 100:
            board.newDataFunctions.append(func)


if not os.path.exists(musicLocation):
    try:
        os.makedirs(musicLocation, mode=0o755)
    except Exception:
        logger.exception("Could not make music dir")


def getSoundFolders(extra_folders: list[str] | None = None) -> dict[str, str]:
    "path:displayname dict"
    soundfolders: dict[str, str] = {}

    soundfolders[kaithem.assetpacks.assetlib] = "Online Assets Library"

    soundfolders[os.path.join(kaithem.misc.datadir, "static")] = "Builtin"
    soundfolders[musicLocation] = "Chandler music folder"
    for i in [i for i in kaithem.sound.directories if not i.startswith("__")]:
        soundfolders[i] = i

    modulesdata = os.path.join(kaithem.misc.vardir, "modules", "data")
    if os.path.exists(modulesdata):
        for i in os.listdir(modulesdata):
            x = os.path.join(
                kaithem.misc.vardir,
                "modules",
                "data",
                i,
                "__filedata__",
                "media",
            )
            if os.path.exists(x):
                soundfolders[x] = "Module:" + i + "/media"

    if extra_folders:
        for i in extra_folders:
            soundfolders[i] = i

    return soundfolders


def resolve_sound(sound: str, extra_folders: list[str] | None = None) -> str:
    # Allow relative paths
    if not sound.startswith("/"):
        for i in getSoundFolders(extra_folders):
            if os.path.isfile(os.path.join(i, sound)):
                sound = os.path.join(i, sound)
    if not sound.startswith("/"):
        sound = sound_player.resolve_sound(sound)
    return sound


# https://stackoverflow.com/questions/517923/what-is-the-best-way-to-remove-accents-normalize-in-a-python-unicode-string
LATIN = "ä  æ  ǽ  đ ð ƒ ħ ı ł ø ǿ ö  œ  ß  ŧ ü  Ä  Æ  Ǽ  Đ Ð Ƒ Ħ I Ł Ø Ǿ Ö  Œ  ẞ  Ŧ Ü "
ASCII = "ae ae ae d d f h i l o o oe oe ss t ue AE AE AE D D F H I L O O OE OE SS T UE"


def remove_diacritics(
    s, outliers=str.maketrans(dict(zip(LATIN.split(), ASCII.split())))
):  # type: ignore
    return "".join(
        c
        for c in unicodedata.normalize("NFD", s.translate(outliers))
        if not unicodedata.combining(c)
    )


def simplify_name(n):
    "Remove fancy chars for the fuzzy matcher to work."
    for i in "_-;:'/+=?! ":
        n = n.replace(i, "")
    n = n.replace("$", "s")
    n = remove_diacritics(n)

    return n.lower()


def resolve_sound_fuzzy(
    sound: str, extra_folders: list[str] | None = None
) -> str:
    try:
        s = resolve_sound(sound)
        if s and os.path.exists(s):
            return s
    except Exception:
        pass

    sound = simplify_name(os.path.basename(sound))

    # Allow relative paths
    if not os.path.exists(sound):
        for i in getSoundFolders(extra_folders):
            if os.path.isfile(os.path.join(i, sound)):
                sound = os.path.join(i, sound)
            else:
                for dirpath, dirnames, filenames in os.walk(i):
                    for j in filenames:
                        if (
                            textdistance.damerau_levenshtein(
                                simplify_name(j), sound
                            )
                            < 2
                        ):
                            sound = os.path.join(dirpath, j)

    if not sound.startswith("/"):
        sound = sound_player.resolve_sound(sound)
    return sound


class RateLimiter:
    def __init__(self) -> None:
        self.t = 0
        self.c = 0

    def limit(self):
        self.c = min(32, self.c + ((time.monotonic() - self.t) * 12))

        self.c -= 1
        self.t = time.monotonic()

        if self.c < 5:
            time.sleep(0.3)
        if self.c < 3:
            time.sleep(1)
        elif self.c < 1:
            return 0

        return 1


ratelimit = RateLimiter()


action_queue = []
action_queue_lock = threading.RLock()

next_frame_action_queue = []


def serialized_async_with_core_lock(f):
    """Do f in bg thread. Events are delayed but guaranteed to be processed in order.
    Note that this can block the frame rendering loop, the frame won't advance till all
    events that happened during the last frame have been processed.
    """

    def g():
        with cl_context:
            f()

    action_queue.append(g)

    def h():
        with action_queue_lock:
            while action_queue:
                action_queue.pop(False)()

    workers.do(h)


def serialized_async_next_frame(f):
    next_frame_action_queue.append(f)


# Only call from main loop
def process_next_frame_actions():
    while next_frame_action_queue:
        x = next_frame_action_queue.pop(0)
        serialized_async_with_core_lock(x)


def wait_frame():
    "Waits until at least the frame after this one has been completed"
    global started_frame_number, completed_frame_number
    s = started_frame_number
    while completed_frame_number < s + 1:
        time.sleep(0.01)
