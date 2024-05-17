from __future__ import annotations

import logging
import os
import threading
import time
import traceback
import unicodedata
import weakref
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import textdistance
from tinytag import TinyTag

from ..kaithemobj import kaithem
from . import console_abc

if TYPE_CHECKING:
    from . import ChandlerConsole

# when the last time we logged an error, so we can ratelimit
lastSysloggedError = 0


def is_img_file(path: str):
    if path.endswith((".png", ".jpg", ".webp", ".png", ".heif", ".tiff", ".gif", ".svg")):
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
        return info["format"]["duration"]
    except Exception:
        print(traceback.format_exc())
    return None


def rl_log_exc(m: str):
    print(m)
    global lastSysloggedError
    if lastSysloggedError < time.monotonic() - 5 * 60:
        logging.exception(m)
    lastSysloggedError = time.monotonic()


lock = threading.RLock()
logger = logging.getLogger("system.chandler")

saveLocation = os.path.join(kaithem.misc.vardir, "chandler")


# Shared info that other modules use, it's here to avoid circular dependencies
# Store the fictures info


fixtureschanged = {}
controlValues = weakref.WeakValueDictionary()


def disallow_special(s: str, allow: str = "", replaceMode: str | None = None) -> str:
    for i in "[]{}()!@#$%^&*()<>,./;':\"-=+\\|`~?\r\n\t":
        if i in s and i not in allow:
            if replaceMode is None:
                raise ValueError("Special char " + i + " not allowed in this context(full str starts with " + s[:100] + ")")
            else:
                s = s.replace(i, replaceMode)
    return s


config = {
    "sound_folders": [],
}


if os.path.exists(os.path.join(saveLocation, "config.yaml")):
    config.update(kaithem.persist.load(os.path.join(saveLocation, "config.yaml")))

musicLocation = os.path.join(kaithem.misc.vardir, "chandler", "music")

boards: dict[str, ChandlerConsole.ChandlerConsole] = {}


def iter_boards():
    for i in boards:
        yield boards[i]


def add_data_pusher_to_all_boards(func: Callable[[console_abc.Console_ABC], Any]):
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


def getSoundFolders() -> dict[str, str]:
    "path:displayname dict"
    soundfolders: dict[str, str] = {i.strip(): i.strip() for i in config["sound_folders"]}

    soundfolders[kaithem.assetpacks.assetlib] = "Online Assets Library"

    soundfolders[os.path.join(kaithem.misc.datadir, "sounds")] = "Builtin"
    soundfolders[musicLocation] = "Chandler music folder"
    for i in [i for i in kaithem.sound.directories if not i.startswith("__")]:
        soundfolders[i] = i

    modulesdata = os.path.join(kaithem.misc.vardir, "modules", "data")
    if os.path.exists(modulesdata):
        for i in os.listdir(modulesdata):
            soundfolders[os.path.join(kaithem.misc.vardir, "modules", "data", i, "__filedata__", "media")] = "Module:" + i + "/media"
    return soundfolders


def resolve_sound(sound: str) -> str:
    # Allow relative paths
    if not sound.startswith("/"):
        for i in getSoundFolders():
            if os.path.isfile(os.path.join(i, sound)):
                sound = os.path.join(i, sound)
    if not sound.startswith("/"):
        sound = kaithem.sound.resolve_sound(sound)
    return sound


# https://stackoverflow.com/questions/517923/what-is-the-best-way-to-remove-accents-normalize-in-a-python-unicode-string
LATIN = "ä  æ  ǽ  đ ð ƒ ħ ı ł ø ǿ ö  œ  ß  ŧ ü  Ä  Æ  Ǽ  Đ Ð Ƒ Ħ I Ł Ø Ǿ Ö  Œ  ẞ  Ŧ Ü "
ASCII = "ae ae ae d d f h i l o o oe oe ss t ue AE AE AE D D F H I L O O OE OE SS T UE"


def remove_diacritics(s, outliers=str.maketrans(dict(zip(LATIN.split(), ASCII.split())))):
    return "".join(c for c in unicodedata.normalize("NFD", s.translate(outliers)) if not unicodedata.combining(c))


def simplify_name(n):
    "Remove fancy chars for the fuzzy matcher to work."
    for i in "_-;:'/+=?! ":
        n = n.replace(i, "")
    n = n.replace("$", "s")
    n = remove_diacritics(n)

    return n.lower()


def resolve_sound_fuzzy(sound: str) -> str:
    try:
        s = resolve_sound(sound)
        if s and os.path.exists(s):
            return s
    except Exception:
        pass

    sound = simplify_name(os.path.basename(sound))

    # Allow relative paths
    if not os.path.exists(sound):
        for i in getSoundFolders():
            if os.path.isfile(os.path.join(i, sound)):
                sound = os.path.join(i, sound)
            else:
                for dirpath, dirnames, filenames in os.walk(i):
                    for j in filenames:
                        if textdistance.damerau_levenshtein(simplify_name(j), sound) < 2:
                            sound = os.path.join(dirpath, j)

    if not sound.startswith("/"):
        sound = kaithem.sound.resolve_sound(sound)
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
