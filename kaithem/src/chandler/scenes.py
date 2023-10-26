
from __future__ import annotations
from .core import disallow_special
from .universes import getUniverse, rerenderUniverse, mapUniverse, mapChannel
from ..kaithemobj import kaithem
from .soundmanager import fadeSound, playSound, stopSound
from . import core
from . import universes
from . import blendmodes
from . import mqtt
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
from typing import Any, Dict, Optional, Type, Iterable, List
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

_activeScenes = []
activeScenes = []


def makeWrappedConnectionClass(parent: Scene):
    self_closure_ref = parent

    class Connection(mqtt.MQTTConnection):
        def on_connect(self):
            self_closure_ref.event("board.mqtt.connected")
            self_closure_ref.pushMeta(statusOnly=True)
            return super().on_connect()

        def on_disconnect(self):
            self_closure_ref.event("board.mqtt.disconnected")
            self_closure_ref.pushMeta(statusOnly=True)
            if self_closure_ref.mqttServer:
                self_closure_ref.event("board.mqtt.error", "Disconnected")
            return super().on_disconnect()

        def on_message(self, t: str, m: bytes):
            gn = self_closure_ref.mqttSyncFeatures.get("syncGroup", False)
            if gn:
                topic = f"/kaithem/chandler/syncgroup/{gn}"
                if t == topic:
                    self_closure_ref.onCueSyncMessage(t, m)

            self_closure_ref.onMqttMessage(t, m)

            return super().on_message(t, m)

    return Connection


def makeBlankArray(size: int):
    x = [0] * size
    return numpy.array(x, dtype="f4")


class FadeCanvas:
    def __init__(self):
        "Handles calculating the effect of one scene over a background. This doesn't do blend modes, it just interpolates."
        self.v: Dict[str, numpy.typing.NDArray[Any]] = {}
        self.a: Dict[str, numpy.typing.NDArray[Any]] = {}
        self.v2: Dict[str, numpy.typing.NDArray[Any]] = {}
        self.a2: Dict[str, numpy.typing.NDArray[Any]] = {}

    def paint(self, fade: float | int, vals: Dict[str, numpy.typing.NDArray[Any]], alphas: Dict[str, numpy.typing.NDArray[Any]]):
        """
        Makes v2 and a2 equal to the current background overlayed with values from scene which is any object that has dicts of dicts of vals and and
        alpha.

        Should you have cached dicts of arrays vals and alpha channels(one pair of arrays per universe), put them in vals and arrays
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

    def clean(self, affect):
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


def codeCommand(code=""):
    "Activates any cues with the matching shortcut code in any scene"
    shortcutCode(code)
    return True


def gotoCommand(scene="=SCENE", cue=""):
    "Triggers a scene to go to a cue.  Ends handling of any further bindings on the current event"

    # Ignore empty
    if not cue.strip():
        return True

    # Track layers of recursion
    newcause = "script.0"
    if kaithem.chandlerscript.contextInfo.event[0] in ("cue.enter", "cue.exit"):
        cause = kaithem.chandlerscript.contextInfo.event[1][1]
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
    scenes_by_name[scene].gotoCue(cue, cause=newcause)
    return True


gotoCommand.completionTags = {
    "scene": "gotoSceneNamesCompleter",
    "cue": "gotoSceneCuesCompleter",
}


def setAlphaCommand(scene="=SCENE", alpha=1):
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


def eventCommand(scene="=SCENE", ev="DummyEvent", value=""):
    "Send an event to a scene, or to all scenes if scene is __global__"
    if scene == "__global__":
        event(ev, value)
    else:
        scenes_by_name[scene].event(ev, value)
    return True


rootContext.commands["shortcut"] = codeCommand
rootContext.commands["goto"] = gotoCommand
rootContext.commands["setAlpha"] = setAlphaCommand
rootContext.commands["ifCue"] = ifCueCommand
rootContext.commands["sendEvent"] = eventCommand

rootContext.commands["setTag"].completionTags = {
    "tagName": "tagPointsCompleter"}


def sendMqttMessage(topic, message):
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


def shortcutCode(code: str, limitScene: Optional[Scene] = None, exclude: Optional[Scene] = None):
    "API to activate a cue by it's shortcut code"
    if not limitScene:
        event("shortcut." + str(code)[:64], None)

    with core.lock:
        if code in shortcut_codes:
            for i in shortcut_codes[code]:
                try:
                    x = i.scene()
                    if limitScene:
                        if (x is not limitScene) and not (x.name == limitScene):
                            print("skip " + x.name, limitScene)
                            continue
                        if (x is not exclude):
                            x.event("shortcut." + str(code)[:64])
                    else:
                        if x and x is not exclude:
                            x.go()
                            x.gotoCue(i.name, cause="manual")
                except Exception:
                    print(traceback.format_exc())


def event(s: str, value=None, info=""):
    "THIS IS THE ONLY TIME THE INFO THING DOES ANYTHING"
    # disallow_special(s, allow=".")
    with core.lock:
        for i in activeScenes:
            i._event(s, value=value, info=info)


class DebugScriptContext(kaithem.chandlerscript.ChandlerScriptContext):
    def __init__(self, sceneObj, *a, **k):
        self.sceneObj = weakref.ref(sceneObj)
        self.sceneName = sceneObj.name
        self.sceneId = sceneObj.id
        super().__init__(*a, **k)

    def onVarSet(self, k, v):
        scene = self.sceneObj()
        if scene:
            try:
                if not k == "_" and scene.rerenderOnVarChange:
                    scene.recalcCueVals()
                    scene.rerender = True

            except Exception:
                core.rl_log_exc("Error handling var set notification")
                print(traceback.format_exc())

            try:
                if not k.startswith("_"):
                    for i in core.boards:
                        if isinstance(v, (str, int, float, bool)):
                            i().link.send(["varchange", self.sceneId, k, v])
                        elif isinstance(v, collections.defaultdict):
                            v = json.dumps(v)[:160]
                            i().link.send(["varchange", self.sceneId, k, v])
                        else:
                            v = str(v)[:160]
                            i().link.send(["varchange", self.sceneId, k, v])
            except Exception:
                core.rl_log_exc("Error handling var set notification")
                print(traceback.format_exc())

    def event(self, e: str, v: str | float | int | bool | None = None):
        kaithem.chandlerscript.ChandlerScriptContext.event(self, e, v)
        try:
            for i in core.boards:
                i().pushEv(e, self.sceneName, time.time(), value=v)
        except Exception:
            core.rl_log_exc("error handling event")
            print(traceback.format_exc())

    def onTimerChange(self, timer, run):
        scene = self.sceneObj()
        if scene:
            scene.runningTimers[timer] = run
            try:
                for i in core.boards:
                    i().link.send(
                        ["scenetimers", self.sceneName, scene.runningTimers]
                    )
            except Exception:
                core.rl_log_exc("Error handling timer set notification")
                print(traceback.format_exc())

    def canGetTagpoint(self, t):
        if t not in self.tagpoints and len(self.tagpoints) > 128:
            raise RuntimeError("Too many tagpoints in one scene")
        return t


def checkPermissionsForSceneData(data, user):
    """Check if used can upload or edit the scene, ekse raise an error if it uses advanced features that would prevent that action.
    We disallow delete because we don't want unprivelaged users to delete something important that they can't fix.

    """
    if "page" in data and (
        data["page"]["html"].strip()
        or data["page"]["js"].strip()
        or data["page"].get("rawhtml", "").strip()
    ):
        if not kaithem.users.checkPermission(user, "/admin/modules.edit"):
            raise ValueError(
                "You cannot do this action on this scene without /admin/modules.edit, because it uses advanced features: pages. User:"
                + str(kaithem.web.user())
            )
    if "mqttServer" in data and data["mqttServer"].strip():
        if not kaithem.users.checkPermission(user, "/admin/modules.edit"):
            raise ValueError(
                "You cannot do this action on this scene without /admin/modules.edit, because it uses advanced features: MQTT:"
                + str(kaithem.web.user())
            )


cues: weakref.WeakValueDictionary[str, Cue] = weakref.WeakValueDictionary()

cueDefaults: Dict[str, int | float | Dict[Any, Any] | List[Any] | bool | None | str] = {
    "fadein": 0,
    "soundFadeOut": 0,
    "soundFadeIn": 0,
    "length": 0,
    "track": True,
    "nextCue": "",
    "sound": "",
    "slide": "",
    "notes": "",
    "soundOutput": "",
    "soundStartPosition": 0,
    "mediaSpeed": 1,
    "mediaWindup": 0,
    "mediaWinddown": 1,
    "rel_length": False,
    "lengthRandomize": 0,
    "inheritRules": "",
    "rules": [],
    "probability": "",
    "values": {},
    "soundVolume": 1,
    "soundLoops": 0,
    "triggerShortcut": "",
    "namedForSound": False,
}


class Cue:
    "A static set of values with a fade in and out duration"
    __slots__ = [
        "id",
        "changed",
        "next_ll",
        "alpha",
        "fadein",
        "length",
        "lengthRandomize",
        "name",
        "values",
        "scene",
        "nextCue",
        "track",
        "notes",
        "shortcut",
        "number",
        "inherit",
        "sound",
        "slide",
        "rel_length",
        "soundOutput",
        "soundStartPosition",
        "mediaSpeed",
        "mediaWindup",
        "mediaWinddown",
        "onEnter",
        "onExit",
        "associations",
        "rules",
        "reentrant",
        "inheritRules",
        "soundFadeIn",
        "soundFadeOut",
        "soundVolume",
        "soundLoops",
        "namedForSound",
        "probability",
        "triggerShortcut",
        "__weakref__",
    ]

    def __init__(
        self,
        parent,
        name: str,
        forceAdd=False,
        values=None,
        alpha=1,
        fadein=0,
        length=0,
        track=True,
        nextCue=None,
        shortcut="",
        sound="",
        slide="",
        soundOutput="",
        soundStartPosition=0,
        mediaSpeed=1,
        mediaWindup=0,
        mediaWinddown=0,
        rel_length=False,
        id=None,
        number=None,
        lengthRandomize=0,
        script="",
        onEnter=None,
        onExit=None,
        rules=None,
        reentrant=True,
        soundFadeIn=0,
        notes="",
        soundFadeOut=0,
        inheritRules="",
        soundVolume=1,
        soundLoops=0,
        namedForSound=False,
        probability="",
        triggerShortcut="",
        **kw
    ):
        # This is so we can loop through them and push to gui
        self.id = uuid.uuid4().hex
        self.name = name
        self.triggerShortcut = triggerShortcut

        # Now unused
        # self.script = script
        self.onEnter = onEnter
        self.onExit = onExit
        self.inheritRules = inheritRules or ""
        self.reentrant = True
        self.soundVolume = soundVolume
        self.soundLoops = soundLoops
        self.namedForSound = namedForSound
        self.probability = probability
        self.notes = ""

        # Rules created via the GUI logic editor
        self.rules: Optional[List[List[Any]]] = rules or []

        disallow_special(name, allowedCueNameSpecials)
        if name[0] in "1234567890 \t_":
            name = "x" + name

        if id:
            disallow_special(id)
        self.inherit = None
        cues[self.id] = self
        # Odd circular dependancy
        try:
            self.number = number or parent.cues_ordered[-1].number + 5000
        except Exception:
            self.number = 5000
        self.next_ll = None
        parent._addCue(self, forceAdd=forceAdd)
        self.changed = {}
        self.alpha = alpha
        self.fadein = fadein
        self.soundFadeOut = soundFadeOut
        self.soundFadeIn = soundFadeIn

        self.length = length
        self.rel_length = rel_length
        self.lengthRandomize = lengthRandomize
        self.values: Dict[str, Dict[str, str | int | float]] = values or {}
        self.scene: weakref.ref[Scene] = weakref.ref(parent)
        self.nextCue: str = nextCue or ""
        # Note: This refers to tracking as found on lighting gear, not the old concept of track from
        # the first version
        self.track = track
        self.shortcut = None
        self.sound = sound or ""
        self.slide = slide or ""
        self.soundOutput = soundOutput or ""
        self.soundStartPosition = soundStartPosition
        self.mediaSpeed = mediaSpeed
        self.mediaWindup = mediaWindup
        self.mediaWinddown = mediaWinddown

        self.setShortcut(shortcut, False)

        self.push()

    def serialize(self):
        x = {
            "fadein": self.fadein,
            "length": self.length,
            "lengthRandomize": self.lengthRandomize,
            "shortcut": self.shortcut,
            "values": self.values,
            "nextCue": self.nextCue,
            "track": self.track,
            "notes": self.notes,
            "number": self.number,
            "sound": self.sound,
            "soundOutput": self.soundOutput,
            "soundStartPosition": self.soundStartPosition,
            "slide": self.slide,
            "mediaSpeed": self.mediaSpeed,
            "mediaWindup": self.mediaWindup,
            "mediaWinddown": self.mediaWinddown,
            "rel_length": self.rel_length,
            "probability": self.probability,
            "rules": self.rules,
            "reentrant": self.reentrant,
            "inheritRules": self.inheritRules,
            "soundFadeIn": self.soundFadeIn,
            "soundFadeOut": self.soundFadeOut,
            "soundVolume": self.soundVolume,
            "soundLoops": self.soundLoops,
            "namedForSound": self.namedForSound,
            "triggerShortcut": self.triggerShortcut,
        }

        # Cleanup defaults
        if x["shortcut"] == number_to_shortcut(self.number):
            del x["shortcut"]
        for i in cueDefaults:
            if str(x[i]) == str(cueDefaults[i]):
                del x[i]
        return x

    def getScene(self):
        s = self.scene()
        if not s:
            raise RuntimeError("Scene must have been deleted")
        return s

    def push(self):
        for i in core.boards:
            if len(i().newDataFunctions) < 100:
                i().newDataFunctions.append(lambda s: s.pushCueMeta(self.id))

    def pushData(self):
        for i in core.boards:
            if len(i().newDataFunctions) < 100:
                i().newDataFunctions.append(lambda s: s.pushCueData(self.id))

    def pushoneval(self, u, ch, v):
        for i in core.boards:
            if len(i().newDataFunctions) < 100:
                i().newDataFunctions.append(
                    lambda s: s.link.send(["scv", self.id, u, ch, v])
                )

    def clone(self, name):
        name = self.getScene().evalExpr(name)

        if name in self.getScene().cues:
            raise RuntimeError("Cannot duplicate cue names in one scene")

        c = Cue(
            self.getScene(),
            name,
            fadein=self.fadein,
            length=self.length,
            lengthRandomize=self.lengthRandomize,
            values=copy.deepcopy(self.values),
            nextCue=self.nextCue,
            rel_length=self.rel_length,
        )

        for i in core.boards:
            if len(i().newDataFunctions) < 100:
                i().newDataFunctions.append(lambda s: s.pushCueMeta(c.id))
        for i in core.boards:
            if len(i().newDataFunctions) < 100:
                i().newDataFunctions.append(lambda s: s.pushCueData(c.id))

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

    def setRules(self, r):
        self.rules = r
        self.getScene().refreshRules()

    def setInheritRules(self, r):
        self.inheritRules = r
        self.getScene().refreshRules()

    def setShortcut(self, code, push=True):
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

    def setValue(self, universe, channel, value):
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
        elif isinstance(channel, str):
            x = channel.strip()
            if not x == channel:
                raise Exception(
                    "Channel name cannot begin or end with whitespace")

            # If it looks like an int, cast it even if it's a string,
            # We get a lot of raw user input that looks like that.
            try:
                channel = float(channel)
            except ValueError:
                pass
        else:
            raise Exception("Only str or int channel numbers allowed")

        # Assume anything that can be an int, is meant to be
        if isinstance(channel, str):
            try:
                channel = int(channel)
            except ValueError:
                pass

        with core.lock:
            if universe == "__variables__":
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
                    scene.cueValsToNumpyCache(self, False)

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


class Scene:
    "An objecting representing one scene. If noe default cue present one is made"

    def __init__(
        self,
        name: str,
        cues=None,
        active=False,
        alpha: float = 1,
        priority=50,
        blend="normal",
        id=None,
        defaultActive=True,
        blendArgs=None,
        backtrack=True,
        bpm=60,
        soundOutput="",
        eventButtons=[],
        displayTags=[],
        infoDisplay="",
        utility=False,
        notes="",
        mqttServer="",
        crossfade=0,
        midiSource="",
        defaultNext="",
        commandTag="",
        slideOverlayURL="",
        musicVisualizations="",
        mqttSyncFeatures=None,
        **ignoredParams
    ):
        if name and name in scenes_by_name:
            raise RuntimeError("Cannot have 2 scenes sharing a name: " + name)

        if not name.strip():
            raise ValueError("Invalid Name")

        self.mqttConnection = None

        disallow_special(name)

        self.mqttSyncFeatures: Dict[str, Any] = mqttSyncFeatures or {}
        self.mqttNodeSessionID: str = base64.b64encode(os.urandom(8)).decode()

        self.eventButtons: list = eventButtons[:]
        self.infoDisplay = infoDisplay
        self.utility: bool = bool(utility)

        # This is used for the remote media triggers feature.
        self.mediaLink: kaithem.widget.APIWidget = kaithem.widget.APIWidget(
            "media_link")
        self.mediaLink.echo = False

        self.slideOverlayURL: str = slideOverlayURL

        # Audio visualizations
        self.musicVisualizations = musicVisualizations

        # The active media file being played through the remote playback mechanism.
        self.allowMediaUrlRemote = None

        def handleMediaLink(u, v):
            if v[0] == "initial":
                self.sendVisualizations()

            if v[0] == "ask":
                self.mediaLink.send(["volume", self.alpha])

                self.mediaLink.send(
                    [
                        "mediaURL",
                        self.allowMediaUrlRemote,
                        self.enteredCue,
                        max(0, self.cue.soundFadeIn or self.crossfade),
                    ]
                )
                self.mediaLink.send(
                    [
                        "slide",
                        self.cue.slide,
                        self.enteredCue,
                        max(0, self.cue.fadein or self.crossfade),
                    ]
                )
                self.mediaLink.send(["overlay", self.slideOverlayURL])

            if v[0] == "error":
                self.event(
                    "system.error",
                    "Web media playback error in remote browser: " + v[1],
                )

        self.mediaLink.attach(handleMediaLink)
        self.lock = threading.RLock()
        self.randomizeModifier = 0

        self.commandTagSubscriptions = []
        self.commandTag = commandTag

        self.displayTagSubscriptions = []
        self.displayTags = []
        self.displayTagValues = {}
        self.displayTagMeta = {}
        self.setDisplayTags(displayTags)

        self.notes = notes
        self.midiSource = ""
        self.defaultNext = str(defaultNext).strip()

        self.id: str = id or uuid.uuid4().hex

        # TagPoint for managing the current cue
        self.cueTag = kaithem.tags.StringTag(
            "/chandler/scenes/" + name + ".cue")
        self.cueTag.expose("users.chandler.admin", "users.chandler.admin")

        self.cueTagClaim = self.cueTag.claim(
            "__stopped__", "Scene", 50, annotation="SceneObject"
        )

        self.cueVolume = 1

        # Allow GotoCue
        def cueTagHandler(val, timestamp, annotation):
            # We generated this event, that means we don't have to respond to it
            if annotation == "SceneObject":
                return

            if val == "__stopped__":
                self.stop()
            else:
                # Just goto the cue
                self.gotoCue(val, cause="tagpoint")

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
        self.defaultalpha = alpha
        self.name = name

        # self.values = values or {}
        self.canvas = FadeCanvas()
        self.backtrack = backtrack
        self.bpm = bpm
        self.soundOutput = soundOutput

        self.cues = {}

        # The list of cues as an actual list that is maintained sorted by number
        self.cues_ordered: List[Cue] = []

        if cues:
            for j in cues:
                Cue(self, name=j, **cues[j])

        if 'default' not in self.cues:
            Cue(self, "default")
        self.cue = self.cues['default']

        # Used for the tap tempo algorithm
        self.lastTap = 0
        self.tapSequence = 0

        # This flag is used to avoid having to repaint the canvas if we don't need to
        self.fadeInCompleted = False
        # A pointer into that list pointing at the current cue. We have to update all this
        # every time we change the lists
        self.cuePointer = 0

        # Used for storing when the sound file ended. 0 indicates a sound file end event hasn't
        # happened since the cue started
        self.sound_end = 0

        self.cueTagClaim.set(self.cue.name, annotation="SceneObject")

        # Used to avoid an excessive number of repeats in random cues
        self.cueHistory = []

        # List of universes we should be affecting.
        # Based on what values are in the cue and what values are inherited
        self.affect = []

        # Lets us cache the lists of values as numpy arrays with 0 alpha for not present vals
        # which are faster that dicts for some operations
        self.cue_cached_vals_as_arrays: Dict[str, numpy.typing.NDArray[Any]] = {}
        self.cue_cached_alphas_as_arrays: Dict[str, numpy.typing.NDArray[Any]] = {}

        self.rerenderOnVarChange = False

        self.enteredCue = 0

        # Map event name to runtime as unix timestamp
        self.runningTimers = {}

        self.priority = priority
        # Used by blend modes
        self.blendArgs = blendArgs or {}
        self.setBlend(blend)
        self.defaultActive = defaultActive

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
        self.scriptContext = self.makeScriptContext()
        self.refreshRules()

        self.mqttServer = mqttServer
        self.activeMqttServer = None

        self.setMidiSource(midiSource)

        if active:
            self.gotoCue("default", sendSync=False, cause="start")
            self.go()
            if isinstance(active, float):
                self.started = time.time() - active

        else:
            self.cueTagClaim.set("__stopped__", annotation="SceneObject")

        self.subscribeCommandTags()

    def toDict(self):
        return {
            "bpm": self.bpm,
            "alpha": self.defaultalpha,
            "cues": {j: self.cues[j].serialize() for j in self.cues},
            "priority": self.priority,
            "active": self.defaultActive,
            "blend": self.blend,
            "blendArgs": self.blendArgs,
            "backtrack": self.backtrack,
            "mqttSyncFeatures": self.mqttSyncFeatures,
            "soundOutput": self.soundOutput,
            "slideOverlayURL": self.slideOverlayURL,
            "eventButtons": self.eventButtons,
            "infoDisplay": self.infoDisplay,
            "utility": self.utility,
            "displayTags": self.displayTags,
            "midiSource": self.midiSource,
            "musicVisualizations": self.musicVisualizations,
            "defaultNext": self.defaultNext,
            "commandTag": self.commandTag,
            "uuid": self.id,
            "notes": self.notes,
            "mqttServer": self.mqttServer,
            "crossfade": self.crossfade,
        }

    def __del__(self):
        pass

    def getStatusString(self):
        x = ""
        if self.mqttConnection:
            if not self.mqttConnection.is_connected:
                x += "MQTT Disconnected "
        return x

    def close(self):
        "Unregister the scene and delete it from the lists"
        with core.lock:
            self.stop()
            self.mqttServer = ''
            x = self.mqttConnection
            if x:
                x.disconnect()
            if scenes_by_name.get(self.name, None) is self:
                del scenes_by_name[self.name]

            if scenes.get(self.id, None) is self:
                del scenes[self.id]

    def evalExpr(self, s):
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
        if self.defaultNext.strip():
            return self.defaultNext.strip()
        try:
            return self.cues_ordered[self.cuePointer + 1].name
        except Exception:
            return None

    def getAfter(self, cue):
        x = self.cues[cue].next_ll
        return x.name if x else None

    def getParent(self, cue):
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
                if (not x.nextCue) or x.nextCue == cue:
                    return x.name
            return None

    def rmCue(self, cue):
        with core.lock:
            if not len(self.cues) > 1:
                raise RuntimeError("Cannot have scene with no cues")

            if cue in cues:
                if cues[cue].name == "default":
                    raise RuntimeError("Cannot delete the cue named default")

            if self.cue and self.name == cue:
                try:
                    self.gotoCue("default", cause="deletion")
                except Exception:
                    self.gotoCue(self.cues_ordered[0].name, cause="deletion")

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

            for i in core.boards:
                if len(i().newDataFunctions) < 100:
                    i().newDataFunctions.append(
                        lambda s: s.link.send(["delcue", id]))
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
        for i in core.boards:
            if len(i().newDataFunctions) < 100:
                i().newDataFunctions.append(lambda s: self.pushCueList(i.id))

    def _addCue(self, cue, prev=None, forceAdd=True):
        name = cue.name
        self.insertSorted(cue)
        if name in self.cues and not forceAdd:
            raise RuntimeError("Cue would overwrite existing.")
        self.cues[name] = cue
        if prev and prev in self.cues:
            self.cues[prev].nextCue = self.cues[name]

        for i in core.boards:
            if len(i().newDataFunctions) < 100:
                i().newDataFunctions.append(
                    lambda s: s.pushCueMeta(self.cues[name].id))
        for i in core.boards:
            if len(i().newDataFunctions) < 100:
                i().newDataFunctions.append(lambda s: s.pushCueData(cue.id))

    def pushMeta(self, cue: str | bool = False, statusOnly: bool = False, keys: None | Iterable[str] = None):
        # Push cue first so the client already has that data when we jump to the new display
        if cue and self.cue:
            for i in core.boards:
                if len(i().newDataFunctions) < 100:
                    i().newDataFunctions.append(lambda s: s.pushCueMeta(self.cue.id))

        for i in core.boards:
            if len(i().newDataFunctions) < 100:
                i().newDataFunctions.append(
                    lambda s: s.pushMeta(
                        self.id, statusOnly=statusOnly, keys=keys)
                )

    def event(self, s: str, value: str | float | int | bool | None = None, info=""):
        # No error loops allowed!
        if not s == "script.error":
            self._event(s, value, info)

    def _event(self, s: str, value: str | float | int | bool | None = None, info=""):
        "Manually trigger any script bindings on an event"
        try:
            if self.scriptContext:
                self.scriptContext.event(s, value)
        except Exception:
            core.rl_log_exc("Error handling event: " + str(s))
            print(traceback.format_exc(6))

    def pickRandomCueFromNames(self, cues):
        names = []
        weights = []

        for i in cues:
            i = i.strip()
            if i in self.cues:
                weights.append(self.evalExpr(
                    self.cues[i].probability.strip() or 1))
                names.append(i)

        return random.choices(names, weights=weights)[0]

    def _parseCueName(self, cue: str):
        if cue == "__shuffle__":
            x = [i.name for i in self.cues_ordered if not (
                i.name == self.cue.name)]
            for i in list(reversed(self.cueHistory[-15:])):
                if len(x) < 3:
                    break
                elif i[0] in x:
                    x.remove(i[0])
            cue = self.pickRandomCueFromNames(x)

        elif cue == "__random__":
            x = [i.name for i in self.cues_ordered if not i.name == self.cue.name]
            cue = self.pickRandomCueFromNames(x)

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
                cue = self.pickRandomCueFromNames(x)

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
                cue = cue = self.pickRandomCueFromNames(x)

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

    def gotoCue(self, cue: str, t: Optional[float] = None, sendSync=True, generateEvents=True, cause="generic"):
        "Goto cue by name, number, or string repr of number"
        # Globally raise an error if there's a big horde of cue transitions happening
        doTransitionRateLimit()

        if self.cue:
            oldSoundOut = self.cue.soundOutput
        else:
            oldSoundOut = None
        if not oldSoundOut:
            oldSoundOut = self.soundOutput

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
                gn = self.mqttSyncFeatures.get("syncGroup", False)
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
                self.sound_end = 0

                try:
                    # Take rules from new cue, don't actually set this as the cue we are in
                    # Until we succeed in running all the rules that happen as we enter
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
                        core.rl_log_exc("Error with cue variable " + i)

                if self.cues[cue].track:
                    self.applyTrackedValues(cue)

                self.mediaLink.send(
                    [
                        "slide",
                        self.cues[cue].slide,
                        self.enteredCue,
                        max(0, self.cues[cue].fadein or self.crossfade),
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
                        if self.cue.soundFadeOut or self.cue.mediaWinddown:
                            fadeSound(
                                None,
                                length=self.cue.soundFadeOut,
                                handle=str(self.id),
                                winddown=self.cue.mediaWinddown,
                            )
                        else:
                            stopSound(str(self.id))
                    # There is no next sound so crossfade to silence
                    if self.crossfade and (not self.cues[cue].sound):
                        if self.cue.soundFadeOut or self.cue.mediaWinddown:
                            fadeSound(
                                None,
                                length=self.cue.soundFadeOut,
                                handle=str(self.id),
                                winddown=self.cue.mediaWinddown,
                            )
                        else:
                            stopSound(str(self.id))

                    self.allowMediaUrlRemote = None

                    out = self.cues[cue].soundOutput
                    if not out:
                        out = self.soundOutput
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
                                    self.cues[cue].fadein or self.crossfade),
                            ]
                        )

                    if self.cues[cue].sound and self.active:
                        sound = self.cues[cue].sound
                        try:
                            self.cueVolume = min(
                                5,
                                max(
                                    0, float(self.evalExpr(
                                        self.cues[cue].soundVolume))
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
                            sound = self.resolveSound(sound)
                        except Exception:
                            print(traceback.format_exc())

                        if os.path.isfile(sound):
                            if not out == "scenewebplayer":
                                # Always fade in if the face in time set.
                                # Also fade in for crossfade, but in that case we only do it if there is something to fade in from.
                                if not (
                                    (
                                        (
                                            (self.crossfade > 0)
                                            and not (self.cues[cue].soundFadeIn < 0)
                                        )
                                        and kaithem.sound.isPlaying(str(self.id))
                                    )
                                    or (self.cues[cue].soundFadeIn > 0)
                                    or self.cues[cue].mediaWindup
                                    or self.cue.mediaWinddown
                                ):
                                    spd = self.scriptContext.preprocessArgument(
                                        self.cues[cue].mediaSpeed
                                    )
                                    playSound(
                                        sound,
                                        handle=str(self.id),
                                        volume=self.alpha * self.cueVolume,
                                        output=out,
                                        loop=self.cues[cue].soundLoops,
                                        start=self.cues[cue].soundStartPosition,
                                        speed=spd,
                                    )
                                else:
                                    fade = self.cues[cue].soundFadeIn or self.crossfade
                                    fadeSound(
                                        sound,
                                        length=max(fade, 0.1),
                                        handle=str(self.id),
                                        volume=self.alpha * self.cueVolume,
                                        output=out,
                                        loop=self.cues[cue].soundLoops,
                                        start=self.cues[cue].soundStartPosition,
                                        windup=self.cues[cue].mediaWindup,
                                        winddown=self.cue.mediaWinddown,
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
                                            self.cues[cue].fadein or self.crossfade),
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
                                # Not support, but it might just be an unsupported type. if mp3, its a real error, we should alert
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
                sc = self.cues[cue].triggerShortcut.strip()
                if sc:
                    shortcutCode(sc, exclude=self)
                self.cue = self.cues[cue]
                self.cueTagClaim.set(
                    self.cues[cue].name, annotation="SceneObject")

                self.recalcRandomizeModifier()
                self.recalcCueLen()

                # Recalc what universes are affected by this scene.
                # We don't clear the old universes, we do that when we're done fading in.
                for i in self.cues[cue].values:
                    i = mapUniverse(i)
                    if i and i in universes.universes:
                        if i not in self.affect:
                            self.affect.append(i)

                self.cueValsToNumpyCache(self.cue, not self.cue.track)
                self.fadeInCompleted = False

                # We don't render here. Very short cues coupt create loops of rerendering and goto
                # self.render(force_repaint=True)

                # Instead we set the flag
                self.rerender = True
                self.pushMeta(statusOnly=True)

                self.preloadNextCueSound()

    def applyTrackedValues(self, cue):
        # When jumping to a cue that isn't directly the next one, apply and "parent" cues.
        # We go backwards until we find a cue that has no parent. A cue has a parent if and only if it has either
        # an explicit parent or the previous cue in the numbered list either has the default next cue or explicitly
        # references this cue.
        cobj = self.cues[cue]

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
                self.cueValsToNumpyCache(cuex)

    def preloadNextCueSound(self):
        # Preload the next cue's sound if we know what it is
        nextCue = None
        if self.cue:
            if self.cue.nextCue == "":
                nextCue = self.getDefaultNext()
            elif self.cue.nextCue in self.cues:
                nextCue = self.cue.nextCue

        if nextCue and nextCue in self.cues:
            c = self.cues[nextCue]
            sound = c.sound
            try:
                sound = self.resolveSound(sound)
            except Exception:
                return
            if os.path.isfile(sound):
                out = c.soundOutput
                if not out:
                    out = self.soundOutput
                if not out:
                    out = "@auto"

                try:
                    kaithem.sound.preload(sound, out)
                except Exception:
                    print(traceback.format_exc())

    def resolveSound(self, sound):
        return core.resolveSound(sound)

    def recalcRandomizeModifier(self):
        "Recalculate the random variance to apply to the length"
        if self.cue:
            self.randomizeModifier = random.triangular(
                -float(self.cue.lengthRandomize), +
                float(self.cue.lengthRandomize)
            )

    def recalcCueLen(self):
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
            # But in this case we want the next one.  We don't want exclusive matching all the either as that seems a bit buggy.
            if nextruntime <= ref:
                nextruntime = selector.after(nextruntime, False)

            t2 = dt_to_ts(nextruntime, selector.tz)

            nextruntime = t2

            v = nextruntime - time.time()

        else:
            if self.cue.sound and self.cue.rel_length:
                path = self.resolveSound(self.cue.sound)
                if (
                    path.endswith(".png")
                    or path.endswith(".jpg")
                    or path.endswith(".webp")
                    or path.endswith(".png")
                    or path.endswith(".heif")
                    or path.endswith(".tiff")
                    or path.endswith(".gif")
                    or path.endswith(".svg")
                ):
                    v = 0
                else:
                    try:
                        # If we are doing crossfading, we have to stop slightly early for
                        # The crossfade to work
                        # TODO this should not stop early if the next cue overrides
                        duration = TinyTag.get(path).duration
                        if duration is not None:
                            slen = (duration -
                                    self.crossfade) + cuelen
                            v = max(0, self.randomizeModifier + slen)
                        else:
                            raise RuntimeError(
                                "Tinytag returned None when getting length")
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

    def recalcCueVals(self):
        self.cueValsToNumpyCache(self.cue, not self.cue.track)

    def cueValsToNumpyCache(self, cuex, clearBefore=False):
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
                repeats = int(cuex.values[i]["__length__"])
            else:
                repeats = 1

            if "__spacing__" in cuex.values[i]:
                chCount = int(cuex.values[i]["__spacing__"])

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

    def makeScriptContext(self):

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

    def refreshRules(self, rulesFrom=None):
        with core.lock:
            # We copy over the event recursion depth so that we can detct infinite loops
            if not self.scriptContext:
                self.scriptContext = self.makeScriptContext()

            self.scriptContext.clearBindings()

            self.scriptContext.setVar("SCENE", self.name)
            self.runningTimers = {}

            if self.active:
                self.scriptContext.setVar("CUE", (rulesFrom or self.cue).name)

                # Actually add the bindings
                self.scriptContext.addBindings((rulesFrom or self.cue).rules)

                loopPrevent = {(rulesFrom or self.cue.name): True}

                x = (rulesFrom or self.cue).inheritRules
                while x and x.strip():
                    # Avoid infinite loop should the user define a cycle of cue inheritance
                    if x.strip() in loopPrevent:
                        break
                    loopPrevent[x.strip()] = True

                    self.scriptContext.addBindings(self.cues[x].rules)
                    x = self.cues[x].inheritRules

                self.scriptContext.startTimers()
                self.doMqttSubscriptions()

            try:
                for i in core.boards:
                    i().link.send(["scenetimers", self.id, self.runningTimers])
            except Exception:
                core.rl_log_exc("Error handling timer set notification")

    def onMqttMessage(self, topic: str, message: bytes):
        try:
            self.event("$mqtt:" + topic, json.loads(message.decode("utf-8")))
        except Exception:
            self.event("$mqtt:" + topic, message)

    def onCueSyncMessage(self, topic: str, message: str):
        gn = self.mqttSyncFeatures.get("syncGroup", False)
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
                    self.gotoCue(m['cue'], t=max(min(time.time(
                    ) + 0.5, m['time']), time.time() - 0.5), sendSync=False, cause="MQTT Sync")

    def doMqttSubscriptions(self, keepUnused=120):
        if self.mqttConnection:
            if self.mqttSyncFeatures.get("syncGroup", False):
                self.mqttConnection.subscribe(
                    f"/kaithem/chandler/syncgroup/{self.mqttSyncFeatures.get('syncGroup',False)}"
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

    def displayTagSubscriber(self, n):
        t = n[1]
        if not self.scriptContext.canGetTagpoint(t):
            raise ValueError("Not allowed tag " + t)

        t = kaithem.tags[n[1]]
        sn = n[1]
        self.displayTagMeta[sn] = {}
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
            try:
                for i in dt:
                    self.displayTagSubscriptions.append(
                        self.displayTagSubscriber(i))
            except Exception:
                print(traceback.format_exc())
            self.displayTags = dt

    def clearConfiguredTags(self):
        with core.lock:
            for i in self.commandTagSubscriptions:
                i[0].unsubscribe(i[1])
            self.commandTagSubscriptions = []

    def commandTagSubscriber(self):
        sn = self.name

        def f(v, t, a):
            v = v[0]

            if v.startswith("launch:"):
                shortcutCode(str(v[len("launch:"):]), sn)

            elif v == "Rev":
                self.prevCue(cause="ECP")

            elif v == "Fwd":
                self.nextCue(cause="ECP")

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
                self.event("button." + v[4:])

        return f

    def subscribeCommandTags(self):
        if not self.commandTag.strip():
            return
        with core.lock:
            for i in [self.commandTag]:
                t = kaithem.tags.ObjectTag(i)
                s = self.commandTagSubscriber()
                self.commandTagSubscriptions.append([t, s])
                t.subscribe(s)

    def setCommandTag(self, st):
        st = st.strip()

        self.clearConfiguredTags()

        self.commandTag = st

        if st:
            st = kaithem.tags.ObjectTag(st)
            if st.subtype and not st.subtype == "event":
                raise ValueError("That tag does not have the event subtype")

            self.subscribeCommandTags()

    def nextCue(self, t=None, cause="generic"):

        cue = self.cue
        if not cue:
            return

        with core.lock:
            if cue.nextCue and (
                (self.evalExpr(cue.nextCue).split("?")[0] in self.cues)
                or cue.nextCue.startswith("__")
                or "|" in cue.nextCue
                or "*" in cue.nextCue
            ):
                self.gotoCue(cue.nextCue, t, cause=cause)
            elif not cue.nextCue:
                x = self.getDefaultNext()
                if x:
                    self.gotoCue(x, t)

    def prevCue(self, cause="generic"):
        with core.lock:
            if len(self.cueHistory) > 1:
                c = self.cueHistory[-2]
                c = c[0]
                self.gotoCue(c, cause)

    def setupBlendArgs(self):
        if hasattr(self.blendClass, "parameters"):
            for i in self.blendClass.parameters:
                if i not in self.blendArgs:
                    self.blendArgs[i] = self.blendClass.parameters[i][3]

    def go(self, nohandoff=False):
        global activeScenes, _activeScenes
        self.setDisplayTags(self.displayTags)

        with core.lock:
            if self in activeScenes:
                return

            # Not sure if we need to remake this, keep it for defensive
            # reasons, TODO
            self.canvas = FadeCanvas()

            self.manualAlpha = False
            self.active = True

            if not self.cue:
                self.gotoCue("default", sendSync=False, cause="start")
            else:
                # Re-enter cue to create the cache
                self.gotoCue(self.cue.name, cause="start")
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

            if self not in _activeScenes:
                _activeScenes.append(self)
            _activeScenes = sorted(
                _activeScenes, key=lambda k: (k.priority, k.started)
            )
            activeScenes = _activeScenes[:]

            self.setMqttServer(self.mqttServer)

            # Minor inefficiency rendering twice the first frame
            self.rerender = True
            # self.render()

    def isActive(self):
        return self.active

    def setPriority(self, p):
        global activeScenes, _activeScenes
        self.hasNewInfo = {}
        self.priority = p
        with core.lock:
            _activeScenes = sorted(
                _activeScenes, key=lambda k: (k.priority, k.started)
            )
            activeScenes = _activeScenes[:]
            try:
                for i in self.affect:
                    rerenderUniverse(i)
            except Exception:
                print(traceback.format_exc())

    def mqttStatusEvent(self, value, timestamp, annotation):
        if value == "connected":
            self.event("board.mqtt.connect")
        else:
            self.event("board.mqtt.disconnect")

        self.pushMeta(statusOnly=True)

    @typechecked
    def setMqttServer(self, mqttServer: str):
        with self.lock:
            x = mqttServer.strip().split(":")
            server = x[0]
            if len(x) > 1:
                port = int(x[-1])
                server = x[-2]
            else:
                port = 1883

            if mqttServer == self.activeMqttServer:
                return

            self.unusedMqttTopics = {}

            if self.mqttConnection:
                self.mqttConnection.disconnect()
                self.mqttConnection = None

            if mqttServer:
                if self in activeScenes:

                    self.mqttConnection = makeWrappedConnectionClass(self)(
                        server,
                        port,
                    )

                    self.mqttSubscribed = {}

            else:
                self.mqttConnection = None
                self.mqttSubscribed = {}

            # Do after so we can get the err on bad format first
            self.mqttServer = self.activeMqttServer = mqttServer

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

    def setMQTTFeature(self, feature, state):
        if state:
            self.mqttSyncFeatures[feature] = state
        else:
            self.mqttSyncFeatures.pop(feature, None)
        self.hasNewInfo = {}
        self.doMqttSubscriptions()

    def setBacktrack(self, b):
        b = bool(b)
        if self.backtrack == b:
            return
        else:
            self.backtrack = b
            x = self.enteredCue
            self.gotoCue(self.cue.name)
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

    def tap(self, t=None):
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
        global activeScenes, _activeScenes
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
            if self in _activeScenes:
                _activeScenes.remove(self)
                activeScenes = _activeScenes[:]

            self.active = False
            self.cue_cached_vals_as_arrays = {}
            self.cue_cached_alphas_as_arrays = {}
            kaithem.sound.stop(str(self.id))

            self.runningTimers.clear()

            try:
                for i in core.boards:
                    i().link.send(["scenetimers", self.id, self.runningTimers])
            except Exception:
                core.rl_log_exc("Error handling timer set notification")
                print(traceback.format_exc())
            # fALLBACK
            self.cue = self.cues.get('default', list(self.cues.values())[0])
            self.cueTagClaim.set("__stopped__", annotation="SceneObject")
            self.doMqttSubscriptions(keepUnused=0)

    def noteOn(self, ch, note, vel):
        self.event("midi.note:" + str(ch) + "." + number_to_note(note), vel)

    def noteOff(self, ch, note):
        self.event("midi.noteoff:" + str(ch) + "." + number_to_note(note), 0)

    def cc(self, ch, n, v):
        self.event("midi.cc:" + str(ch) + "." + str(n), v)

    def setMidiSource(self, s):
        if s == self.midiSource:
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

        self.midiSource = s

    def onMidiMessage(self, t, v):
        if v[0] == "noteon":
            self.noteOn(v[1], v[2], v[3])
        if v[0] == "noteoff":
            self.noteOff(v[1], v[2])
        if v[0] == "cc":
            self.cc(v[1], v[2], v[3])

    def setMusicVisualizations(self, s):
        if s == self.musicVisualizations:
            return

        s2 = ""
        for i in s.split("\n"):
            if i.strip():
                s2 += i.strip() + "\n"

        self.musicVisualizations = s2
        self.sendVisualizations()
        self.pushMeta(keys={"musicVisualizations"})

    def sendVisualizations(self):
        self.mediaLink.send(
            [
                "butterchurnfiles",
                [
                    i.split("milkdrop:")[-1]
                    for i in self.musicVisualizations.split("\n")
                    if i
                ],
            ]
        )

    def setAlpha(self, val, sd=False):
        val = min(1, max(0, val))
        try:
            self.cueVolume = min(
                5, max(0, float(self.evalExpr(self.cue.soundVolume))))
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
            self.defaultalpha = val
            self.pushMeta(keys={"alpha", "dalpha"})
        else:
            self.pushMeta(keys={"alpha", "dalpha"})
        self.rerender = True

        self.mediaLink.send(["volume", val])

    def addCue(self, name, **kw):
        return Cue(self, name, **kw)

    def setBlend(self, blend):
        disallow_special(blend)
        blend = str(blend)[:256]
        self.blend = blend
        if blend in blendmodes.blendmodes:
            if self.isActive():
                self._blend = blendmodes.blendmodes[blend](self)
            self.blendClass = blendmodes.blendmodes[blend]
            self.setupBlendArgs()
        else:
            self.blendArgs = self.blendArgs or {}
            self._blend = blendmodes.HardcodedBlendMode(self)
            self.blendClass = blendmodes.HardcodedBlendMode
        self.rerender = True
        self.hasNewInfo = {}

    def setBlendArg(self, key, val):
        disallow_special(key, "_")
        # serializableness check
        json.dumps(val)
        if (
            not hasattr(self.blendClass, "parameters")
            or key not in self.blendClass.parameters
        ):
            raise KeyError("No such param")

        if val is None:
            del self.blendArgs[key]
        else:
            if self.blendClass.parameters[key][1] == "number":
                val = float(val)
            self.blendArgs[key] = val
        self.rerender = True
        self.hasNewInfo = {}

    def render(self, force_repaint=False):
        "Calculate the current alpha value, handle stopping the scene and spawning the next one"
        if self.cue.fadein:
            fadePosition = min(
                (time.time() - self.enteredCue) /
                (self.cue.fadein * (60 / self.bpm)), 1
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
        if force_repaint or (not self.fadeInCompleted):
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
                self.fadeInCompleted = True
                self.rerender = True

        if self.cuelen and (time.time() - self.enteredCue) > self.cuelen * (
            60 / self.bpm
        ):
            # rel_length cues end after the sound in a totally different part of code
            # Calculate the "real" time we entered, which is exactly the previous entry time plus the len.
            # Then round to the nearest millisecond to prevent long term drift due to floating point issues.
            self.nextCue(
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
