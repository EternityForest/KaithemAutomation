import atexit
import threading
import time

import icemedia.sound_player
from scullery import messagebus

from . import ChandlerConsole, core, scene_lighting, universes

logger = core.logger
soundLock = threading.Lock()


# Locals for performance... Is this still a thing??
float = float
abs = abs
int = int
max = max
min = min


def refresh_scenes(t, v):
    """Tell scenes the set of universes has changed"""
    with core.lock:
        for b in core.iter_boards():
            for i in b.active_scenes:
                i.lighting_manager.refresh()


messagebus.subscribe("/chandler/command/refresh_scene_lighting", refresh_scenes)


def refreshFixtures(topic, val):
    # Deal with fixtures in this universe that aren't actually attached to this object yet.
    for i in range(5):
        try:
            with core.lock:
                for i in universes.fixtures:
                    f = universes.fixtures[i]()
                    if not f:
                        continue
                    if f.universe == val or val is None:
                        f.assign(f.universe, f.startAddress)
            break
        except RuntimeError:
            # Should there be some kind of dict changed size problem, retry
            time.sleep(0.1)


messagebus.subscribe("/chandler/command/refreshFixtures", refreshFixtures)


def pollsounds():
    for b in core.iter_boards():
        for i in b.active_scenes:
            # If the cuelen isn't 0 it means we are using the newer version that supports randomizing lengths.
            # We keep this in case we get a sound format we can'r read the length of in advance
            if i.cuelen == 0:
                # Forbid any crazy error loopy business with too short sounds
                if (time.time() - i.entered_cue) > 1 / 5:
                    if i.cue.sound and i.cue.rel_length:
                        if not i.media_ended_at:
                            if not icemedia.sound_player.is_playing(str(i.id)):
                                i.media_ended_at = time.time()
                        if i.media_ended_at and (time.time() - i.media_ended_at > (i.cue.length * i.bpm)):
                            i.next_cue(cause="sound")


def poll_board_scenes(board: ChandlerConsole.ChandlerConsole, t=None):
    "Poll scenes in the board"
    t = t or time.time()

    # Remember that scenes get rendered in ascending priority order here
    for i in board.active_scenes:
        # We don't need to call render() if the frame is a static scene and the opacity
        # and all that is the same, we can just re-layer it on top of the values
        if i.poll_again_flag or (i.cue.length and ((time.time() - i.entered_cue) > i.cuelen * (60 / i.bpm))):
            i.poll_again_flag = False
            i.poll()


lastrendered = 0


controluniverse = universes.Universe("control")
varsuniverse = universes.Universe("__variables__")

run = [True]


def loop():
    global lastrendered

    # This function is apparently slightly slow?
    u_cache = universes.getUniverses()
    u_cache_time = time.time()

    while run[0]:
        t = time.time()
        try:
            # Profiler says this needs a cache
            if t - u_cache_time > 1:
                u_cache = universes.getUniverses()
                u_cache_time = t

            do_gui_push = False
            if t - lastrendered > 1 / 14.0:
                with core.lock:
                    pollsounds()
                do_gui_push = True
                lastrendered = t

            with core.lock:
                changed = {}

                # The pre-render step has to
                # happen before we start compositing on the layers

                for b in core.iter_boards():
                    poll_board_scenes(b)
                    changed.update(scene_lighting.pre_render(b, u_cache))

                for b in core.iter_boards():
                    c = scene_lighting.composite_layers_from_board(b, u=u_cache)
                    changed.update(c)

                    if do_gui_push:
                        b.guiPush(u_cache)

                scene_lighting.do_output(changed, u_cache)

            time.sleep(1 / 60)
        except Exception:
            logger.exception("Wat")


thread = threading.Thread(target=loop, name="ChandlerThread", daemon=True)
thread.start()


def STOP(*a):
    run[0] = False


atexit.register(STOP)
messagebus.subscribe("/system/shutdown", STOP)
