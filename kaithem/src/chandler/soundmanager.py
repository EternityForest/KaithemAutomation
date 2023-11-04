import threading
from . import core
from ..kaithemobj import kaithem

soundActionSerializer = threading.RLock()

soundActionQueue = []


# We must serialize sound actions to avoid a race condition where the stop
# Happens before the start, causing the sound to keep going
def doSoundAction(g):
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


def play_sound(*args, **kwargs):
    if core.ratelimit.limit():

        def doFunction():
            kaithem.sound.play(*args, **kwargs)
            # kaithem.sound.wait()

        doSoundAction(doFunction)


def stopSound(*args, **kwargs):
    if core.ratelimit.limit():

        def doFunction():
            kaithem.sound.stop(*args, **kwargs)

        doSoundAction(doFunction)


def fadeSound(*args, **kwargs):
    if core.ratelimit.limit():

        def doFunction():
            kaithem.sound.fade_to(*args, **kwargs)

        doSoundAction(doFunction)
    else:
        # A bit of a race condition here, if the sound had not started yet. But if we are triggering rate limit we
        # have other issues.
        kaithem.sound.stop(kwargs["handle"])
