import threading
from functools import wraps
from typing import Any, Callable, List, Optional

from icemedia import sound_player
from scullery import workers

from . import core

soundActionSerializer = threading.RLock()

soundActionQueue: List[Callable[..., Any]] = []


# We must serialize sound actions to avoid a race condition where the stop
# Happens before the start, causing the sound to keep going
def doSoundAction(g: Callable[..., Any]):
    soundActionQueue.append(g)

    def f():
        if soundActionSerializer.acquire(timeout=5):
            try:
                while soundActionQueue:
                    x = soundActionQueue.pop(False)
                    x()
            finally:
                soundActionSerializer.release()

    workers.do(f)


@wraps(sound_player.play_sound)
def play_sound(
    filename: str,
    handle: str = "PRIMARY",
    extraPaths: List[str] = [],
    volume: float = 1,
    output: Optional[str] = "",
    loop: float = 1,
    start: float = 0,
    speed: float = 1,
):
    if core.ratelimit.limit():

        def doFunction():
            sound_player.play_sound(
                filename=filename,
                handle=handle,
                extraPaths=extraPaths,
                volume=volume,
                output=output,
                loop=loop,
                start=start,
                speed=speed,
            )

        doSoundAction(doFunction)


def stop_sound(handle: str = "PRIMARY"):
    def doFunction():
        sound_player.stop_sound(handle)

    doSoundAction(doFunction)


def fadeSound(
    file: str | None,
    length: float = 1.0,
    block: bool = False,
    handle: str = "PRIMARY",
    output: Optional[str] = "",
    volume: float = 1,
    windup: float = 0,
    winddown: float = 0,
    loop: int = 1,
    start: float = 0,
    speed: float = 1,
):
    if core.ratelimit.limit():

        def doFunction():
            sound_player.fade_to(
                file,
                length=length,
                block=block,
                handle=handle,
                output=output or "",
                volume=volume,
                windup=windup,
                winddown=winddown,
                loop=loop,
                start=start,
                speed=speed,
            )

        doSoundAction(doFunction)
    else:
        # A bit of a race condition here, if the sound had not started yet. But if we are triggering rate limit we
        # have other issues.
        sound_player.stop_sound(handle)
