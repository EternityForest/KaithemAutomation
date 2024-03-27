
from __future__ import annotations
from .core import disallow_special
from .universes import getUniverse, rerenderUniverse, mapUniverse, mapChannel
from ..kaithemobj import kaithem
from .soundmanager import fadeSound, play_sound, stopSound
from . import core
from . import universes
from . import blendmodes
from . import mqtt
from .. import schemas
from .mathutils import number_to_note, dt_to_ts, ease
import numpy
import numpy.typing
from tinytag import TinyTag
from typeguard import typechecked

from decimal import Decimal
import weakref
import base64
import collections
import datetime
import json
import logging
import os
import random
import threading
import time
import traceback
import urllib.parse
import uuid
import gc
from typing import Any, Dict, Optional, Set, Type, Iterable, List, Callable
import copy
import recur

# Locals for performance... Is this still a thing??
float = float
abs = abs
int = int
max = max
min = min

allowedCueNameSpecials = "_~."

scenes: weakref.WeakValueDictionary[str, Scene] = weakref.WeakValueDictionary()
scenes_by_name: weakref.WeakValueDictionary[str,
                                            Scene] = weakref.WeakValueDictionary()

cues: weakref.WeakValueDictionary[str, Cue] = weakref.WeakValueDictionary()

_active_scenes: List[Scene] = []
active_scenes: List[Scene] = []


def is_static_media(s: str):
    "True if it's definitely media that does not have a length"
    for i in ('.bmp', '.jpg', '.html', '.webp', '.php'):
        if s.startswith(i):
            return True

    # Try to detect http stuff
    if not '.' in s.split("?")[0].split("#")[0].split("/")[-1]:
        if not os.path.exists(s):
            return True

    return False


def fnToCueName(fn: str):
    isNum = False
    try:
        int(fn.split(".")[0])
        isNum = True
    except Exception:
        pass

    # Nicely Handle stuff of the form "84. trackname"
    if isNum and len(fn.split(".")) > 2:
        fn = fn.split(".", 1)[-1]

    fn = fn.split(".")[0]

    fn = fn.replace("-", "_")
    fn = fn.replace("_", " ")
    fn = fn.replace(":", " ")

    # Sometimes used as a stylized S
    fn = fn.replace("$", "S")
    fn = fn.replace("@", " at ")

    # Usually going to be the number sign, we can ditch
    fn = fn.replace("#", "")

    # Handle spaces already there or not
    fn = fn.replace(" & ", " and ")
    fn = fn.replace("&", " and ")

    for i in r"""\~!@#$%^&*()+`-=[]\{}|;':"./,<>?""":
        if i not in allowedCueNameSpecials:
            fn = fn.replace(i, "")

    return fn


def makeWrappedConnectionClass(parent: Scene):
    self_closure_ref = parent

    class Connection(mqtt.MQTTConnection):
        def on_connect(self):
            self_closure_ref.event("board.mqtt.connected")
            self_closure_ref.pushMeta(statusOnly=True)
            return super().on_connect()

        def on_disconnect(self):
            self_closure_ref.event("board.mqtt.dis_connected")
            self_closure_ref.pushMeta(statusOnly=True)
            if self_closure_ref.mqtt_server:
                self_closure_ref.event("board.mqtt.error", "Dis_connected")
            return super().on_disconnect()

        def on_message(self, t: str, m: str | bytes):
            if isinstance(m, bytes):
                m2 = m.decode()
            else:
                m2 = str(m)
            gn = self_closure_ref.mqtt_sync_features.get("syncGroup", False)
            if gn:
                topic = f"/kaithem/chandler/syncgroup/{gn}"
                # Leading slash or no, stay compatible
                if t == topic or t == topic[1:]:
                    self_closure_ref.onCueSyncMessage(t, m2)

            self_closure_ref.onMqttMessage(t, m2)

            return super().on_message(t, m)

    return Connection


def makeBlankArray(size: int):
    x = [0] * size
    return numpy.array(x, dtype="f4")


class FadeCanvas:
    def __init__(self):
        """Handles calculating the effect of one scene over a background. 
        This doesn't do blend modes, it just interpolates."""
        self.v: Dict[str, numpy.typing.NDArray[Any]] = {}
        self.a: Dict[str, numpy.typing.NDArray[Any]] = {}
        self.v2: Dict[str, numpy.typing.NDArray[Any]] = {}
        self.a2: Dict[str, numpy.typing.NDArray[Any]] = {}

    def paint(self, fade: float | int, vals: Dict[str, numpy.typing.NDArray[Any]], alphas: Dict[str, numpy.typing.NDArray[Any]]):
        """
        Makes v2 and a2 equal to the current background overlayed 
        with values from scene which is any object that has dicts of dicts of vals and and
        alpha.

        Should you have cached dicts of arrays vals and 
        alpha channels(one pair of arrays per universe), 
        put them in vals and arrays
        for better performance.

        fade is the fade amount from 0 to 1 (from background to the new)

        defaultValue is the default value for a universe. Usually 0.

        """

        # We assume a lot of these lists have the same set of universes. If it gets out of sync you
        # probably have to stop and restart the
        for i in vals:
            effectiveFade = fade
            obj = getUniverse(i)
            # TODO: How to handle nonexistant
            if not obj:
                continue
            # Add existing universes to canvas, skip non existing ones
            if i not in self.v:
                size = len(obj.values)
                self.v[i] = makeBlankArray(size)
                self.a[i] = makeBlankArray(size)
                self.v2[i] = makeBlankArray(size)
                self.a2[i] = makeBlankArray(size)

            # Some universes can disable local fading, like smart bulbs wehere we have remote fading.
            # And we would rather use that. Of course, the disadvantage is we can't properly handle
            # Multiple things fading all at once.
            if not obj.localFading:
                effectiveFade = 1

            # We don't want to fade any values that have 0 alpha in the scene,
            # because that's how we mark "not present", and we want to track the old val.
            # faded = self.v[i]*(1-(fade*alphas[i]))+ (alphas[i]*fade)*vals[i]
            faded = self.v[i] * (1 - effectiveFade) + (effectiveFade * vals[i])

            # We always want to jump straight to the value if alpha was previously 0.
            # That's because a 0 alpha would mean the last scene released that channel, and there's
            # nothing to fade from, so we want to fade in from transparent not from black
            is_new = self.a == 0
            self.v2[i] = numpy.where(is_new, vals[i], faded)

        # Now we calculate the alpha values. Including for
        # Universes the cue doesn't affect.
        for i in self.a:
            effectiveFade = fade
            obj = getUniverse(i)
            # TODO ?
            if not obj:
                continue
            if not obj.localFading:
                effectiveFade = 1
            if i not in alphas:
                aset = 0
            else:
                aset = alphas[i]
            self.a2[i] = self.a[i] * (1 - effectiveFade) + effectiveFade * aset

    def save(self):
        self.v = copy.deepcopy(self.v2)
        self.a = copy.deepcopy(self.a2)

    def clean(self, affect: Iterable[str]):
        for i in list(self.a.keys()):
            if i not in affect:
                del self.a[i]

        for i in list(self.a2.keys()):
            if i not in affect:
                del self.a2[i]

        for i in list(self.v.keys()):
            if i not in affect:
                del self.v[i]

        for i in list(self.v2.keys()):
            if i not in affect:
                del self.v2[i]


rootContext = kaithem.chandlerscript.ChandlerScriptContext()


# Index Cues by codes that we use to jump to them. This is a dict of lists of cues with that short code,
shortcut_codes: Dict[str, List[Cue]] = {}


def codeCommand(code: str = ""):
    "Activates any cues with the matching shortcut code in any scene"
    shortcutCode(code)
    return True


def gotoCommand(scene: str = "=SCENE", cue: str = ""):
    "Triggers a scene to go to a cue.  Ends handling of any further bindings on the current event"

    # Ignore empty
    if not cue.strip():
        return True

    # Track layers of recursion
    newcause = "script.0"
    if kaithem.chandlerscript.context_info.event[0] in ("cue.enter", "cue.exit"):
        cause = kaithem.chandlerscript.context_info.event[1][1]
        # Nast hack, but i don't thing we need more layers and parsing might be slower.
        if cause == "script.0":
            newcause = "script.1"

        elif cause == "script.1":
            newcause = "script.2"

        elif cause == "script.2":
            raise RuntimeError(
                "More than 3 layers of redirects in cue.enter or cue.exit"
            )

    # We don't want to handle other bindings after a goto, leaving a scene stops execution.
    scenes_by_name[scene].scriptContext.stopAfterThisHandler()
    scenes_by_name[scene].goto_cue(cue, cause=newcause)
    return True


gotoCommand.completionTags = {
    "scene": "gotoSceneNamesCompleter",
    "cue": "gotoSceneCuesCompleter",
}


def setAlphaCommand(scene: str = "=SCENE", alpha: float = 1):
    "Set the alpha value of a scene"
    scenes_by_name[scene].setAlpha(float(alpha))
    return True


def ifCueCommand(scene: str, cue: str):
    "True if the scene is running that cue"
    return (
        True
        if scenes_by_name[scene].active
        and scenes_by_name[scene].cue.name == cue
        else None
    )


ifCueCommand.summaryTemplate = "True if cue is running"


def eventCommand(scene: str = "=SCENE", ev: str = "DummyEvent", value: str = ""):
    "Send an event to a scene, or to all scenes if scene is __global__"
    if scene == "__global__":
        event(ev, value)
    else:
        scenes_by_name[scene].event(ev, value)
    return True


def setWebVarCommand(scene: str = "=SCENE", key: str = "varFoo", value: str = ""):
    "Set a slideshow variable. These can be used in the slideshow text as {{var_name}}"
    if not key.startswith('var'):
        raise ValueError("Custom slideshow variable names for slideshow must start with 'var' ")
    scenes_by_name[scene].set_slideshow_variable(key, value)
    return True

rootContext.commands["shortcut"] = codeCommand
rootContext.commands["goto"] = gotoCommand
rootContext.commands["setAlpha"] = setAlphaCommand
rootContext.commands["ifCue"] = ifCueCommand
rootContext.commands["sendEvent"] = eventCommand
rootContext.commands["setSlideshowVariable"] = setWebVarCommand

rootContext.commands["setTag"].completionTags = {
    "tagName": "tagPointsCompleter"}


def sendMqttMessage(topic: str, message: str):
    "JSON encodes message, and publishes it to the scene's MQTT server"
    raise RuntimeError(
        "This was supposed to be overridden by a scene specific version")


rootContext.commands["sendMQTT"] = sendMqttMessage


cueTransitionsLimitCount = 0
cueTransitionsHorizon = 0


def doTransitionRateLimit():
    global cueTransitionsHorizon, cueTransitionsLimitCount
    # This doesn't need locking. It can tolerate being approximate.
    if time.monotonic() > cueTransitionsHorizon - 0.3:
        cueTransitionsHorizon = time.monotonic()
        cueTransitionsLimitCount = 0

    # Limit to less than 2 per 100ms
    if cueTransitionsLimitCount > 6:
        raise RuntimeError(
            "Too many cue transitions extremely fast.  You may have a problem somewhere."
        )
    cueTransitionsLimitCount += 2


def number_to_shortcut(number: int | float | str):
    s = str((Decimal(number) / 1000).quantize(Decimal("0.001")))
    # https://stackoverflow.com/questions/11227620/drop-trailing-zeros-from-decimal
    s = s.rstrip("0").rstrip(".") if "." in s else s
    return s


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


def shortcutCode(code: str, limitScene: Optional[Scene] = None, exclude: Optional[Scene] = None):
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
                        if (x is not exclude):
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
        for i in active_scenes:
            i._event(s, value=value, info=info)


class DebugScriptContext(kaithem.chandlerscript.ChandlerScriptContext):
    def __init__(self, sceneObj: Scene, *a, **k):
        self.sceneObj = weakref.ref(sceneObj)
        self.sceneName: str = sceneObj.name
        self.sceneId = sceneObj.id
        super().__init__(*a, **k)

    def onVarSet(self, k, v):
        scene = self.sceneObj()
        if scene:
            try:
                if not k == "_" and scene.rerenderOnVarChange:
                    scene.recalc_cue_vals()
                    scene.rerender = True

            except Exception:
                core.rl_log_exc("Error handling var set notification")
                print(traceback.format_exc())

            try:
                if not k.startswith("_"):
                    for board in core.iter_boards():
                        if board:
                            if isinstance(v, (str, int, float, bool)):
                                board.linkSend(["varchange", self.sceneId, k, v])
                            elif isinstance(v, collections.defaultdict):
                                v = json.dumps(v)[:160]
                                board.linkSend(["varchange", self.sceneId, k, v])
                            else:
                                v = str(v)[:160]
                                board.linkSend(["varchange", self.sceneId, k, v])
            except Exception:
                core.rl_log_exc("Error handling var set notification")
                print(traceback.format_exc())

    def event(self, e: str, v: str | float | int | bool | None = None):
        kaithem.chandlerscript.ChandlerScriptContext.event(self, e, v)
        try:
            for board in core.iter_boards():
                board.pushEv(e, self.sceneName, time.time(), value=v)
        except Exception:
            core.rl_log_exc("error handling event")
            print(traceback.format_exc())

    def onTimerChange(self, timer, run):
        scene = self.sceneObj()
        if scene:
            scene.runningTimers[timer] = run
            try:
                for board in core.iter_boards():
                    board.linkSend(
                        ["scenetimers", self.sceneName, scene.runningTimers]
                    )
            except Exception:
                core.rl_log_exc("Error handling timer set notification")
                print(traceback.format_exc())

    def canGetTagpoint(self, t):
        if t not in self.tagpoints and len(self.tagpoints) > 128:
            raise RuntimeError("Too many tagpoints in one scene")
        return t


def checkPermissionsForSceneData(data: Dict[str, Any], user: str):
    """Check if used can upload or edit the scene, ekse raise an error if it uses advanced features that would prevent that action.
    We disallow delete because we don't want unprivelaged users to delete something important that they can't fix.

    """
    if "mqtt_server" in data and data["mqtt_server"].strip():
        if not kaithem.users.check_permission(user, "/admin/modules.edit"):
            raise ValueError(
                "You cannot do this action on this scene without /admin/modules.edit, because it uses advanced features: MQTT:"
                + str(kaithem.web.user())
            )


# All the properties that can be saved and loaded are actually defined in the schema,
cue_schema = schemas.get_schema("chandler/cue")

stored_as_property = ['markdown']

slots = list(cue_schema['properties'].keys()) + ["id",     "changed",
                                                 "next_ll",
                                                 "name",
                                                 "scene",
                                                 "inherit",
                                                 "onEnter",
                                                 "onExit",
                                                 "__weakref__"]
s2 = []
for i in slots:
    if not i in stored_as_property:
        s2.append(i)
    else:
        s2.append("_"+i)
slots = s2

class Cue:
    "A static set of values with a fade in and out duration"
    __slots__ = slots

    def __init__(
        self,
        parent: Scene,
        name: str,
        number: Optional[int] = None,
        forceAdd: bool = False,
        shortcut: str = "",
        id: Optional[str] = None,
        onEnter: Optional[Callable[..., Any]] = None,
        onExit: Optional[Callable[..., Any]] = None,
        **kw: Any
    ):

        # declare vars
        self.name: str
        self.number: int
        self.inherit_rules: str
        self.reentrant: bool
        self.sound_volume: float | str
        self.sound_loops: int
        self.named_for_sound: bool
        self.notes: str
        self.alpha: float
        self.fade_in: float
        self.sound_fade_out: float
        self.sound_fade_in: float
        self.length: float | str
        self.rel_length: bool
        self.length_randomize: float
        self.next_cue: str
        self.track: bool
        self.shortcut: str
        self.trigger_shortcut: str
        self.sound: str
        self.slide: str
        self.sound_output: str
        self.sound_start_position: str | float
        self.media_speed: str
        self.media_wind_up: str
        self.media_wind_down: str
        self.probability: float | str
        self.values: Dict[str, Dict[str | int, str | int | float | None]]

        self._markdown: str = kw.get('markdown', '').strip()

        if id:
            disallow_special(id)

        disallow_special(name, allowedCueNameSpecials)
        if name[0] in "1234567890":
            name = "x" + name

        # This is so we can loop through them and push to gui
        self.id: str = id or uuid.uuid4().hex
        self.name = name

        # Odd circular dependancy
        try:
            self.number = number or parent.cues_ordered[-1].number + 5000
        except Exception:
            self.number = 5000

        # Most of the data is loaded here based on what's in the schema
        for i in cue_schema['properties']:
            # number is special because of auto increment
            if not i == 'number':
                if i in kw:
                    setattr(self, i, kw[i])
                else:
                    setattr(self, i, copy.deepcopy(cue_schema['properties'][i]['default']))

        for i in kw:
            if i not in cue_schema['properties']:
                logging.error("Unknown cue data key " + str(i) +
                              " loading anyway but data may be lost")

        # Now unused
        # self.script = script
        self.onEnter = onEnter
        self.onExit = onExit

        cues[self.id] = self

        self.next_ll: Optional[Cue] = None
        parent._add_cue(self, forceAdd=forceAdd)
        self.changed = {}

        self.scene: weakref.ref[Scene] = weakref.ref(parent)
        self.setShortcut(shortcut, False)

        self.push()

    def serialize(self):
        x2 = {}
        # The schema decides what properties we save
        for i in schemas.get_schema("chandler/cue")['properties']:
            x2[i] = getattr(self, i)

        schemas.supress_defaults("chandler/cue", x2)

        return x2

    def getScene(self):
        s = self.scene()
        if not s:
            raise RuntimeError("Scene must have been deleted")
        return s

    def push(self):
        core.add_data_pusher_to_all_boards(lambda s: s.pushCueMeta(self.id))

    def pushData(self):
        core.add_data_pusher_to_all_boards(lambda s: s.pushCueData(self.id))

    def pushoneval(self, u: str, ch: str | int, v: str | float | None):
        core.add_data_pusher_to_all_boards(lambda s: s.linkSend(["scv", self.id, u, ch, v])
                                           )

    def clone(self, name: str):
        if name in self.getScene().cues:
            raise RuntimeError("Cannot duplicate cue names in one scene")

        c = Cue(
            self.getScene(),
            name,
            fade_in=self.fade_in,
            length=self.length,
            length_randomize=self.length_randomize,
            values=copy.deepcopy(self.values),
            next_cue=self.next_cue,
            rel_length=self.rel_length,
            track=self.track
        )

        core.add_data_pusher_to_all_boards(lambda s: s.pushCueMeta(c.id))
        core.add_data_pusher_to_all_boards(lambda s: s.pushCueData(c.id))

    def setTrack(self, val):
        self.track = bool(val)
        self.getScene().rerender = True

    def setNumber(self, n):
        "Can take a string representing a decimal number for best accuracy, saves as *1000 fixed point"
        if self.shortcut == number_to_shortcut(self.number):
            self.setShortcut(
                number_to_shortcut(
                    int((Decimal(n) * Decimal(1000)).quantize(1)))
            )
        self.number = int((Decimal(n) * Decimal(1000)).quantize(1))

        # re-sort the cuelist
        self.getScene().insertSorted(None)

        self.push()

    @property
    def markdown(self):
        return self._markdown

    @markdown.setter
    def markdown(self, s: str):
        s = s.strip().replace('\r', '')
        if not s == self._markdown:
            self._markdown = s
            self.push()
            scene = self.scene()
            if scene:
                scene.mediaLink.send(
                    [
                        "text",
                        self._markdown,
                    ]
                )


    def setRules(self, r: Optional[List[List[str | float | bool] | str | float | bool]]):
        self.rules = r
        self.getScene().refreshRules()

    def setInheritRules(self, r):
        self.inherit_rules = r
        self.getScene().refreshRules()

    def setShortcut(self, code: str, push: bool = True):

        code = normalize_shortcut(code)

        disallow_special(code, allow="._")

        if code == "__generate__from__number__":
            code = number_to_shortcut(self.number)
        with core.lock:
            if self.shortcut in shortcut_codes:
                try:
                    shortcut_codes[code].remove(self)
                except Exception:
                    print(traceback.format_exc())

            if random.random() < 1:
                # Do a full GC pass of the shortcut codes list
                torm = []
                for i in shortcut_codes:
                    if not shortcut_codes[i]:
                        torm.append(i)
                    else:
                        for j in list(shortcut_codes[i]):
                            if not j.scene():
                                shortcut_codes[i].remove(j)
                for i in torm:
                    del shortcut_codes[i]

            if code:
                if code in shortcut_codes:
                    shortcut_codes[code].append(self)
                else:
                    shortcut_codes[code] = [self]

            self.shortcut = code
            if push:
                self.push()

    @typechecked
    def set_value(self, universe: str, channel: str | int, value: str | float | None):
        disallow_special(universe, allow="_@.")

        scene = self.getScene()

        if not scene:
            raise RuntimeError("The scene doesn't exist")
        if value is not None:
            try:
                value = float(value)
            except ValueError:
                pass

        if isinstance(channel, (int, float)):
            pass

        else:
            x = channel.strip()
            if not x == channel:
                raise Exception(
                    "Channel name cannot begin or end with whitespace")

            # If it looks like an int, cast it even if it's a string,
            # We get a lot of raw user input that looks like that.
            try:
                channel = int(channel)
            except ValueError:
                pass

        # Assume anything that can be an int, is meant to be
        if isinstance(channel, str):
            try:
                channel = int(channel)
            except ValueError:
                pass

        with core.lock:
            if universe == "__variables__":
                assert isinstance(channel, str)
                scene.scriptContext.setVar(channel, scene.evalExpr(value))

            reset = False
            if not (value is None):
                if universe not in self.values:
                    self.values[universe] = {}
                    reset = True
                if channel not in self.values[universe]:
                    reset = True
                self.values[universe][channel] = value
            else:
                empty = False
                if channel in self.values[universe]:
                    del self.values[universe][channel]
                if not self.values[universe]:
                    empty = True
                    del self.values[universe]
                if empty:
                    self.pushData()
            self.pushoneval(universe, channel, value)

            unmappeduniverse = universe

            x = mapChannel(universe, channel)

            if scene.cue == self and scene.isActive():
                scene.rerender = True

                # If we change something in a pattern effect we just do a full recalc since those are complicated.
                if (
                    unmappeduniverse in self.values
                    and "__length__" in self.values[unmappeduniverse]
                ):
                    scene.cue_vals_to_numpy_cache(self, False)

                    # The FadeCanvas needs to know about this change
                    scene.render(force_repaint=True)

                # Otherwise if we are changing a simple mapped channel we optimize
                elif x:
                    universe, channel = x[0], x[1]

                    if (
                        universe not in scene.cue_cached_alphas_as_arrays
                    ) and value is not None:
                        uobj = getUniverse(universe)
                        if uobj:
                            scene.cue_cached_vals_as_arrays[
                                universe
                            ] = numpy.array([0.0] * len(uobj.values), dtype="f4")
                            scene.cue_cached_alphas_as_arrays[
                                universe
                            ] = numpy.array([0.0] * len(uobj.values), dtype="f4")
                    if universe in scene.cue_cached_alphas_as_arrays:
                        scene.cue_cached_alphas_as_arrays[universe][channel] = (
                            1 if value is not None else 0
                        )
                        scene.cue_cached_vals_as_arrays[universe][
                            channel
                        ] = scene.evalExpr(value if value is not None else 0)
                    if universe not in scene.affect:
                        scene.affect.append(universe)

                    # The FadeCanvas needs to know about this change
                    scene.render(force_repaint=True)

            scene.rerender = True

            # For blend modes that don't like it when you
            # change the list of values without resetting
            if reset:
                scene.setBlend(scene.blend)


scene_schema = schemas.get_schema("chandler/scene")


class Scene:
    "An objecting representing one scene. If noe default cue present one is made"

    def __init__(
        self,
        name: str,
        cues: Optional[Dict[str, Dict[str, Any]]] = None,
        active: bool = False,
        alpha: float = 1,
        priority: float = 50,
        blend: str = "normal",
        id: Optional[str] = None,
        default_active: bool = True,
        blend_args: Optional[Dict[str, Any]] = None,
        backtrack: bool = True,
        bpm: float = 60,
        sound_output: str = "",
        event_buttons: List[Iterable[str]] = [],
        display_tags=[],
        info_display: str = "",
        utility: bool = False,
        hide: bool = False,
        notes: str = "",
        mqtt_server: str = "",
        crossfade: float = 0,
        midi_source: str = "",
        default_next: str = "",
        command_tag: str = "",
        slide_overlay_url: str = "",
        slideshow_layout: str = "",
        music_visualizations: str = "",
        mqtt_sync_features: Optional[Dict[str, Any]] = None,
        **ignoredParams
    ):
        """


        Args:
            name (str): _description_
            cues (_type_, optional):
            active (bool, optional):
            alpha (float, optional):
            priority (float, optional):
            blend (str, optional):
            id (Optional[str], optional):
            default_active (bool, optional):
            blend_args (Optional[Dict[str, Any]], optional):
            backtrack (bool, optional):
            bpm (float, optional):
            sound_output (str, optional):
            event_buttons (List[Iterable[str]], optional): List of ButtonLabel, EventName pairs
            display_tags (list, optional):
            info_display (str, optional):
            utility (bool, optional):
            hide (bool):
            notes (str, optional):
            mqtt_server (str, optional):
            crossfade (int, optional):
            midi_source (str, optional):
            default_next (str, optional):
            command_tag (str, optional):
            slide_overlay_url (str, optional):
            slideshow_layout (str, optional):
            music_visualizations (str, optional):
            mqtt_sync_features (_type_, optional):

        Raises:
            RuntimeError: _description_
            ValueError: _description_
        """
        if name and name in scenes_by_name:
            raise RuntimeError("Cannot have 2 scenes sharing a name: " + name)

        if not name.strip():
            raise ValueError("Invalid Name")
        

        # Variables to send to the slideshow.  They are UI only and
        # we don't have any reactive features
        self.web_variables: Dict[str, Any] = {}

        self.mqttConnection = None
        self.mqttSubscribed: Dict[str, bool]

        disallow_special(name)

        self.mqtt_sync_features: Dict[str, Any] = mqtt_sync_features or {}
        self.mqttNodeSessionID: str = base64.b64encode(os.urandom(8)).decode()

        self.event_buttons: list = event_buttons[:]
        self.info_display = info_display
        self.utility: bool = bool(utility)

        # This is used for the remote media triggers feature.
        self.mediaLink = kaithem.widget.APIWidget()
        self.mediaLink.echo = False

        self.slide_overlay_url: str = slide_overlay_url

        # Kind of long so we do it in the external file
        self.slideshow_layout: str = slideshow_layout.strip() or scene_schema['properties']['slideshow_layout']['default']

        # Audio visualizations
        self.music_visualizations = music_visualizations

        # The active media file being played through the remote playback mechanism.
        self.allowMediaUrlRemote = None

        self.hide = hide

        def handleMediaLink(u, v):
            if v[0] == "initial":
                self.sendVisualizations()

            if v[0] == "ask":
                self.mediaLink.send(["volume", self.alpha])

                self.mediaLink.send(
                    [
                        "text",
                        self.cue.markdown
                    ]
                )

                self.mediaLink.send(
                    [
                        "cue_ends",
                        self.cuelen + self.enteredCue,
                        self.cuelen
                    ]
                )

                self.mediaLink.send(
                    [
                        "all_variables",
                        self.web_variables
                    ]
                )


                self.mediaLink.send(
                    [
                        "mediaURL",
                        self.allowMediaUrlRemote,
                        self.enteredCue,
                        max(0, self.cue.fade_in or self.cue.sound_fade_in or self.crossfade),
                    ]
                )
                self.mediaLink.send(
                    [
                        "slide",
                        self.cue.slide,
                        self.enteredCue,
                        max(0, self.cue.fade_in or self.crossfade),
                    ]
                )
                self.mediaLink.send(["overlay", self.slide_overlay_url])

            if v[0] == "error":
                self.event(
                    "system.error",
                    "Web media playback error in remote browser: " + v[1],
                )

        self.mediaLink.attach(handleMediaLink)
        self.lock = threading.RLock()
        self.randomizeModifier = 0

        self.command_tagSubscriptions = []
        self.command_tag = command_tag

        self.notes = notes
        self._midi_source: str = ""
        self.default_next = str(default_next).strip()

        self.id: str = id or uuid.uuid4().hex

        # TagPoint for managing the current cue
        self.cueTag = kaithem.tags.StringTag(
            "/chandler/scenes/" + name + ".cue")
        self.cueTag.expose("users.chandler.admin", "users.chandler.admin")

        self.cueTagClaim = self.cueTag.claim(
            "__stopped__", "Scene", 50, annotation="SceneObject"
        )

        self.cueVolume = 1

        # Allow goto_cue
        def cueTagHandler(val, timestamp, annotation):
            # We generated this event, that means we don't have to respond to it
            if annotation == "SceneObject":
                return

            if val == "__stopped__":
                self.stop()
            else:
                # Just goto the cue
                self.goto_cue(val, cause="tagpoint")

        self.cueTagHandler = cueTagHandler

        self.cueTag.subscribe(cueTagHandler)

        # This is used to expose the state of the music cue mostly.
        self.cueInfoTag = kaithem.tags.ObjectTag(
            "/chandler/scenes/" + name + ".cueInfo"
        )
        self.cueInfoTag.value = {"audio.meta": {}}
        self.cueInfoTag.expose("users.chandler.admin", "users.chandler.admin")

        self.albumArtTag = kaithem.tags.StringTag(
            "/chandler/scenes/" + name + ".albumArt"
        )
        self.albumArtTag.expose("users.chandler.admin")

        # Used to determine the numbering of added cues
        self.topCueNumber = 0
        # Only used for monitor scenes
        self.valueschanged = {}
        # Place to stash a blend object for new blending mode
        # Hardcoded indicates that applyLayer reads the blend name and we
        # have hardcoded logic there
        self._blend: blendmodes.BlendMode = blendmodes.HardcodedBlendMode(self)
        self.blendClass: Type[blendmodes.BlendMode] = blendmodes.HardcodedBlendMode
        self.alpha = alpha
        self.crossfade = crossfade

        self.cuelen = 0

        # TagPoint for managing the current alpha
        self.alphaTag = kaithem.tags["/chandler/scenes/" + name + ".alpha"]
        self.alphaTag.min = 0
        self.alphaTag.max = 1
        self.alphaTag.expose("users.chandler.admin", "users.chandler.admin")

        self.alphaTagClaim = self.alphaTag.claim(
            self.alpha, "Scene", 50, annotation="SceneObject"
        )

        # Allow setting the alpha
        def alphaTagHandler(val, timestamp, annotation):
            # We generated this event, that means we don't have to respond to it
            if annotation == "SceneObject":
                return
            self.setAlpha(val)

        self.alphaTag.subscribe(alphaTagHandler)
        self.alphaTagHandler = alphaTagHandler

        self.active = False
        self.default_alpha = alpha
        self.name = name

        self.canvas = FadeCanvas()
        self._backtrack = backtrack
        self.bpm = bpm
        self.sound_output = sound_output

        self.cues: Dict[str, Cue] = {}

        # The list of cues as an actual list that is maintained sorted by number
        self.cues_ordered: List[Cue] = []

        if cues:
            for j in cues:
                Cue(self, name=j, **cues[j])

        if 'default' not in self.cues:
            Cue(self, "default")

        self.cue: Cue = self.cues['default']

        # Used for the tap tempo algorithm
        self.lastTap: float = 0
        self.tapSequence = 0

        # This flag is used to avoid having to repaint the canvas if we don't need to
        self.fade_in_completed = False
        # A pointer into that list pointing at the current cue. We have to update all this
        # every time we change the lists
        self.cuePointer = 0

        # Used for storing when the sound file  or slide ended. 0 indicates a sound file end event hasn't
        # happened since the cue started
        self.media_ended_at = 0

        self.cueTagClaim.set(self.cue.name, annotation="SceneObject")

        # Used to avoid an excessive number of repeats in random cues
        self.cueHistory: List[str] = []

        # List of universes we should be affecting right now
        # Based on what values are in the cue and what values are inherited
        self.affect: List[str] = []

        # Lets us cache the lists of values as numpy arrays with 0 alpha for not present vals
        # which are faster that dicts for some operations
        self.cue_cached_vals_as_arrays: Dict[str,
                                             numpy.typing.NDArray[Any]] = {}
        self.cue_cached_alphas_as_arrays: Dict[str,
                                               numpy.typing.NDArray[Any]] = {}

        self.rerenderOnVarChange = False

        self.enteredCue: float = 0

        # Map event name to runtime as unix timestamp
        self.runningTimers: Dict[str, float] = {}

        self._priority = priority

        # Used by blend modes
        self.blend_args: Dict[str, float | int | bool | str] = blend_args or {}
        self.setBlend(blend)
        self.default_active = default_active

        # Used to indicate that the most recent frame has changed something about the scene
        # Metadata that GUI clients need to know about.
        self.hasNewInfo = {}

        # Set to true every time the alpha value changes or a scene value changes
        # set to false at end of rendering
        self.rerender = False

        # Last time the scene was started. Not reset when stopped
        self.started = 0

        self.chandlerVars = {}

        if name:
            scenes_by_name[self.name] = self
        if not name:
            name = self.id
        scenes[self.id] = self

        # The bindings for script commands that might be in the cue metadata
        # Used to be made on demand, now we just always have it
        self.scriptContext = self.make_script_context()

        self.displayTagSubscriptions = []
        self.display_tags = []
        self.displayTagValues = {}
        self.displayTagPointObjects: Dict[str, object] = {}
        self.displayTagMeta: Dict[str, Dict[str, Any]] = {}
        self.setDisplayTags(display_tags)

        self.refreshRules()

        self.mqtt_server = mqtt_server
        self.activeMqttServer = None

        self._midi_source = ''

        self.midi_source = midi_source

        if active:
            self.goto_cue("default", sendSync=False, cause="start")
            self.go()
            if isinstance(active, (int, float)):
                self.started = time.time() - active

        else:
            self.cueTagClaim.set("__stopped__", annotation="SceneObject")

        self.subscribe_command_tags()

    def toDict(self) -> Dict[str, Any]:

        # These are the properties that aren't just straight 1 to 1 copies
        # of props, but still get saved
        d = {
            "alpha": self.default_alpha,
            "cues": {j: self.cues[j].serialize() for j in self.cues},
            "active": self.default_active, 
            "uuid": self.id,
        }

        for i in scene_schema['properties']:
            if i not in d:
                d[i] = getattr(self, i)

        schemas.validate("chandler/scene", d)

        return d

    def __del__(self):
        pass

    def getStatusString(self):
        x = ""
        if self.mqttConnection:
            if not self.mqttConnection.is_connected:
                x += "MQTT Dis_connected "
        return x

    def set_slideshow_variable(self, k: str, v: Any):
        self.mediaLink.send(
                [
                    "web_var",
                    k,
                    v
                ]
            )
        
        self.web_variables[k] = v

    def close(self):
        "Unregister the scene and delete it from the lists"
        with core.lock:
            self.stop()
            self.mqtt_server = ''
            x = self.mqttConnection
            if x:
                x.disconnect()
            if scenes_by_name.get(self.name, None) is self:
                del scenes_by_name[self.name]

            if scenes.get(self.id, None) is self:
                del scenes[self.id]

    def evalExprFloat(self, s: str | float) -> float:
        f = self.evalExpr(s)
        assert isinstance(f, (int, float))
        return f

    # -> Any | bool | float | int | str | Callable[[], float] | Callable[..., int] | type[int] | type[float] | type[str] | slice | tuple[Any, Any] | None:
    def evalExpr(self, s: str | float | bool | None):
        """Given A string, return a number if it looks like one, evaluate the expression if it starts with =, otherwise
        return the input.

        Given a number, return it.

        Basically, implements something like the logic from a spreadsheet app.
        """
        return self.scriptContext.preprocessArgument(s)

    def insertSorted(self, c):
        "Insert a None to just recalt the whole ordering"
        with core.lock:
            if c:
                self.cues_ordered.append(c)

            self.cues_ordered.sort(key=lambda i: i.number)

            # We inset cues before we actually have a selected cue.
            if hasattr(self, 'cue') and self.cue:
                try:
                    self.cuePointer = self.cues_ordered.index(self.cue)
                except Exception:
                    print(traceback.format_exc())
            else:
                self.cuePointer = 0

            # Regenerate linked list by brute force when a new cue is added.
            for i in range(len(self.cues_ordered) - 1):
                self.cues_ordered[i].next_ll = self.cues_ordered[i + 1]
            self.cues_ordered[-1].next_ll = None

    def getDefaultNext(self):
        if self.default_next.strip():
            return self.default_next.strip()
        try:
            x = self.cues_ordered[self.cuePointer + 1].name

            # Special cues are excluded from the normal flow
            if not x.startswith("__"):
                return x
            else:
                return None
        except Exception:
            return None

    def getAfter(self, cue: str):
        x = self.cues[cue].next_ll
        return x.name if x else None

    def getParent(self, cue: str) -> Optional[str]:
        "Return the cue that this cue name should backtrack values from or None"
        with core.lock:
            if not self.cues[cue].track:
                return None

            # This is an optimization for if we already know the index
            if self.cue and cue == self.cue.name:
                v = self.cuePointer
            else:
                v = self.cues_ordered.index(self.cues[cue])

            if not v == 0:
                x = self.cues_ordered[v - 1]
                if (not x.next_cue) or x.next_cue == cue:
                    return x.name
            return None

    def rmCue(self, cue: str):
        with core.lock:
            if not len(self.cues) > 1:
                raise RuntimeError("Cannot have scene with no cues")

            if cue in cues:
                if cues[cue].name == "default":
                    raise RuntimeError("Cannot delete the cue named default")

            if self.cue and self.name == cue:
                try:
                    self.goto_cue("default", cause="deletion")
                except Exception:
                    self.goto_cue(self.cues_ordered[0].name, cause="deletion")

            if cue in cues:
                id = cue
                name = cues[id].name
            elif cue in self.cues:
                name = cue
                id = self.cues[cue].id
            else:
                raise RuntimeError("Cue does not seem to exist")

            self.cues_ordered.remove(self.cues[name])

            if cue in cues:
                id = cue
                self.cues[cues[cue].name].setShortcut("")
                del self.cues[cues[cue].name]
            elif cue in self.cues:
                id = self.cues[cue].id
                self.cues[cue].setShortcut("")
                del self.cues[cue]

            for board in core.iter_boards():
                if len(board.newDataFunctions) < 100:
                    board.newDataFunctions.append(
                        lambda s: s.linkSend(["delcue", id]))
            try:
                self.cuePointer = self.cues_ordered.index(self.cue)
            except Exception:
                print(traceback.format_exc())
        # Regenerate linked list by brute force when a new cue is added.
        for i in range(len(self.cues_ordered) - 1):
            self.cues_ordered[i].next_ll = self.cues_ordered[i + 1]
        self.cues_ordered[-1].next_ll = None

    # I think we can delete this
    def pushCues(self):
        for board in core.iter_boards():
            if len(board.newDataFunctions) < 100:
                board.newDataFunctions.append(lambda s: self.pushCueList(i.id))

    def _add_cue(self, cue: Cue, prev: str = None, forceAdd=True):
        name = cue.name
        self.insertSorted(cue)
        if name in self.cues and not forceAdd:
            raise RuntimeError("Cue would overwrite existing.")
        self.cues[name] = cue
        if prev and prev in self.cues:
            raise RuntimeError("Not supported this code path")
            self.cues[prev].next_cue = self.cues[name]

        core.add_data_pusher_to_all_boards(lambda s: s.pushCueMeta(self.cues[name].id))
        core.add_data_pusher_to_all_boards(lambda s: s.pushCueData(cue.id))

    def pushMeta(self, cue: str | bool = False, statusOnly: bool = False, keys: None | Iterable[str] = None):
        # Push cue first so the client already has that data when we jump to the new display
        if cue and self.cue:
            core.add_data_pusher_to_all_boards(lambda s: s.pushCueMeta(self.cue.id))

        core.add_data_pusher_to_all_boards(lambda s: s.pushMeta(
            self.id, statusOnly=statusOnly, keys=keys)
        )

    def event(self, s: str, value: Any = True, info: str = "", exclude_errors: bool = True):
        # No error loops allowed!
        if ((not s == "script.error") and exclude_errors):
            self._event(s, value, info)

    def _event(self, s: str, value: Any, info: str = ""):
        "Manually trigger any script bindings on an event"
        try:
            if self.scriptContext:
                self.scriptContext.event(s, value)
        except Exception:
            core.rl_log_exc("Error handling event: " + str(s))
            print(traceback.format_exc(6))

    def pick_random_cue_from_names(self, cues: List[str] | Set[str] | Dict[str, Any]) -> str:
        names: List[str] = []
        weights: List[float] = []

        for i in cues:
            i = i.strip()
            # Exclude special cues
            if i.startswith('__'):
                continue
            if i in self.cues:
                weights.append(self.evalExprFloat(
                    str(self.cues[i].probability).strip() or 1))
                names.append(i)

        return random.choices(names, weights=weights)[0]

    def _parseCueName(self, cue: str) -> str:
        "Take a raw cue name and find an actual matching cue. Handles things like shuffle"
        if cue == "__shuffle__":
            x = [i.name for i in self.cues_ordered if not (
                i.name == self.cue.name)]
            for i in list(reversed(self.cueHistory[-15:])):
                if len(x) < 3:
                    break
                elif i[0] in x:
                    x.remove(i[0])
            cue = self.pick_random_cue_from_names(x)

        elif cue == "__random__":
            x = [i.name for i in self.cues_ordered if not i.name == self.cue.name]
            cue = self.pick_random_cue_from_names(x)

        else:
            # Handle random selection option cues
            if "|" in cue:
                x = cue.split("|")
                if random.random() > 0.3:
                    for i in reversed(self.cueHistory[-15:]):
                        if len(x) < 3:
                            break
                        elif i[0] in x:
                            x.remove(i)
                cue = self.pick_random_cue_from_names(x)

            elif "*" in cue:
                import fnmatch

                x = []

                if cue.startswith("shuffle:"):
                    cue = cue[len("shuffle:"):]
                    shuffle = True
                else:
                    shuffle = False

                for i in self.cues_ordered:
                    if fnmatch.fnmatch(i.name, cue):
                        x.append(i.name)
                if not x:
                    raise ValueError("No matching cue for pattern: " + cue)

                if shuffle:
                    # Do the "Shuffle logic" that avoids  recently used cues.
                    # Eliminate until only two remain, the min to not get stuck in
                    # A fixed pattern.
                    optionsNeeded = 2
                    for i in reversed(self.cueHistory[-50:]):
                        if len(x) <= optionsNeeded:
                            break
                        elif i[0] in x:
                            x.remove(i)
                cue = cue = self.pick_random_cue_from_names(x)

        cue = cue.split("?")[0]

        if cue not in self.cues:
            try:
                cue = float(cue)
            except Exception:
                raise ValueError("No such cue " + str(cue))
            for i in self.cues_ordered:
                if i.number - (float(cue) * 1000) < 0.001:
                    cue = i.name
                    break
        return cue

    def goto_cue(self, cue: str, t: Optional[float] = None, sendSync=True, generateEvents=True, cause="generic"):
        "Goto cue by name, number, or string repr of number"
        # Globally raise an error if there's a big horde of cue transitions happening
        doTransitionRateLimit()

        if self.cue:
            oldSoundOut = self.cue.sound_output
        else:
            oldSoundOut = None
        if not oldSoundOut:
            oldSoundOut = self.sound_output

        cue = str(self.evalExpr(cue))

        if "?" in cue:
            cue, args = cue.split("?")
            kwargs = urllib.parse.parse_qs(args)
        else:
            kwargs = {}

        k2 = {}

        for i in kwargs:
            if len(kwargs[i]) == 1:
                k2[i] = kwargs[i][0]

        kwargs = collections.defaultdict(lambda: "", k2)

        self.scriptContext.setVar("KWARGS", kwargs)

        t = t or time.time()

        if cue in self.cues:
            if sendSync:
                gn = self.mqtt_sync_features.get("syncGroup", False)
                if gn:
                    topic = f"/kaithem/chandler/syncgroup/{gn}"
                    m = {
                        'time': t,
                        "cue": cue,
                        "senderSessionID": self.mqttNodeSessionID
                    }
                    self.sendMqttMessage(topic, m)

        with core.lock:
            with self.lock:
                if not self.active:
                    return

                if self.canvas:
                    self.canvas.save()

                # There might be universes we affect that we don't anymore,
                # We need to rerender those because otherwise the system might think absolutely nothing has changed.
                # A full rerender on every cue change isn't the most efficient, but it shouldn't be too bad
                # since most frames don't have a cue change in them
                for i in self.affect:
                    rerenderUniverse(i)

                if cue == "__stop__":
                    self.stop()
                    return

                cue = self._parseCueName(cue)

                cobj = self.cues[cue]

                if self.cue:
                    if cobj == self.cue:
                        if not cobj.reentrant:
                            return
                else:
                    # Act like we actually we in the default cue, but allow reenter no matter what since
                    # We weren't in any cue
                    self.cue = self.cues["default"]
                    self.cueTagClaim.set(
                        self.cue.name, annotation="SceneObject")

                self.enteredCue = t

                # Allow specifying an "Exact" time to enter for zero-drift stuff, so things stay in sync
                # I don't know if it's fully correct to set the timestamp before exit...
                # However we really don't want to queue up a bazillion transitions
                # If we can't keep up, so we limit that to 3s
                # if t and t>time.time()-3:
                # Also, limit to 500ms in the future, seems like there could be bugs otherwise
                #   self.enteredCue = min(t,self.enteredCue+0.5)

                entered = self.enteredCue

                if not (cue == self.cue.name):
                    if generateEvents:
                        if self.active and self.scriptContext:
                            self.event("cue.exit", value=[
                                       self.cue.name, cause])

                # We return if some the enter transition already
                # Changed to a new cue
                if not self.enteredCue == entered:
                    return

                self.cueHistory.append((cue, time.time()))
                self.cueHistory = self.cueHistory[-1024:]
                self.media_ended_at = 0

                try:
                    # Take rules from new cue, don't actually set this as the cue we are in
                    # Until we succeed in running all the rules that happen as we enter
                    # We do set the local variables for the incoming cue though.
                    self.refreshRules(cobj)
                except Exception:
                    core.rl_log_exc("Error handling script")
                    print(traceback.format_exc(6))

                if self.active:
                    if self.cue.onExit:
                        self.cue.onExit(t)

                    if cobj.onEnter:
                        cobj.onEnter(t)

                    if generateEvents:
                        self.event("cue.enter", [cobj.name, cause])

                # We return if some the enter transition already
                # Changed to a new cue
                if not self.enteredCue == entered:
                    return

                # We don't fully reset until after we are done fading in and have rendered.
                # Until then, the affect list has to stay because it has stuff that prev cues affected.
                # Even if we are't tracking, we still need to know to rerender them without the old effects,
                # And the fade means we might still affect them for a brief time.

                # TODO backtracking these variables?
                cuevars = self.cues[cue].values.get("__variables__", {})
                for i in cuevars:
                    try:
                        self.scriptContext.setVar(i, self.evalExpr(cuevars[i]))
                    except Exception:
                        print(traceback.format_exc())
                        core.rl_log_exc("Error with cue variable " + str(i))

                if self.cues[cue].track:
                    self.apply_tracked_values(cue)

                self.mediaLink.send(
                    [
                        "slide",
                        self.cues[cue].slide,
                        self.enteredCue,
                        max(0, self.cues[cue].fade_in or self.crossfade),
                    ]
                )

                self.mediaLink.send(
                    [
                        "text",
                        self.cues[cue].markdown,
                    ]
                )

                # optimization, try to se if we can just increment if we are going to the next cue, else
                # we have to actually find the index of the new cue
                if (
                    self.cuePointer < (len(self.cues_ordered) - 1)
                    and self.cues[cue] is self.cues_ordered[self.cuePointer + 1]
                ):
                    self.cuePointer += 1
                else:
                    self.cuePointer = self.cues_ordered.index(self.cues[cue])

                if not self.cues[cue].sound == "__keep__":
                    # Don't stop audio of we're about to crossfade to the next track
                    if not (self.crossfade and self.cues[cue].sound):
                        if self.cue.sound_fade_out or self.cue.media_wind_down:
                            fadeSound(
                                None,
                                length=self.cue.sound_fade_out,
                                handle=str(self.id),
                                winddown=self.evalExprFloat(self.cue.media_wind_down or 0),
                            )
                        else:
                            stopSound(str(self.id))
                    # There is no next sound so crossfade to silence
                    if self.crossfade and (not self.cues[cue].sound):
                        if self.cue.sound_fade_out or self.cue.media_wind_down:
                            fadeSound(
                                None,
                                length=self.cue.sound_fade_out,
                                handle=str(self.id),
                                winddown=self.evalExprFloat(self.cue.media_wind_down or 0),
                            )
                        else:
                            stopSound(str(self.id))

                    self.allowMediaUrlRemote = None

                    out = self.cues[cue].sound_output
                    if not out:
                        out = self.sound_output
                    if not out:
                        out = None

                    if oldSoundOut == "scenewebplayer" and not out == "scenewebplayer":
                        self.mediaLink.send(["volume", self.alpha])
                        self.mediaLink.send(
                            [
                                "mediaURL",
                                None,
                                self.enteredCue,
                                max(0,
                                    self.cues[cue].fade_in or self.crossfade),
                            ]
                        )

                    if self.cues[cue].sound and self.active:
                        sound = self.cues[cue].sound
                        try:
                            self.cueVolume = min(
                                5,
                                max(
                                    0, self.evalExprFloat(
                                        self.cues[cue].sound_volume or 1)
                                ),
                            )
                        except Exception:
                            self.event(
                                "script.error",
                                self.name
                                + " in cueVolume eval:\n"
                                + traceback.format_exc(),
                            )
                            self.cueVolume = 1
                        try:
                            sound = self.resolve_sound(sound)
                        except Exception:
                            print(traceback.format_exc())

                        if os.path.isfile(sound):
                            if not out == "scenewebplayer":
                                # Always fade in if the face in time set.
                                # Also fade in for crossfade,
                                # but in that case we only do it if there is something to fade in from.
                                if not (
                                    (
                                        (
                                            (self.crossfade > 0)
                                            and not (self.cues[cue].sound_fade_in < 0)
                                        )
                                        and kaithem.sound.is_playing(str(self.id))
                                    )
                                    or (self.cues[cue].sound_fade_in > 0)
                                    or self.cues[cue].media_wind_up
                                    or self.cue.media_wind_down
                                ):
                                    spd = self.scriptContext.preprocessArgument(
                                        self.cues[cue].media_speed
                                    )
                                    spd = spd or 1

                                    spd = float(spd)

                                    play_sound(
                                        sound,
                                        handle=str(self.id),
                                        volume=self.alpha * self.cueVolume,
                                        output=out,
                                        loop=self.cues[cue].sound_loops,
                                        start=self.evalExprFloat((self.cues[cue].sound_start_position or 0)),
                                        speed=spd,
                                    )
                                else:
                                    fade = self.cues[cue].sound_fade_in or self.crossfade
                                    fadeSound(
                                        sound,
                                        length=max(fade, 0.1),
                                        handle=str(self.id),
                                        volume=self.alpha * self.cueVolume,
                                        output=out,
                                        loop=self.cues[cue].sound_loops,
                                        start=self.evalExprFloat(self.cues[cue].sound_start_position or 0),
                                        windup=self.evalExprFloat(self.cues[cue].media_wind_up or 0),
                                        winddown=self.evalExprFloat(self.cue.media_wind_down or 0),
                                    )

                            else:
                                self.allowMediaUrlRemote = sound
                                self.mediaLink.send(["volume", self.alpha])
                                self.mediaLink.send(
                                    [
                                        "mediaURL",
                                        sound,
                                        self.enteredCue,
                                        max(0,
                                            self.cues[cue].fade_in or self.crossfade),
                                    ]
                                )

                            try:
                                soundMeta = TinyTag.get(sound, image=True)

                                currentAudioMetadata = {
                                    "title": soundMeta.title or "Unknown",
                                    "artist": soundMeta.artist or "Unknown",
                                    "album": soundMeta.album or "Unknown",
                                    "year": soundMeta.year or "Unknown",
                                }
                                t = soundMeta.get_image()
                            except Exception:
                                # Not support, but it might just be an unsupported type.
                                # if mp3, its a real error, we should alert
                                if sound.endswith(".mp3"):
                                    self.event(
                                        "error",
                                        "Reading metadata for: "
                                        + sound
                                        + traceback.format_exc(),
                                    )
                                t = None
                                currentAudioMetadata = {
                                    "title": "",
                                    "artist": "",
                                    "album": "",
                                    "year": "",
                                }

                            self.cueInfoTag.value = {
                                "audio.meta": currentAudioMetadata}

                            if t and len(t) < 3 * 10**6:
                                self.albumArtTag.value = (
                                    "data:image/jpeg;base64,"
                                    + base64.b64encode(t).decode()
                                )
                            else:
                                self.albumArtTag.value = ""

                        else:
                            self.event(
                                "error", "File does not exist: " + sound)
                sc = self.cues[cue].trigger_shortcut.strip()
                if sc:
                    shortcutCode(sc, exclude=self)
                self.cue = self.cues[cue]
                self.cueTagClaim.set(
                    self.cues[cue].name, annotation="SceneObject")

                self.recalc_randomize_modifier()
                self.recalc_cue_len()

                # Recalc what universes are affected by this scene.
                # We don't clear the old universes, we do that when we're done fading in.
                for i in self.cues[cue].values:
                    i = mapUniverse(i)
                    if i and i in universes.universes:
                        if i not in self.affect:
                            self.affect.append(i)

                self.cue_vals_to_numpy_cache(self.cue, not self.cue.track)
                self.fade_in_completed = False

                # We don't render here. Very short cues coupt create loops of rerendering and goto
                # self.render(force_repaint=True)

                # Instead we set the flag
                self.rerender = True
                self.pushMeta(statusOnly=True)

                self.preload_next_cue_sound()

                self.mediaLink.send(
                    [
                        "cue_ends",
                        self.cuelen + self.enteredCue,
                        self.cuelen
                    ]
                )

    def apply_tracked_values(self, cue) -> Dict[str, Any]:
        # When jumping to a cue that isn't directly the next one, apply and "parent" cues.
        # We go backwards until we find a cue that has no parent. A cue has a parent if and only if it has either
        # an explicit parent or the previous cue in the numbered list either has the default next cue or explicitly
        # references this cue.

        # Returns a dict of backtracked variables for
        # the script context that should be set when entering
        # this cue, but that is nit supported yet
        cobj = self.cues[cue]

        vars = {}

        if (
            self.backtrack
            # Track whenever the cue we are going to is not the next one in the numbering sequence
            and not cue == (self.getDefaultNext())
            and cobj.track
        ):
            to_apply = []
            seen = {}
            safety = 10000
            x = self.getParent(cue)
            while x:
                # No l00ps
                if x in seen:
                    break

                # Don't backtrack past the current cue for no reason
                if x is self.cue:
                    break

                to_apply.append(self.cues[x])
                seen[x] = True
                x = self.getParent(x)
                safety -= 1
                if not safety:
                    break

            # Apply all the lighting changes we would have seen if we had gone through the list one at a time.
            for cuex in reversed(to_apply):
                self.cue_vals_to_numpy_cache(cuex)

                # cuevars = self.cues[cue].values.get("__variables__", {})
                # for i in cuevars:
                #     try:
                #         vars[i] = (i, self.evalExpr(cuevars[i]))
                #     except Exception:
                #         print(traceback.format_exc())
                #         core.rl_log_exc("Error with cue variable " + i)

        return vars

    def preload_next_cue_sound(self):
        # Preload the next cue's sound if we know what it is
        next_cue = None
        if self.cue:
            if self.cue.next_cue == "":
                next_cue = self.getDefaultNext()
            elif self.cue.next_cue in self.cues:
                next_cue = self.cue.next_cue

        if next_cue and next_cue in self.cues:
            c = self.cues[next_cue]
            sound = c.sound
            try:
                sound = self.resolve_sound(sound)
            except Exception:
                return
            if os.path.isfile(sound):
                out = c.sound_output
                if not out:
                    out = self.sound_output
                if not out:
                    out = "@auto"

                try:
                    kaithem.sound.preload(sound, out)
                except Exception:
                    print(traceback.format_exc())

    def resolve_sound(self, sound) -> str:
        return core.resolve_sound(sound)

    def recalc_randomize_modifier(self):
        "Recalculate the random variance to apply to the length"
        if self.cue:
            self.randomizeModifier = random.triangular(
                -float(self.cue.length_randomize), +
                float(self.cue.length_randomize)
            )

    def recalc_cue_len(self):
        "Calculate the actual cue len, without changing the randomizeModifier"
        if not self.active:
            return
        cuelen = self.scriptContext.preprocessArgument(self.cue.length)
        v = cuelen or 0
        v = float(v)

        cuelen_str = str(cuelen)
        if cuelen_str.startswith("@"):
            selector = recur.getConstraint(cuelen_str[1:])
            ref = datetime.datetime.now()
            nextruntime = selector.after(ref, True)

            # Workaround for "every hour" and the like, which would normally return the start of the current hour,
            # But in this case we want the next one.
            # We don't want exclusive matching all the either as that seems a bit buggy.
            if nextruntime <= ref:
                nextruntime = selector.after(nextruntime, False)

            t2 = dt_to_ts(nextruntime, selector.tz)

            nextruntime = t2

            v = nextruntime - time.time()

        else:
            if len(self.cue.sound) and self.cue.rel_length:
                path = self.resolve_sound(self.cue.sound or self.cue.slide)
                if (core.is_img_file(path)):
                    v = 0
                else:
                    try:
                        # If we are doing crossfading, we have to stop slightly early for
                        # The crossfade to work
                        # TODO this should not stop early if the next cue overrides
                        duration = core.get_audio_duration(path)
                        if duration > 0:
                            slen = (duration -
                                    self.crossfade) + cuelen
                            v = max(0, self.randomizeModifier + slen)
                        else:
                            raise RuntimeError(
                                "Failed to get length")
                    except Exception:
                        logging.exception(
                            "Error getting length for sound " + str(path))
                        # Default to 5 mins just so it's obvious there is a problem, and so that the cue actually does end eventually
                        self.cuelen = 300
                        return

            if len(self.cue.slide) and self.cue.rel_length:
                path = self.resolve_sound(self.cue.slide)
                if (core.is_img_file(path)):
                    pass
                else:
                    try:
                        # If we are doing crossfading, we have to stop slightly early for
                        # The crossfade to work
                        # TODO this should not stop early if the next cue overrides
                        duration = core.get_audio_duration(path)
                        if duration > 0:
                            slen = (duration -
                                    self.crossfade) + cuelen
                            # Choose the longer of slide and main sound if both present
                            v = max(0, self.randomizeModifier + slen, v)
                        else:
                            raise RuntimeError(
                                "Failed to get length")
                    except Exception:
                        logging.exception(
                            "Error getting length for sound " + str(path))
                        # Default to 5 mins just so it's obvious there is a problem, and so that the cue actually does end eventually
                        self.cuelen = 300
                        return

        if v <= 0:
            self.cuelen = 0
        else:
            # never go below 0.1*the setting or else you could go to zero and get a never ending cue
            self.cuelen = max(0, float(v * 0.1),
                              self.randomizeModifier + float(v))

    def recalc_cue_vals(self):
        self.cue_vals_to_numpy_cache(self.cue, not self.cue.track)

    def cue_vals_to_numpy_cache(self, cuex: Cue, clearBefore=False):
        """Apply everything from the cue to the fade canvas"""
        # Loop over universes in the cue
        if clearBefore:
            self.cue_cached_vals_as_arrays = {}
            self.cue_cached_alphas_as_arrays = {}

        for i in cuex.values:
            universe = mapUniverse(i)
            if not universe:
                continue

            fixture = None
            try:
                if i[1:] in universes.fixtures:
                    f = universes.fixtures[i[1:]]()
                    if f:
                        fixture = f
            except KeyError:
                print(traceback.format_exc())

            chCount = 0

            if fixture:
                chCount = len(fixture.channels)

            if "__length__" in cuex.values[i]:
                s = cuex.values[i]["__length__"]
                assert s
                repeats = int(self.evalExprFloat(s))
            else:
                repeats = 1

            if "__spacing__" in cuex.values[i]:
                s = cuex.values[i]["__spacing__"]
                assert s
                chCount = int(self.evalExprFloat(s))

            uobj = getUniverse(universe)

            if not uobj:
                continue

            if universe not in self.cue_cached_vals_as_arrays:
                size = len(uobj.values)
                self.cue_cached_vals_as_arrays[universe] = numpy.array(
                    [0.0] * size, dtype="f4"
                )
                self.cue_cached_alphas_as_arrays[universe] = numpy.array(
                    [0.0] * size, dtype="f4"
                )

            if universe not in self.affect:
                self.affect.append(universe)

            self.rerenderOnVarChange = False

            dest = {}

            for j in cuex.values[i]:
                if isinstance(j, str) and j.startswith("__dest__."):
                    dest[j[9:]] = self.evalExpr(
                        cuex.values[i][j] if not (
                            cuex.values[i][j] is None) else 0
                    )

            for idx in range(repeats):
                for j in cuex.values[i]:
                    if isinstance(j, str) and j.startswith("__"):
                        continue

                    cuev = cuex.values[i][j]

                    evaled = self.evalExpr(cuev if not (cuev is None) else 0)
                    # This should always be a float
                    evaled = float(evaled)

                    # Do the blend thing
                    if j in dest:
                        # Repeats is a count, idx is zero based, we want diveder to be 1 on the last index of the set
                        divider = idx / (max(repeats - 1, 1))
                        evaled = (evaled * (1 - divider)) + (dest[j] * divider)

                    x = mapChannel(i, j)
                    if x:
                        universe, channel = x[0], x[1]
                        try:
                            self.cue_cached_alphas_as_arrays[universe][
                                channel + (idx * chCount)
                            ] = (1.0 if cuev is not None else 0)
                            self.cue_cached_vals_as_arrays[universe][
                                channel + (idx * chCount)
                            ] = evaled
                        except Exception:
                            print("err", traceback.format_exc())
                            self.event(
                                "script.error",
                                self.name
                                + " cue "
                                + cuex.name
                                + " Val "
                                + str((universe, channel))
                                + "\n"
                                + traceback.format_exc(),
                            )

                    if isinstance(cuev, str) and cuev.startswith("="):
                        self.rerenderOnVarChange = True

    def make_script_context(self):

        scriptContext = DebugScriptContext(self,
                                           rootContext, variables=self.chandlerVars, gil=core.lock
                                           )

        scriptContext.addNamespace("pagevars")

        def sendMQTT(t, m):
            self.sendMqttMessage(t, m)
            return True

        self.wrMqttCmdSendWrapper = sendMQTT
        scriptContext.commands["sendMQTT"] = sendMQTT
        return scriptContext

    def refreshRules(self, rulesFrom: Optional[Cue] = None):
        with core.lock:
            # We copy over the event recursion depth so that we can detct infinite loops
            if not self.scriptContext:
                self.scriptContext = self.make_script_context()

            self.scriptContext.clearBindings()

            self.scriptContext.setVar("SCENE", self.name)
            self.runningTimers = {}

            if self.active:
                self.scriptContext.setVar("CUE", (rulesFrom or self.cue).name)

                # Actually add the bindings
                rules = (rulesFrom or self.cue).rules
                if rules:
                    self.scriptContext.addBindings(rules)

                loopPrevent = {(rulesFrom or self.cue.name): True}


                x = (rulesFrom or self.cue).inherit_rules
                while x and x.strip():
                    # Avoid infinite loop should the user define a cycle of cue inheritance
                    if x.strip() in loopPrevent:
                        break

                    if x =='__rules__':
                        break
                    
                    loopPrevent[x.strip()] = True

                    self.scriptContext.addBindings(self.cues[x].rules)
                    x = self.cues[x].inherit_rules

                if '__rules__' in self.cues:
                    self.scriptContext.addBindings(self.cues['__rules__'].rules)

                self.scriptContext.startTimers()
                self.doMqttSubscriptions()

            try:
                for board in core.iter_boards():
                    board.linkSend(["scenetimers", self.id, self.runningTimers])
            except Exception:
                core.rl_log_exc("Error handling timer set notification")

    def onMqttMessage(self, topic: str, message: str | bytes):
        try:
            self.event("$mqtt:" + topic, message)
        except Exception:
            self.event("$mqtt:" + topic, json.loads(message.decode("utf-8")))

    def onCueSyncMessage(self, topic: str, message: str):
        gn = self.mqtt_sync_features.get("syncGroup", False)
        if gn:
            # topic = f"/kaithem/chandler/syncgroup/{gn}"
            m = json.loads(message)

            if not self.mqttNodeSessionID == m['senderSessionID']:
                # # Don't listen to old messages, those are just out of sync nonsense that could be
                # # some error.  However if the time is like, really old.  more than 10 hours, assume that
                # # It's because of an NTP issue and we're just outta sync.
                # if (not ((m['time'] < (time.time()-15) )  and (abs(m['time'] - time.time() )> 36000  ))):

                # TODO: Just ignore cues that do not have a sync match

                if m['cue'] in self.cues:
                    # Don't adjust out start time too much. It only exists to fix network latency.
                    self.goto_cue(m['cue'], t=max(min(time.time(
                    ) + 0.5, m['time']), time.time() - 0.5), sendSync=False, cause="MQTT Sync")

    def doMqttSubscriptions(self, keepUnused=120):
        if self.mqttConnection:
            if self.mqtt_sync_features.get("syncGroup", False):

                # In the future we will not use a leading slash
                self.mqttConnection.subscribe(
                    f"/kaithem/chandler/syncgroup/{self.mqtt_sync_features.get('syncGroup',False)}"
                )
                self.mqttConnection.subscribe(
                    f"kaithem/chandler/syncgroup/{self.mqtt_sync_features.get('syncGroup',False)}"
                )

        if self.mqttConnection and self.scriptContext:
            # Subscribe to everything we aren't subscribed to
            for i in self.scriptContext.eventListeners:
                if i.startswith("$mqtt:"):
                    x = i.split(":", 1)
                    if not x[1] in self.mqttSubscribed:
                        self.mqttConnection.subscribe(
                            x[1]
                        )
                        self.mqttSubscribed[x[1]] = True

            # Unsubscribe from no longer used things
            torm = []

            for i in self.mqttSubscribed:
                if not "$mqtt:" + i in self.scriptContext.eventListeners:
                    if i not in self.unusedMqttTopics:
                        self.unusedMqttTopics[i] = time.monotonic()
                        continue
                    elif self.unusedMqttTopics[i] > time.monotonic() - keepUnused:
                        continue
                    self.mqttConnection.unsubscribe(i)
                    del self.unusedMqttTopics[i]
                    torm.append(i)
                else:
                    if i in self.unusedMqttTopics:
                        del self.unusedMqttTopics[i]

            for i in torm:
                del self.mqttSubscribed[i]

    def sendMqttMessage(self, topic, message):
        "JSON encodes message, and publishes it to the scene's MQTT server"
        if self.mqttConnection:
            self.mqttConnection.publish(topic, json.dumps(message))

    def clearDisplayTags(self):
        with core.lock:
            for i in self.displayTagSubscriptions:
                i[0].unsubscribe(i[1])
            self.displayTagSubscriptions = []
            self.displayTagValues = {}
            self.displayTagMeta = {}
            self.displayTagPointObjects = {}

    def displayTagSubscriber(self, n):
        t = n[1]
        if not t.startswith("/"):
            t = "/" + t

        if not self.scriptContext.canGetTagpoint(t):
            raise ValueError("Not allowed tag " + t)

        try:
            t = kaithem.tags.all_tags_raw[t]()
        except Exception:
            t = kaithem.tags[n[1]]
        if not t:
            t = kaithem.tags[n[1]]

        sn = n[1]
        self.displayTagMeta[sn] = {}
        if isinstance(t, kaithem.tags.NumericTagPointClass):
            self.displayTagMeta[sn]["min"] = t.min
            self.displayTagMeta[sn]["max"] = t.max
            self.displayTagMeta[sn]["hi"] = t.hi
            self.displayTagMeta[sn]["lo"] = t.lo
            self.displayTagMeta[sn]["unit"] = t.unit
        self.displayTagMeta[sn]["subtype"] = t.subtype

        self.pushMeta(keys=["displayTagMeta"])

        def f(v, t, a):
            self.displayTagValues[sn] = v
            self.pushMeta(keys=["displayTagValues"])

        t.subscribe(f)
        self.displayTagValues[sn] = t.value
        self.pushMeta(keys=["displayTagValues"])

        return t, f

    def setDisplayTags(self, dt):
        dt = dt[:]
        with core.lock:
            self.clearDisplayTags()
            gc.collect()
            gc.collect()
            gc.collect()

            try:
                for i in dt:

                    # Upgrade legacy format
                    if len(i) == 2:
                        i.append({'type': 'auto'})

                    if 'type' not in i[2]:
                        i[2]['type'] = 'auto'

                    if not i[1].startswith("="):
                        t = None

                        if i[2]['type'] == 'numeric_input':
                            t = kaithem.tags[i[1]]

                        if i[2]['type'] == 'switch_input':
                            t = kaithem.tags[i[1]]

                        if i[2]['type'] == 'string_input':
                            t = kaithem.tags.StringTag(i[1])

                        if t:
                            self.displayTagPointObjects[i[1]] = t

                    self.displayTagSubscriptions.append(
                        self.displayTagSubscriber(i))
            except Exception:
                print(traceback.format_exc())
                self.event('board.error', traceback.format_exc())
            self.display_tags = dt

    def clear_configured_tags(self):
        with core.lock:
            for i in self.command_tagSubscriptions:
                i[0].unsubscribe(i[1])
            self.command_tagSubscriptions = []

    def command_tag_subscriber(self):
        sn = self.name

        def f(v, t, a):
            v = v[0]

            if v.startswith("launch:"):
                shortcutCode(str(v[len("launch:"):]), sn)

            elif v == "Rev":
                self.prev_cue(cause="ECP")

            elif v == "Fwd":
                self.next_cue(cause="ECP")

            elif v == "VolumeUp":
                self.setAlpha(self.alpha + 0.07)

            elif v == "VolumeDown":
                self.setAlpha(self.alpha - 0.07)

            elif v == "VolumeMute":
                self.setAlpha(0)

            elif v == "Play":
                if self.active:
                    self.stop()
                else:
                    self.go()

            elif v == "VolumeMute":
                self.setAlpha(0)

            if v.startswith("Lit_"):
                self.event("button." + v[4:], None)

        return f

    def subscribe_command_tags(self):
        if not self.command_tag.strip():
            return
        with core.lock:
            for i in [self.command_tag]:
                t = kaithem.tags.ObjectTag(i)
                s = self.command_tag_subscriber()
                self.command_tagSubscriptions.append([t, s])
                t.subscribe(s)

    def rename_cue(self, old: str, new: str):
        disallow_special(new, allowedCueNameSpecials)
        if new[0] in "1234567890 \t_":
            new = "x" + new

        if self.cue.name == old:
            raise RuntimeError("Can't rename active cue")
        if new in self.cues:
            raise RuntimeError("Already exists")
        if old == 'default':
            raise RuntimeError("Can't rename default cue")

        cue = self.cues.pop(old)
        cue.name = new
        cue.named_for_sound = False
        self.cues[new] = cue

        # Delete old, push new
        for board in core.iter_boards():
            if len(board.newDataFunctions) < 100:
                board.newDataFunctions.append(
                    lambda s: s.linkSend(["delcue", cue.id]))

        cue.push()

    def set_command_tag(self, tag_name: str):
        tag_name = tag_name.strip()

        self.clear_configured_tags()

        self.command_tag = tag_name

        if tag_name:
            tag = kaithem.tags.ObjectTag(tag_name)
            if tag.subtype and not tag.subtype == "event":
                raise ValueError("That tag does not have the event subtype")

            self.subscribe_command_tags()

    def next_cue(self, t=None, cause="generic"):

        cue = self.cue
        if not cue:
            return

        with core.lock:
            if cue.next_cue and (
                (self.evalExpr(cue.next_cue).split("?")[0] in self.cues)
                or cue.next_cue.startswith("__")
                or "|" in cue.next_cue
                or "*" in cue.next_cue
            ):
                self.goto_cue(cue.next_cue, t, cause=cause)
            elif not cue.next_cue:
                x = self.getDefaultNext()
                if x:
                    self.goto_cue(x, t)

    def prev_cue(self, cause="generic"):
        with core.lock:
            if len(self.cueHistory) > 1:
                c = self.cueHistory[-2]
                c = c[0]
                self.goto_cue(c, cause=cause)

    def setup_blend_args(self):
        if hasattr(self.blendClass, "parameters"):
            for i in self.blendClass.parameters:
                if i not in self.blend_args:
                    self.blend_args[i] = self.blendClass.parameters[i][3]

    def go(self, nohandoff=False):
        global active_scenes, _active_scenes
        self.setDisplayTags(self.display_tags)

        with core.lock:
            if self in active_scenes:
                return

            # Not sure if we need to remake this, keep it for defensive
            # reasons, TODO
            self.canvas = FadeCanvas()

            self.manualAlpha = False
            self.active = True

            if not self.cue:
                self.goto_cue("default", sendSync=False, cause="start")
            else:
                # Re-enter cue to create the cache
                self.goto_cue(self.cue.name, cause="start")
            # Bug workaround for bug where scenes do nothing when first activated
            self.canvas.paint(
                0,
                vals=self.cue_cached_vals_as_arrays,
                alphas=self.cue_cached_alphas_as_arrays,
            )

            self.enteredCue = time.time()

            if self.blend in blendmodes.blendmodes:
                self._blend = blendmodes.blendmodes[self.blend](self)

            self.effectiveValues = None

            self.hasNewInfo = {}
            self.started = time.time()

            if self not in _active_scenes:
                _active_scenes.append(self)
            _active_scenes = sorted(
                _active_scenes, key=lambda k: (k.priority, k.started)
            )
            active_scenes = _active_scenes[:]

            self.setMqttServer(self.mqtt_server)

            # Minor inefficiency rendering twice the first frame
            self.rerender = True
            # self.render()

    def isActive(self):
        return self.active

    @property
    def priority(self):
        return self._priority

    @priority.setter
    def priority(self, p: float):
        global active_scenes, _active_scenes
        self.hasNewInfo = {}
        self._priority = p
        with core.lock:
            _active_scenes = sorted(
                _active_scenes, key=lambda k: (k.priority, k.started)
            )
            active_scenes = _active_scenes[:]
            try:
                for i in self.affect:
                    rerenderUniverse(i)
            except Exception:
                print(traceback.format_exc())

    def mqttStatusEvent(self, value: str, timestamp: float, annotation: Any):
        if value == "connected":
            self.event("board.mqtt.connect")
        else:
            self.event("board.mqtt.disconnect")

        self.pushMeta(statusOnly=True)

    @typechecked
    def setMqttServer(self, mqtt_server: str):
        with self.lock:
            x = mqtt_server.strip().split(":")
            server = x[0]
            if len(x) > 1:
                port = int(x[-1])
                server = x[-2]
            else:
                port = 1883

            if mqtt_server == self.activeMqttServer:
                return

            # Track time.monotonic of when they became unused
            self.unusedMqttTopics: Dict[str, float] = {}

            if self.mqttConnection:
                self.mqttConnection.disconnect()
                self.mqttConnection = None

            if mqtt_server:
                if self in active_scenes:

                    self.mqttConnection = makeWrappedConnectionClass(self)(
                        server,
                        port,
                    )

                    self.mqttSubscribed = {}

            else:
                self.mqttConnection = None
                self.mqttSubscribed = {}

            # Do after so we can get the err on bad format first
            self.mqtt_server = self.activeMqttServer = mqtt_server

            self.doMqttSubscriptions()

    def setName(self, name: str):
        disallow_special(name)
        if self.name == "":
            raise ValueError("Cannot name scene an empty string")
        if not isinstance(name, str):
            raise TypeError("Name must be str")
        with core.lock:
            if name in scenes_by_name:
                raise ValueError("Name in use")
            if self.name in scenes_by_name:
                del scenes_by_name[self.name]
            self.name = name
            scenes_by_name[name] = self
            self.hasNewInfo = {}
            self.scriptContext.setVar("SCENE", self.name)

    def setMQTTFeature(self, feature: str, state):
        if state:
            self.mqtt_sync_features[feature] = state
        else:
            self.mqtt_sync_features.pop(feature, None)
        self.hasNewInfo = {}
        self.doMqttSubscriptions()

    @property
    def backtrack(self):
        return self._backtrack

    @backtrack.setter
    def backtrack(self, b):
        b = bool(b)
        if self._backtrack == b:
            return
        else:
            self._backtrack = b
            x = self.enteredCue
            self.goto_cue(self.cue.name)
            self.enteredCue = x
            self.rerender = True
        self.hasNewInfo = {}

    def setBPM(self, b):
        b = float(b)
        if self.bpm == b:
            return
        else:
            self.bpm = b
            self.rerender = True
        self.hasNewInfo = {}

    def tap(self, t: Optional[float] = None):
        "Do a tap tempo tap. If the tap happened earlier, use t to enter that time"
        t = t or time.time()

        x = t - self.lastTap

        self.lastTap = t

        time_per_beat = 60 / self.bpm

        # More than 8s, we're starting a new tap tapSequence
        if x > 8:
            self.tapSequence = 0

        # If we are more than 5 percent off from where the beat is expected,
        # Start agaon
        if self.tapSequence > 1:
            if abs(x - time_per_beat) > time_per_beat * 0.05:
                self.tapSequence = 0

        if self.tapSequence:
            f = max((1 / self.tapSequence) ** 2, 0.0025)
            self.bpm = self.bpm * (1 - f) + (60 / (x)) * f
        self.tapSequence += 1

        ts = t - self.enteredCue
        beats = ts / time_per_beat

        fbeat = beats % 1
        # We are almost right on where a beat would be, make a small phase adjustment

        # Back project N beats into the past finding the closest beat to when we entered the cue
        new_ts = round(beats) * time_per_beat
        x = t - new_ts

        if (fbeat < 0.1 or fbeat > 0.90) and self.tapSequence:
            # Filter between that backprojected time and the real time
            # Yes I know we already incremented tapSequence
            f = 1 / self.tapSequence**1.2
            self.enteredCue = self.enteredCue * (1 - f) + x * f
        elif self.tapSequence:
            # Just change enteredCue to match the phase.
            self.enteredCue = x
        self.pushMeta(keys={"bpm"})

    def stop(self):
        global active_scenes, _active_scenes
        with core.lock:
            # No need to set rerender
            if self.scriptContext:
                self.scriptContext.clearBindings()
                self.scriptContext.clearState()

            # Use the cue as the marker of if we actually
            # Completed the stop, not just if we logically should be stopped
            # Because we want to be able to manually retry that if we failed.
            if not self.cue:
                return

            # Just using this to get rid of prev value
            self._blend = blendmodes.HardcodedBlendMode(self)
            self.hasNewInfo = {}

            try:
                for i in self.affect:
                    rerenderUniverse(i)
            except Exception:
                print(traceback.format_exc())

            self.affect = []
            if self in _active_scenes:
                _active_scenes.remove(self)
                active_scenes = _active_scenes[:]

            self.active = False
            self.cue_cached_vals_as_arrays = {}
            self.cue_cached_alphas_as_arrays = {}
            kaithem.sound.stop(str(self.id))

            self.runningTimers.clear()

            try:
                for board in core.iter_boards():
                    board.linkSend(["scenetimers", self.id, self.runningTimers])
            except Exception:
                core.rl_log_exc("Error handling timer set notification")
                print(traceback.format_exc())
            # fALLBACK
            self.cue = self.cues.get('default', list(self.cues.values())[0])
            self.cueTagClaim.set("__stopped__", annotation="SceneObject")
            self.doMqttSubscriptions(keepUnused=0)

    def noteOn(self, ch: int, note: int, vel: float):
        self.event("midi.note:" + str(ch) + "." + number_to_note(note), vel)

    def noteOff(self, ch: int, note: int):
        self.event("midi.noteoff:" + str(ch) + "." + number_to_note(note), 0)

    def cc(self, ch: int, n: int, v: float):
        self.event("midi.cc:" + str(ch) + "." + str(n), v)

    def pitch(self, ch: int, v: int):
        self.event("midi.pitch:" + str(ch), v)

    @property
    def midi_source(self):
        return self._midi_source

    @midi_source.setter
    def midi_source(self, s: str):
        if s == self._midi_source:
            return

        if not s:
            kaithem.message.unsubscribe(
                "/midi/"
                + s.replace(":", "_")
                .replace("[", "")
                .replace("]", "")
                .replace(" ", ""),
                self.onMidiMessage,
            )
        else:
            kaithem.message.subscribe(
                "/midi/"
                + s.replace(":", "_")
                .replace("[", "")
                .replace("]", "")
                .replace(" ", ""),
                self.onMidiMessage,
            )

        self._midi_source = s

    def onMidiMessage(self, t: str, v: List[Any]):
        if v[0] == "noteon":
            self.noteOn(v[1], v[2], v[3])
        if v[0] == "noteoff":
            self.noteOff(v[1], v[2])
        if v[0] == "cc":
            self.cc(v[1], v[2], v[3])
        if v[0] == "pitch":
            self.pitch(v[1], v[2])

    def setMusicVisualizations(self, s: str):
        if s == self.music_visualizations:
            return

        s2 = ""
        for i in s.split("\n"):
            if i.strip():
                s2 += i.strip() + "\n"

        self.music_visualizations = s2
        self.sendVisualizations()
        self.pushMeta(keys={"music_visualizations"})

    def sendVisualizations(self):
        self.mediaLink.send(
            [
                "butterchurnfiles",
                [
                    i.split("milkdrop:")[-1]
                    for i in self.music_visualizations.split("\n")
                    if i
                ],
            ]
        )

    def setAlpha(self, val: float, sd: bool = False):
        val = min(1, max(0, val))
        try:
            self.cueVolume = min(
                5, max(0, float(self.evalExpr(self.cue.sound_volume))))
        except Exception:
            self.event(
                "script.error",
                self.name + " in cueVolume eval:\n" + traceback.format_exc(),
            )
            self.cueVolume = 1

        kaithem.sound.setvol(val * self.cueVolume, str(self.id))

        if not self.isActive() and val > 0:
            self.go()
        self.manualAlpha = True
        self.alpha = val
        self.alphaTagClaim.set(val, annotation="SceneObject")
        if sd:
            self.default_alpha = val
            self.pushMeta(keys={"alpha", "default_alpha"})
        else:
            self.pushMeta(keys={"alpha", "default_alpha"})
        self.rerender = True

        self.mediaLink.send(["volume", val])

    def add_cue(self, name: str, **kw: Any):
        return Cue(self, name, **kw)

    def setBlend(self, blend: str):
        disallow_special(blend)
        blend = str(blend)[:256]
        self.blend = blend
        if blend in blendmodes.blendmodes:
            if self.isActive():
                self._blend = blendmodes.blendmodes[blend](self)
            self.blendClass = blendmodes.blendmodes[blend]
            self.setup_blend_args()
        else:
            self.blend_args = self.blend_args or {}
            self._blend = blendmodes.HardcodedBlendMode(self)
            self.blendClass = blendmodes.HardcodedBlendMode
        self.rerender = True
        self.hasNewInfo = {}

    def setBlendArg(self, key: str, val: float | bool | str):
        disallow_special(key, "_")
        # serializableness check
        json.dumps(val)
        if (
            not hasattr(self.blendClass, "parameters")
            or key not in self.blendClass.parameters
        ):
            raise KeyError("No such param")

        if val is None:
            del self.blend_args[key]
        else:
            if self.blendClass.parameters[key][1] == "number":
                val = float(val)
            self.blend_args[key] = val
        self.rerender = True
        self.hasNewInfo = {}

    def render(self, force_repaint=False):
        "Calculate the current alpha value, handle stopping the scene and spawning the next one"
        if self.cue.fade_in:
            fadePosition: float = min(
                (time.time() - self.enteredCue) /
                (self.cue.fade_in * (60.0 / self.bpm)), 1.0
            )
            fadePosition = ease(fadePosition)
        else:
            fadePosition = 1

        if fadePosition < 1:
            self.rerender = True

        # TODO: We absolutely should not have to do this every time we rerender.
        # Bugfix is in order!
        # self.canvas.paint(fadePosition,vals=self.cue_cached_vals_as_arrays, alphas=self.cue_cached_alphas_as_arrays)

        # Remember, we can and do the next cue thing and still need to repaint, because sometimes the next cue thing does nothing
        if force_repaint or (not self.fade_in_completed):
            self.canvas.paint(
                fadePosition,
                vals=self.cue_cached_vals_as_arrays,
                alphas=self.cue_cached_alphas_as_arrays,
            )
            if fadePosition >= 1:
                # We no longer affect universes from the previous cue we are fading from

                # But we *do* still keep tracked and backtracked values.
                self.affect = []
                for i in self.cue_cached_vals_as_arrays:
                    u = mapUniverse(i)
                    if u and u in universes.universes:
                        if u not in self.affect:
                            self.affect.append(u)

                # Remove unused universes from the cue
                self.canvas.clean(self.cue_cached_vals_as_arrays)
                self.fade_in_completed = True
                self.rerender = True

        if self.cuelen and (time.time() - self.enteredCue) > self.cuelen * (
            60 / self.bpm
        ):
            # rel_length cues end after the sound in a totally different part of code
            # Calculate the "real" time we entered, which is exactly the previous entry time plus the len.
            # Then round to the nearest millisecond to prevent long term drift due to floating point issues.
            self.next_cue(
                round(self.enteredCue + self.cuelen * (60 / self.bpm), 3), cause="time"
            )

    def updateMonitorValues(self):
        if self.blend == "monitor":
            data = self.cue.values
            for i in data:
                for j in data[i]:
                    x = mapChannel(i, j)
                    if x:
                        u = getUniverse(x[0])
                        if u:
                            v = u.values[x[1]]
                            self.cue.values[i][j] = float(v)
            self.valueschanged = {}

    def new_cue_from_sound(self, snd):
        bn = os.path.basename(snd)
        bn = fnToCueName(bn)
        try:
            tags = TinyTag.get(snd)
            if tags.artist and tags.title:
                bn = tags.title + " ~ " + tags.artist
        except Exception:
            print(traceback.format_exc())

        bn = disallow_special(bn, "_~", replaceMode=" ")
        if bn not in self.cues:
            self.add_cue(bn)
            self.cues[bn].rel_length = True
            self.cues[bn].length = 0.01

            soundfolders = core.getSoundFolders()
            s = None
            for i in soundfolders:
                s = snd
                # Make paths relative to a sound folder
                if not i.endswith("/"):
                    i = i + "/"
                if s.startswith(i):
                    s = s[len(i):]
                    break
            if not s:
                raise RuntimeError("Unknown, linter said was possible")
            self.cues[bn].sound = s
            self.cues[bn].named_for_sound = True

    def import_m3u(self, d):
        d = d.replace("\r", '').split("\n")

        info = None

        for i in d:
            if i.strip().startswith("#EXTINF:"):
                info = i.strip().split(",")[-1]

            if i.strip() and not i.strip().startswith("#"):
                i = os.path.expanduser(i)
                try:
                    if os.path.exists(i.strip()):
                        self.new_cue_from_sound(i.strip())
                    else:
                        # Try to find it wherever it may be.
                        # This is a fuzzy match that could in theory make mistakes.
                        i2 = core.resolve_sound_fuzzy(i)
                        if os.path.exists(i2):
                            self.new_cue_from_sound(i2, mame=i.info)
                        else:
                            event("board.error", "Error locating "+str(i))
                except Exception:
                    event("board.error", "Error locating "+str(i))

                info = None

    def get_m3u(self, rel=None):
        "Convert the sounds mentioned in cues to m3u files."
        o = "#EXTM3U\r\n\r\n"

        for i in self.cues_ordered:
            if i.sound:
                try:
                    c = self.resolve_sound(i.sound)

                    d = core.get_audio_duration(c)

                    # If name not autogenerated, add it to playlist file
                    n = "," + i.name
                    if i.named_for_sound:
                        n = ''

                    if d:
                        o += "#EXTINF:"+str(d)+n + "\r\n"
                    else:
                        if (not i.rel_length) and i.length:
                            o += "#EXTINF:"+str(i.length)+n + "\r\n"

                    h = os.path.expanduser("~")

                    if c.startswith(h):
                        c = "~"+c[len(h):]

                    o += c + "\r\n"

                except Exception:
                    pass

        return o
