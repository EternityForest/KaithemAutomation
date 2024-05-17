import threading
import time

import cherrypy
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
    """Stop and restart all active scenes, because some caches might need to be updated
    when a new universes is added
    """
    with core.lock:
        for b in core.iter_boards():
            for i in b.active_scenes:
                # Attempt to restart all scenes.
                # Try to put them back in the same state
                # A lot of things are written assuming the list stays constant,
                # this is needed for refreshing.
                x = i.started
                y = i.entered_cue
                i.stop()
                i.go()
                i.poll()
                i.started = x
                i.entered_cue = y


messagebus.subscribe("/chandler/command/refreshScenes", refresh_scenes)


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
    # This function is apparently slightly slow?
    u_cache = universes.getUniverses()
    u = universes.universes
    u_id = id(u)

    while run[0]:
        try:
            if not u_id == id(universes.universes):
                u_cache = universes.getUniverses()
                u = universes.universes
                u_id = id(u)

            with core.lock:
                for b in core.iter_boards():
                    poll_board_scenes(b)
                    scene_lighting.composite_layers_and_do_output(b)

            global lastrendered
            if time.time() - lastrendered > 1 / 14.0:
                with core.lock:
                    pollsounds()
                    for b in core.iter_boards():
                        b.guiPush(u_cache)

                lastrendered = time.time()
            time.sleep(1 / 60)
        except Exception:
            logger.exception("Wat")


thread = threading.Thread(target=loop, name="ChandlerThread", daemon=True)
thread.start()


def STOP():
    run[0] = False


cherrypy.engine.subscribe("stop", STOP, priority=10)
