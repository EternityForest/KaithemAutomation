import threading
from . import core
from ..kaithemobj import kaithem
from functools import wraps
from typing import List, Callable, Any, Optional

soundActionSerializer = threading.RLock()

soundActionQueue: List[Callable[..., Any]] = []


# We must serialize sound actions to avoid a race condition where the stop
# Happens before the start, causing the sound to keep going
def doSoundAction(g: Callable[..., Any]):
    soundActionQueue.append(g)

    def f():
        if soundActionSerializer.acquire(timeout=25):
            try:
                while soundActionQueue:
                    x = soundActionQueue.pop(False)
                    x()
            finally:
                soundActionSerializer.release()

    kaithem.misc.do(f)


@wraps(kaithem.sound.play)
def play_sound(filename: str,
               handle: str = "PRIMARY",
               extraPaths: List[str] = [],
               volume: float = 1,
               output: Optional[str] = "",
               loop: float = 1,
               start: float = 0,
               speed: float = 1):
    if core.ratelimit.limit():

        def doFunction():
            kaithem.sound.play(filename=filename,
                               handle=handle,
                               extraPaths=extraPaths,
                               volume=volume,
                               output=output,
                               loop=loop,
                               start=start,
                               speed=speed)
            # kaithem.sound.wait()

        doSoundAction(doFunction)


def stop_sound(handle: str = "PRIMARY"):
    if core.ratelimit.limit():

        def doFunction():
            kaithem.sound.stop(handle)

        doSoundAction(doFunction)


def fadeSound(file: str | None,
              length: float = 1.0,
              block: bool = False,
              handle: str = "PRIMARY",
              output: Optional[str] = "",
              volume: float = 1,
              windup: float = 0,
              winddown: float = 0,
              loop: int = 1,
              start: float = 0,
              speed: float = 1):
    if core.ratelimit.limit():

        def doFunction():
            kaithem.sound.fade_to(file,
                                  length=length,
                                  block=block,
                                  handle=handle,
                                  output=output or '',
                                  volume=volume,
                                  windup=windup,
                                  winddown=winddown,
                                  loop=loop,
                                  start=start,
                                  speed=speed)

        doSoundAction(doFunction)
    else:
        # A bit of a race condition here, if the sound had not started yet. But if we are triggering rate limit we
        # have other issues.
        kaithem.sound.stop(handle)
