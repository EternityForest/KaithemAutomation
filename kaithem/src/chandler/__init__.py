import time
import weakref
import threading
import traceback
import numpy

from .WebChandlerConsole import WebConsole
from .scenes import Scene, event, shortcutCode

from ..kaithemobj import kaithem
from . import core
from . import universes
from . import blendmodes
from . import scenes
from .universes import getUniverses
from .scenes import rootContext


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
        for i in scenes.activeScenes:
            # Attempt to restart all scenes.
            # Try to put them back in the same state
            # A lot of things are written assuming the list stays constant,
            # this is needed for refreshing.
            x = i.started
            y = i.enteredCue
            i.stop()
            i.go()
            i.render()
            i.started = x
            i.enteredCue = y


kaithem.message.subscribe("/chandler/command/refreshScenes", refresh_scenes)


def refreshFixtures(topic, val):
    # Deal with fixtures in this universe that aren't actually attached to this object yet.
    for i in range(0, 5):
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


kaithem.message.subscribe("/chandler/command/refreshFixtures", refreshFixtures)






def pollsounds():
    for i in scenes.activeScenes:
        # If the cuelen isn't 0 it means we are using the newer version that supports randomizing lengths.
        # We keep this in case we get a sound format we can'r read the length of in advance
        if i.cuelen == 0:
            # Forbid any crazy error loopy business with too short sounds
            if (time.time() - i.enteredCue) > 1 / 5:
                if i.cue.sound and i.cue.rel_length:
                    if not kaithem.sound.isPlaying(str(i.id)) and not i.sound_end:
                        i.sound_end = time.time()
                    if i.sound_end and (
                        time.time() - i.sound_end > (i.cue.length * i.bpm)
                    ):
                        i.nextCue(cause="sound")



def composite(background, values, alphas, alpha):
    "In place compositing of one universe as a numpy array on a background.  Returns background."
    background = background * (1 - (alphas * alpha)) + values * alphas * alpha
    return background


def applyLayer(universe, uvalues, scene, uobj):
    "May happen in place, or not, but always returns the new version"

    if universe not in scene.canvas.v2:
        return uvalues

    vals = scene.canvas.v2[universe]
    alphas = scene.canvas.a2[universe]

    # The universe may need to know when it's current fade should end,
    # if it handles fading in a different way.
    # This will look really bad for complex things, to try and reduce them to a series of fades,
    # but we just do the best we can, and assume there's mostly only 1 scene at a time affecting things
    uobj.fadeEndTime = max(
        uobj.fadeEndTime, scene.cue.fadein + scene.enteredCue)

    ualphas = uobj.alphas

    if scene.blend == "normal":
        # todo: is it bad to multiply by bool?
        unsetVals = ualphas == 0.0
        fade = numpy.maximum(scene.alpha, unsetVals & uobj.hueBlendMask)

        uvalues = composite(uvalues, vals, alphas, fade)
        # Essetially calculate remaining light percent, then multiply layers and convert back to alpha
        ualphas = 1 - ((1 - (alphas * fade)) * (1 - (ualphas)))

    elif scene.blend == "HTP":
        uvalues = numpy.maximum(uvalues, vals * (alphas * scene.alpha))
        ualphas = (alphas * scene.alpha) > 0

    elif scene.blend == "inhibit":
        uvalues = numpy.minimum(uvalues, vals * (alphas * scene.alpha))
        ualphas = (alphas * scene.alpha) > 0

    elif scene.blend == "gel" or scene.blend == "multiply":
        if scene.alpha:
            # precompute constants
            c = 255 / scene.alpha
            uvalues = (uvalues * (1 - alphas * scene.alpha)) + \
                (uvalues * vals) / c

            # COMPLETELY incorrect, but we don't use alpha for that much, and the real math
            # Is compliccated. #TODO
            ualphas = (alphas * scene.alpha) > 0

    elif scene._blend:
        try:
            uvalues = scene._blend.frame(
                universe, uvalues, vals, alphas, scene.alpha)
            # Also incorrect-ish, but treating modified vals as fully opaque is good enough.
            ualphas = (alphas * scene.alpha) > 0
        except Exception:
            print("Error in blend function")
            print(traceback.format_exc())
    uobj.alphas = ualphas
    return uvalues


def pre_render():
    "Reset all universes to either the all 0s background or the cached layer, depending on if the cache layer is still valid"
    # Here we find out what universes can be reset to a cached layer and which need to be fully rerendered.
    changedUniverses = {}
    to_reset = {}

    universes = getUniverses()

    # Important to reverse, that way scenes that need a full reset come after and don't get overwritten
    for i in reversed(scenes.activeScenes):
        for u in i.affect:
            if u in universes:
                universe = universes[u]
                universe.all_static = True
                if i.rerender:
                    changedUniverses[u] = (0, 0)

                    # We are below the cached layer, we need to fully reset
                    if (i.priority, i.started) <= universe.prerendered_layer:
                        to_reset[u] = 1
                    else:
                        # We are stacking on another layer or changing the top layer. We don't need
                        # To rerender the entire stack, we just start from the prerendered_layer
                        # Set the universe to the state it was in just after the prerendered layer was rendered.
                        # Since the values are mutable, we need to set this back every frame

                        # Don't overwrite a request to reset the entire thing
                        if not to_reset.get(u, 0) == 1:
                            to_reset[u] = 2
    for u in universes:
        if universes[u].full_rerender:
            to_reset[u] = 1

        universes[u].fadeEndTime = 0
        universes[u].interpolationTime = 0

    for u in to_reset:
        if (to_reset[u] == 1) or not universes[u].prerendered_layer[1]:
            universes[u].reset()
            changedUniverses[u] = (0, 0)
        else:
            universes[u].reset_to_cache()
            changedUniverses[u] = (0, 0)
    return changedUniverses


def render(t=None):
    "This is the primary rendering function"
    changedUniverses = pre_render()

    t = t or time.time()

    universesSnapshot = getUniverses()

    # Remember that scenes get rendered in ascending priority order here
    for i in scenes.activeScenes:
        # We don't need to call render() if the frame is a static scene and the opacity
        # and all that is the same, we can just re-layer it on top of the values
        if i.rerender or (
            i.cue.length and ((time.time() - i.enteredCue)
                              > i.cuelen * (60 / i.bpm))
        ):
            i.rerender = False
            i.render()

        if i.blend == "monitor":
            i.updateMonitorValues()
            continue

        data = i.affect

        # Loop over universes the scene affects
        for u in data:
            if u.startswith("__") and u.endswith("__"):
                continue

            if u not in universesSnapshot:
                continue

            universeObject = universesSnapshot[u]

            # If this is above the prerendered stuff we try to avoid doing every frame
            if (i.priority, i.started) > universeObject.top_layer:
                # If this layer we are about to render was found to be the highest layer that likely won't need rerendering,
                # Save the state just befor we apply that layer.
                if (
                    universeObject.save_before_layer == (i.priority, i.started)
                ) and not ((i.priority, i.started) == (0, 0)):
                    universeObject.save_prerendered(
                        universeObject.top_layer[0], universeObject.top_layer[1]
                    )

                changedUniverses[u] = (i.priority, i.started)
                universeObject.values = applyLayer(
                    u, universeObject.values, i, universeObject
                )
                universeObject.top_layer = (i.priority, i.started)

                # If this is the first nonstatic layer, meaning it's render function requested a rerender next frame
                # or if this is the last one, mark it as the one we should save just before
                if i.rerender or (i is scenes.activeScenes[-1]):
                    if universeObject.all_static:
                        # Copy it and set to none as a flag that we already found it
                        universeObject.all_static = False
                        universeObject.save_before_layer = universeObject.top_layer

    for i in changedUniverses:
        try:
            if i in universesSnapshot:
                x = universesSnapshot[i]
                x.preFrame()
                x.onFrame()
        except Exception:
            raise

    for i in universesSnapshot:
        universesSnapshot[i].full_rerender = False
    changedUniverses = {}




def getAllDeviceTagPoints():
    o = {}
    for i in kaithem.devices:
        o[i] = {}
        for j in kaithem.devices[i].tagpoints:
            o[i][j] = [
                kaithem.devices[i].tagpoints[j].name,
                kaithem.devices[i].tagpoints[j].subtype,
            ]







lastrendered = 0


board = WebConsole()
core.boards.append(weakref.ref(board))
core.board = board


class ObjPlugin:
    board = board
    Scene = Scene
    scenesByUUID = scenes.scenes
    scenes = scenes.scenes_by_name
    Universe = universes.Universe
    blendmodes = blendmodes.blendmodes
    fixture = universes.Fixture
    shortcut = shortcutCode
    commands = rootContext.commands
    event = event


k_interface = ObjPlugin()
kaithem.chandler = k_interface

def nbr():
    return (
        50,
        '<a href="/chandler/commander"><i class="icofont-cheer-leader"></i>Chandler</a>',
    )


kaithem.web.navBarPlugins["chandler"] = nbr

def nbr2():
    return (50, '<a href="/chandler/editor"><i class="icofont-pencil"></i>Editor</a>')

kaithem.web.navBarPlugins["chandler2"] = nbr2




controluniverse = universes.Universe("control")
varsuniverse = universes.Universe("__variables__")


def loop():
    while 1:
        try:
            with core.lock:
                render()

            global lastrendered
            if time.time() - lastrendered > 1 / 14.0:
                with core.lock:
                    pollsounds()

                    for i in core.boards:
                        b = i()
                        if b:
                            b.guiPush()
                        del b
                lastrendered = time.time()
            time.sleep(1 / 60)
        except Exception:
            logger.exception("Wat")


thread = threading.Thread(target=loop, name="ChandlerThread", daemon=True)
thread.start()
