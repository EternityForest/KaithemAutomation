
import os
import threading
import time
import weakref
import logging
import traceback
from tinytag import TinyTag
from ..kaithemobj import kaithem
from typing import Optional, Dict, List

from . import console_abc

# when the last time we logged an error, so we can ratelimit
lastSysloggedError = 0


def is_img_file(path: str):
    if (path.endswith(".png")
        or path.endswith(".jpg")
        or path.endswith(".webp")
        or path.endswith(".png")
        or path.endswith(".heif")
        or path.endswith(".tiff")
        or path.endswith(".gif")
            or path.endswith(".svg")):
        return True


def get_audio_duration(path: str) -> Optional[float]:
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
        info = ffmpeg.probe(filename)
        return info['format']['duration']
    except Exception:
        print(traceback.format_exc())
    return None


def rl_log_exc(m):
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


def disallow_special(s: str, allow: str = "", replaceMode: Optional[str] = None) -> str:
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


config = {
    'soundFolders': [],
}


if os.path.exists(os.path.join(saveLocation, "config.yaml")):
    config.update(kaithem.persist.load(
        os.path.join(saveLocation, "config.yaml")))

musicLocation = os.path.join(kaithem.misc.vardir, "chandler", "music")

boards: List[weakref.ref[console_abc.Console_ABC]] = []


def iter_boards():
    for i in boards:
        x = i()
        if x:
            yield x


if not os.path.exists(musicLocation):
    try:
        os.makedirs(musicLocation, mode=0o755)
    except Exception:
        logger.exception("Could not make music dir")


def getSoundFolders() -> Dict[str, str]:
    "path:displayname dict"
    soundfolders: Dict[str, str] = {
        i.strip(): i.strip() for i in config['soundFolders']}

    soundfolders[kaithem.assetpacks.assetlib] = 'Online Assets Library'

    soundfolders[os.path.join(kaithem.misc.datadir, "sounds")] = 'Builtin'
    soundfolders[musicLocation] = "Chandler music folder"
    for i in [i for i in kaithem.sound.directories if not i.startswith("__")]:
        soundfolders[i] = i

    for i in os.listdir(os.path.join(kaithem.misc.vardir, "modules", 'data')):
        soundfolders[os.path.join(kaithem.misc.vardir, "modules", 'data',
                                  i, "__filedata__", 'media')] = "Module:" + i + "/media"
    return soundfolders


def resolve_sound(sound: str):
    # Allow relative paths
    if not sound.startswith("/"):
        for i in getSoundFolders():
            if os.path.isfile(os.path.join(i, sound)):
                sound = os.path.join(i, sound)
    if not sound.startswith("/"):
        sound = kaithem.sound.resolve_sound(sound)
    return sound


class RateLimiter():
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
