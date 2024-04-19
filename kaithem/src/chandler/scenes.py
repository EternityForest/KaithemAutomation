from __future__ import annotations

import base64
import collections
import datetime
import gc
import json
import logging
import os
import random
import threading
import time
import traceback
import urllib.parse
import uuid
import weakref
from collections.abc import Callable, Iterable
from typing import Any

import numpy
import numpy.typing
from beartype import beartype
from tinytag import TinyTag

from .. import schemas, tagpoints, util, widgets
from ..kaithemobj import kaithem
from . import blendmodes, core, mqtt, persistance, universes
from .core import disallow_special
from .cue import Cue, allowedCueNameSpecials, cues, fnToCueName, normalize_shortcut, shortcut_codes
from .fadecanvas import FadeCanvas
from .mathutils import dt_to_ts, ease, number_to_note
from .soundmanager import fadeSound, play_sound, stop_sound
from .universes import getUniverse, mapChannel, mapUniverse, rerenderUniverse

# Locals for performance... Is this still a thing??
float = float
abs = abs
int = int
max = max
min = min


scenes: weakref.WeakValueDictionary[str, Scene] = weakref.WeakValueDictionary()
scenes_by_name: weakref.WeakValueDictionary[str, Scene] = weakref.WeakValueDictionary()

_active_scenes: list[Scene] = []
active_scenes: list[Scene] = []


def is_static_media(s: str):
    "True if it's definitely media that does not have a length"
    for i in (".bmp", ".jpg", ".html", ".webp", ".php"):
        if s.startswith(i):
            return True

    # Try to detect http stuff
    if "." not in s.split("?")[0].split("#")[0].split("/")[-1]:
        if not os.path.exists(s):
            return True

    return False


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


rootContext = kaithem.chandlerscript.ChandlerScriptContext()


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
            raise RuntimeError("More than 3 layers of redirects in cue.enter or cue.exit")

    # We don't want to handle other bindings after a goto, leaving a scene stops execution.
    scenes_by_name[scene].script_context.stopAfterThisHandler()
    scenes_by_name[scene].goto_cue(cue, cause=newcause)
    return True


gotoCommand.completionTags = {  # type: ignore
    "scene": "gotoSceneNamesCompleter",
    "cue": "gotoSceneCuesCompleter",
}


def setAlphaCommand(scene: str = "=SCENE", alpha: float = 1):
    "Set the alpha value of a scene"
    scenes_by_name[scene].setAlpha(float(alpha))
    return True


def ifCueCommand(scene: str, cue: str):
    "True if the scene is running that cue"
    return True if scenes_by_name[scene].active and scenes_by_name[scene].cue.name == cue else None


def eventCommand(scene: str = "=SCENE", ev: str = "DummyEvent", value: str = ""):
    "Send an event to a scene, or to all scenes if scene is __global__"
    if scene == "__global__":
        event(ev, value)
    else:
        scenes_by_name[scene].event(ev, value)
    return True


def setWebVarCommand(scene: str = "=SCENE", key: str = "varFoo", value: str = ""):
    "Set a slideshow variable. These can be used in the slideshow text as {{var_name}}"
    if not key.startswith("var"):
        raise ValueError("Custom slideshow variable names for slideshow must start with 'var' ")
    scenes_by_name[scene].set_slideshow_variable(key, value)
    return True


def uiNotificationCommand(text: str):
    "Send a notification to the operator, on the web editor and console pages"
    for board in core.iter_boards():
        if len(board.newDataFunctions) < 100:
            board.newDataFunctions.append(lambda s: s.linkSend(["ui_alert", text]))


rootContext.commands["shortcut"] = codeCommand
rootContext.commands["goto"] = gotoCommand
rootContext.commands["set_alpha"] = setAlphaCommand
rootContext.commands["if_cue"] = ifCueCommand
rootContext.commands["send_event"] = eventCommand
rootContext.commands["set_slideshow_variable"] = setWebVarCommand
rootContext.commands["console_notification"] = uiNotificationCommand

rootContext.commands["set_tag"].completionTags = {"tagName": "tagPointsCompleter"}


def sendMqttMessage(topic: str, message: str):
    "JSON encodes message, and publishes it to the scene's MQTT server"
    raise RuntimeError("This was supposed to be overridden by a scene specific version")


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
        raise RuntimeError("Too many cue transitions extremely fast.  You may have a problem somewhere.")
    cueTransitionsLimitCount += 2


def shortcutCode(code: str, limitScene: Scene | None = None, exclude: Scene | None = None):
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
                        if x is not exclude:
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
                    board.linkSend(["scenetimers", scene.id, scene.runningTimers])
            except Exception:
                core.rl_log_exc("Error handling timer set notification")
                print(traceback.format_exc())

    def canGetTagpoint(self, t):
        if t not in self.tagpoints and len(self.tagpoints) > 128:
            raise RuntimeError("Too many tagpoints in one scene")
        return t


def checkPermissionsForSceneData(data: dict[str, Any], user: str):
    """Check if used can upload or edit the scene, ekse raise an
      error if
        it uses advanced features that would prevent that action.
    We disallow delete because we don't want unprivelaged users
    to delete something important that they can't fix.

    """
    if "mqtt_server" in data and data["mqtt_server"].strip():
        if not kaithem.users.check_permission(user, "system_admin"):
            raise ValueError(
                "You cannot do this action on this scene without system_admin, because it uses advanced features: MQTT:"
                + str(kaithem.web.user())
            )


scene_schema = schemas.get_schema("chandler/scene")


class Scene:
    "An objecting representing one scene. If noe default cue present one is made"

    def __init__(
        self,
        name: str,
        cues: dict[str, dict[str, Any]] | None = None,
        active: bool = False,
        alpha: float = 1,
        priority: float = 50,
        blend: str = "normal",
        id: str | None = None,
        default_active: bool = True,
        blend_args: dict[str, Any] | None = None,
        backtrack: bool = True,
        bpm: float = 60,
        sound_output: str = "",
        event_buttons: list[Iterable[str]] = [],
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
        mqtt_sync_features: dict[str, Any] | None = None,
        **ignoredParams,
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
        self.web_variables: dict[str, Any] = {}

        self.mqttConnection = None
        self.mqttSubscribed: dict[str, bool]

        self.on_demand_universes: dict[str, universes.Universe] = {}

        disallow_special(name)

        self.mqtt_sync_features: dict[str, Any] = mqtt_sync_features or {}
        self.mqttNodeSessionID: str = base64.b64encode(os.urandom(8)).decode()

        self.event_buttons: list = event_buttons[:]
        self.info_display = info_display
        self.utility: bool = bool(utility)

        self.id: str = id or uuid.uuid4().hex

        class APIWidget(widgets.APIWidget):
            # Ignore badly named s param because it need to not conflic with outer self
            def on_new_subscriber(s, user, cid, **kw):  # type: ignore
                self.send_all_media_link_info()

        # This is used for the remote media triggers feature.
        # We must explicitly give it an ID so that it stays consistent
        # between runs and we can auto-reconnect
        self.media_link_socket = APIWidget(id=self.id + "_media_link")
        self.media_link_socket.echo = False

        self.slide_overlay_url: str = slide_overlay_url

        # Kind of long so we do it in the external file
        self.slideshow_layout: str = slideshow_layout.strip() or scene_schema["properties"]["slideshow_layout"]["default"]

        # Audio visualizations
        self.music_visualizations = music_visualizations

        # The active media file being played through the remote playback mechanism.
        self.allowed_remote_media_url = None

        self.hide = hide

        self.slideshow_telemetry: collections.OrderedDict[str, dict[str, Any]] = collections.OrderedDict()

        self.slideshow_telemetry_ratelimit = (time.monotonic(), 200)

        def handleMediaLink(u, v, id):
            if v[0] == "telemetry":
                ts, remain = self.slideshow_telemetry_ratelimit
                remain = max(0, min(200, (time.monotonic() - ts) * 3 + remain - 1))

                if remain:
                    ip = kaithem.widget.ws_connections[id].peer_address
                    n = ip + "@" + self.name

                    if v[1]["status"] == "disconnect":
                        self.slideshow_telemetry.pop(n, None)
                        for board in core.iter_boards():
                            board.linkSend(["slideshow_telemetry", n, None])
                        return

                    self.slideshow_telemetry[n] = {
                        "status": str(v[1]["status"])[:128],
                        "name": str(v[1].get("name", ""))[:128],
                        "ip": ip,
                        "id": id,
                        "ts": time.time(),
                        "battery": kaithem.widget.ws_connections[id].batteryStatus,
                        "scene": self.name,
                    }
                    self.slideshow_telemetry.move_to_end(n)

                    if len(self.slideshow_telemetry) > 256:
                        k, x = self.slideshow_telemetry.popitem(False)
                        for board in core.iter_boards():
                            board.linkSend(["slideshow_telemetry", k, None])

                    try:
                        for board in core.iter_boards():
                            board.linkSend(["slideshow_telemetry", n, self.slideshow_telemetry[n]])
                    except Exception:
                        pass

            elif v[0] == "initial":
                self.sendVisualizations()

            elif v[0] == "ask":
                self.send_all_media_link_info()

            elif v[0] == "error":
                self.event(
                    "system.error",
                    "Web media playback error in remote browser: " + v[1],
                )

        self.media_link_socket.attach2(handleMediaLink)
        self.lock = threading.RLock()
        self.randomizeModifier = 0

        self.command_tagSubscriptions: list[tuple[tagpoints.ObjectTagPointClass, Callable]] = []
        self.command_tag = command_tag

        self.notes = notes
        self._midi_source: str = ""
        self.default_next = str(default_next).strip()

        # TagPoint for managing the current cue
        self.cueTag = kaithem.tags.StringTag("/chandler/scenes/" + name + ".cue")
        self.cueTag.expose("view_status", "chandler_operator")

        self.cueTagClaim = self.cueTag.claim("__stopped__", "Scene", 50, annotation="SceneObject")

        self.cueVolume = 1.0

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
        self.cueInfoTag = kaithem.tags.ObjectTag("/chandler/scenes/" + name + ".cueInfo")
        self.cueInfoTag.value = {"audio.meta": {}}
        self.cueInfoTag.expose("view_status", "chandler_operator")

        self.albumArtTag = kaithem.tags.StringTag("/chandler/scenes/" + name + ".albumArt")
        self.albumArtTag.expose("view_status")

        # Used to determine the numbering of added cues
        self.topCueNumber = 0
        # Only used for monitor scenes

        # If an entry here it means the monitor scene with that ID
        # already sent data to web
        self.monitor_values_already_pushed_by: dict[str, bool] = {}
        # Place to stash a blend object for new blending mode
        # Hardcoded indicates that applyLayer reads the blend name and we
        # have hardcoded logic there
        self._blend: blendmodes.BlendMode = blendmodes.HardcodedBlendMode(self)
        self.blendClass: type[blendmodes.BlendMode] = blendmodes.HardcodedBlendMode
        self.alpha = alpha
        self.crossfade = crossfade

        self.cuelen = 0.0

        # TagPoint for managing the current alpha
        self.alphaTag = kaithem.tags["/chandler/scenes/" + name + ".alpha"]
        self.alphaTag.min = 0
        self.alphaTag.max = 1
        self.alphaTag.expose("view_status", "chandler_operator")

        self.alphaTagClaim = self.alphaTag.claim(self.alpha, "Scene", 50, annotation="SceneObject")

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

        self.cues: dict[str, Cue] = {}

        # The list of cues as an actual list that is maintained sorted by number
        self.cues_ordered: list[Cue] = []

        if cues:
            for j in cues:
                Cue(self, name=j, **cues[j])

        if "default" not in self.cues:
            Cue(self, "default")

        self.cue: Cue = self.cues["default"]

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
        self.cueHistory: list[tuple[str, float]] = []

        # List of universes we should be affecting right now
        # Based on what values are in the cue and what values are inherited
        self.affect: list[str] = []

        # Lets us cache the lists of values as numpy arrays with 0 alpha for not present vals
        # which are faster that dicts for some operations
        self.cue_cached_vals_as_arrays: dict[str, numpy.typing.NDArray[Any]] = {}
        self.cue_cached_alphas_as_arrays: dict[str, numpy.typing.NDArray[Any]] = {}

        self.rerenderOnVarChange = False

        self.entered_cue: float = 0

        # Map event name to runtime as unix timestamp
        self.runningTimers: dict[str, float] = {}

        self._priority = priority

        # Used by blend modes
        self.blend_args: dict[str, float | int | bool | str] = blend_args or {}
        self.setBlend(blend)
        self.default_active = default_active

        # Used to indicate that the most recent frame has changed something about the scene
        # Metadata that GUI clients need to know about.

        # An entry here means the board with that ID is all good
        # Clear this to indicate everything needs to be sent to web.
        self.metadata_already_pushed_by: dict[str, bool] = {}

        # Set to true every time the alpha value changes or a scene value changes
        # set to false at end of rendering
        self.rerender = False

        # Last time the scene was started. Not reset when stopped
        self.started = 0.0

        # Script engine variable space
        self.chandler_vars: dict[str, Any] = {}

        if name:
            scenes_by_name[self.name] = self
        if not name:
            name = self.id
        scenes[self.id] = self

        # The bindings for script commands that might be in the cue metadata
        # Used to be made on demand, now we just always have it
        self.script_context = self.make_script_context()

        # Holds (tagpoint, subscribe function) tuples whenever we subscribe
        # to a tag to display it
        self.display_tag_subscription_refs: list[tuple[tagpoints.GenericTagPointClass, Callable]] = []

        # Name, TagpointName, properties
        # This is the actual configured data.
        self.display_tags: list[tuple[str, str, dict[str, Any]]] = []

        # The most recent values of our display tags
        self.display_tag_values: dict[str, Any] = {}

        self.display_tag_meta: dict[str, dict[str, Any]] = {}
        self.set_display_tags(display_tags)

        self.refresh_ules()

        self.mqtt_server = mqtt_server
        self.activeMqttServer = None

        self._midi_source = ""

        self.midi_source = midi_source

        if active:
            self.goto_cue("default", sendSync=False, cause="start")
            self.go()
            if isinstance(active, (int, float)):
                self.started = time.time() - active

        else:
            self.cueTagClaim.set("__stopped__", annotation="SceneObject")

        self.subscribe_command_tags()

    def send_all_media_link_info(self):
        self.media_link_socket.send(["volume", self.alpha])

        self.media_link_socket.send(["text", self.cue.markdown])

        self.media_link_socket.send(["cue_ends", self.cuelen + self.entered_cue, self.cuelen])

        self.media_link_socket.send(["all_variables", self.web_variables])

        self.media_link_socket.send(
            [
                "mediaURL",
                self.allowed_remote_media_url,
                self.entered_cue,
                max(0, self.cue.fade_in or self.cue.sound_fade_in or self.crossfade),
            ]
        )
        self.media_link_socket.send(
            [
                "slide",
                self.cue.slide,
                self.entered_cue,
                max(0, self.cue.fade_in or self.crossfade),
            ]
        )
        self.media_link_socket.send(["overlay", self.slide_overlay_url])

    def toDict(self) -> dict[str, Any]:
        # These are the properties that aren't just straight 1 to 1 copies
        # of props, but still get saved
        d = {
            "alpha": self.default_alpha,
            "cues": {j: self.cues[j].serialize() for j in self.cues},
            "active": self.default_active,
            "uuid": self.id,
        }

        for i in scene_schema["properties"]:
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
        self.media_link_socket.send(["web_var", k, v])

        self.web_variables[k] = v

    def close(self):
        "Unregister the scene and delete it from the lists"
        with core.lock:
            self.stop()
            self.mqtt_server = ""
            x = self.mqttConnection
            if x:
                x.disconnect()
            if scenes_by_name.get(self.name, None) is self:
                del scenes_by_name[self.name]

            if scenes.get(self.id, None) is self:
                del scenes[self.id]

    def evalExprFloat(self, s: str | int | float) -> float:
        f = self.evalExpr(s)
        assert isinstance(f, (int, float))
        return f

    def evalExpr(self, s: str | int | float | bool | None):
        """Given A string, return a number if it looks like one, evaluate the expression if it starts with =, otherwise
        return the input.

        Given a number, return it.

        Basically, implements something like the logic from a spreadsheet app.
        """
        return self.script_context.preprocessArgument(s)

    def insertSorted(self, c):
        "Insert a None to just recalt the whole ordering"
        with core.lock:
            if c:
                self.cues_ordered.append(c)

            self.cues_ordered.sort(key=lambda i: i.number)

            # We inset cues before we actually have a selected cue.
            if hasattr(self, "cue") and self.cue:
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

    def getParent(self, cue: str) -> str | None:
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
                    board.newDataFunctions.append(lambda s: s.linkSend(["delcue", id]))
            try:
                self.cuePointer = self.cues_ordered.index(self.cue)
            except Exception:
                print(traceback.format_exc())
        # Regenerate linked list by brute force when a new cue is added.
        for i in range(len(self.cues_ordered) - 1):
            self.cues_ordered[i].next_ll = self.cues_ordered[i + 1]
        self.cues_ordered[-1].next_ll = None

    def _add_cue(self, cue: Cue, forceAdd=True):
        name = cue.name
        self.insertSorted(cue)
        if name in self.cues and not forceAdd:
            raise RuntimeError("Cue would overwrite existing.")
        self.cues[name] = cue

        core.add_data_pusher_to_all_boards(lambda s: s.pushCueMeta(self.cues[name].id))
        core.add_data_pusher_to_all_boards(lambda s: s.pushCueData(cue.id))

    def pushMeta(
        self,
        cue: str | bool = False,
        statusOnly: bool = False,
        keys: None | Iterable[str] = None,
    ):
        # Push cue first so the client already has that data when we jump to the new display
        if cue and self.cue:
            core.add_data_pusher_to_all_boards(lambda s: s.pushCueMeta(self.cue.id))

        core.add_data_pusher_to_all_boards(lambda s: s.pushMeta(self.id, statusOnly=statusOnly, keys=keys))

    def event(self, s: str, value: Any = True, info: str = "", exclude_errors: bool = True):
        # No error loops allowed!
        if (not s == "script.error") and exclude_errors:
            self._event(s, value, info)

    def _event(self, s: str, value: Any, info: str = ""):
        "Manually trigger any script bindings on an event"
        try:
            if self.script_context:
                self.script_context.event(s, value)
        except Exception:
            core.rl_log_exc("Error handling event: " + str(s))
            print(traceback.format_exc(6))

    def pick_random_cue_from_names(self, cues: list[str] | set[str] | dict[str, Any]) -> str:
        """
        Picks a random cue from a list of cue names.

        Args:
            cues (List[str] | Set[str] | Dict[str, Any]): A list, set, or dictionary of cue names.

        Returns:
            str: The randomly selected cue name.

        Raises:
            IndexError: If the input list of cues is empty.

        Notes:
            - Special cues that start with '__' are excluded from the selection.
            - The probability of each cue is taken into account when selecting.
            - If a cue does not have a probability specified, it defaults to 1.
            - The input `cues` can be a list, set, or dictionary.

        Example:
            >>> pick_random_cue_from_names(['c1', 'c2', 'c3'])
            'c2'
        """
        names: list[str] = []
        weights: list[float] = []

        for i in cues:
            i = i.strip()
            # Exclude special cues
            if i.startswith("__"):
                continue
            if i in self.cues:
                weights.append(self.evalExprFloat(str(self.cues[i].probability).strip() or 1))
                names.append(i)

        return random.choices(names, weights=weights)[0]

    def _parseCueName(self, cue_name: str) -> tuple[str, float | int]:
        """
        Take a raw cue name and find an actual matching cue. Handles things like shuffle
        Returns a tuple of cuename, entered_time because some special cues are things
        like stored checkpoints which may have an old entered_time.
        """
        if cue_name == "__shuffle__":
            x = [i.name for i in self.cues_ordered if not (i.name == self.cue.name)]

            for history_item in list(reversed(self.cueHistory[-15:])):
                if len(x) < 3:
                    break
                elif history_item[0] in x:
                    x.remove(history_item[0])

            cue_name = self.pick_random_cue_from_names(x)

        elif cue_name == "__checkpoint__":
            c = persistance.get_checkpoint(self.id)

            if c:
                # Can't checkpoint a special cue
                if c[0].startswith("__"):
                    return ("", 0)
                if c[0] in self.cues:
                    if self.cues[c[0]].checkpoint:
                        return (c[0], c[1])
            return ("", 0)

        elif cue_name == "__schedule__":
            # Fast forward through scheduled @time endings.

            # Avoid confusing stuff even though we technically could impleent it.
            if self.default_next.strip():
                raise RuntimeError("Scene's default next is not empty, __schedule__ doesn't work here.")

            def processlen(raw_length) -> str:
                # Return length but always a string and empty if it was 0
                try:
                    raw_length = float(raw_length)
                    if raw_length:
                        return str(raw_length)
                    else:
                        return ""
                except Exception:
                    return str(raw_length)

            consider: list[Cue] = []

            found: dict[str, bool] = {}
            pointer = self.cue
            for safety_counter in range(1000):
                # The logical next cue, except that __fast_forward also points to the next in sequence
                nextname = ""
                if pointer.next_ll:
                    nextname = pointer.next_ll.name
                nxt = (pointer.next_cue if not pointer.next_cue == "__schedule__" else nextname) or nextname

                if pointer is not self.cue:
                    if str(pointer.next_cue).startswith("__"):
                        raise RuntimeError("Found special __ cue, fast forward not possible")

                    if str(pointer.length).startswith("="):
                        raise RuntimeError("Found special =expression length cue, fast forward not possible")

                if processlen(pointer.length) or pointer is self.cue:
                    consider.append(pointer)
                    found[pointer.name] = True
                else:
                    break

                if (nxt not in self.cues) or (nxt in found):
                    break

                pointer = self.cues[nxt]

            times: dict[str, float] = {}

            last = None

            scheduled_count = 0

            # Follow chain of next cues to get a set to consider
            for cue in consider:
                if processlen(cue.length).startswith("@"):
                    scheduled_count += 1
                    ref = datetime.datetime.now()
                    selector = util.get_rrule_selector(processlen(cue.length)[1:], ref)
                    a = selector.before(ref)

                    # Hasn't happened yet, can't fast forward past it
                    if not a:
                        break

                    a2 = dt_to_ts(a)

                    # We found the end time of the cue.
                    # If that turns out to be the most recent,
                    # We go to the one after that ifit has a next,
                    # Else just go to
                    if cue.next_ll:
                        times[cue.next_ll.name] = a2
                    elif cue.next_cue in self.cues:
                        times[cue.next_cue] = a2
                    else:
                        times[cue.name] = a2

                    last = a2

                else:
                    if last:
                        times[cue.name] = last + float(cue.length)

            # Can't fast forward without a scheduled cue
            if scheduled_count:
                most_recent: tuple[float, str | None] = (0.0, None)

                # Find the scheduled one that occurred most recently
                for entry in times:
                    if times[entry] > most_recent[0]:
                        if times[entry] < time.time():
                            most_recent = times[entry], entry
                if most_recent[1]:
                    return (most_recent[1], most_recent[0])

        elif cue_name == "__random__":
            x = [i.name for i in self.cues_ordered if not i.name == self.cue.name]
            cue_name = self.pick_random_cue_from_names(x)

        else:
            # Handle random selection option cues
            if "|" in cue_name:
                x = cue_name.split("|")
                if random.random() > 0.3:
                    for i in reversed(self.cueHistory[-15:]):
                        if len(x) < 3:
                            break
                        elif i[0] in x:
                            x.remove(i[0])
                cue_name = self.pick_random_cue_from_names(x)

            elif "*" in cue_name:
                import fnmatch

                x = []

                if cue_name.startswith("shuffle:"):
                    cue_name = cue_name[len("shuffle:") :]
                    shuffle = True
                else:
                    shuffle = False

                for c in self.cues_ordered:
                    if fnmatch.fnmatch(c.name, cue_name):
                        x.append(c.name)
                if not x:
                    raise ValueError("No matching cue for pattern: " + cue_name)

                if shuffle:
                    # Do the "Shuffle logic" that avoids  recently used cues.
                    # Eliminate until only two remain, the min to not get stuck in
                    # A fixed pattern.
                    for history_item in list(reversed(self.cueHistory[-15:])):
                        if len(x) < 3:
                            break
                        elif history_item[0] in x:
                            x.remove(history_item[0])
                cue_name = cue_name = self.pick_random_cue_from_names(x)

        cue_name = cue_name.split("?")[0]

        if cue_name not in self.cues:
            try:
                cue_name = float(cue_name)  # type: ignore
            except Exception:
                raise ValueError("No such cue " + str(cue_name))
            for cue_i in self.cues_ordered:
                if cue_i.number - (float(cue_name) * 1000) < 0.001:
                    cue_name = cue_i.name
                    break

        return (cue_name, 0)

    def goto_cue(
        self,
        cue: str,
        cue_entered_time: float | None = None,
        sendSync=True,
        generateEvents=True,
        cause="generic",
    ):
        """
        A method to go to a specific cue with optional time, synchronization, event generation, and cause specification.

        :param cue: The name of the cue to go to.  May be a cue number or a special value like __random__
        :param t: Optional time parameter, defaults to None.
        :param sendSync: Boolean indicating whether to send synchronization message, defaults to True.
        :param generateEvents: Boolean indicating whether to generate events, defaults to True.
        :param cause: The cause of the cue transition, defaults to "generic".
        """
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

        k2: dict[str, str] = {}

        for i in kwargs:
            if len(kwargs[i]) == 1:
                k2[i] = kwargs[i][0]

        kwargs_var: collections.defaultdict[str, str] = collections.defaultdict(lambda: "")
        kwargs_var.update(k2)

        self.script_context.setVar("KWARGS", kwargs_var)

        cue_entered_time = cue_entered_time or time.time()

        if cue in self.cues:
            if sendSync:
                gn = self.mqtt_sync_features.get("syncGroup", False)
                if gn:
                    topic = f"/kaithem/chandler/syncgroup/{gn}"
                    m = {
                        "time": cue_entered_time,
                        "cue": cue,
                        "senderSessionID": self.mqttNodeSessionID,
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

                cue, cuetime = self._parseCueName(cue)

                cue_entered_time = cuetime or cue_entered_time

                if not cue:
                    return

                cobj = self.cues[cue]

                if self.cue:
                    if cobj == self.cue:
                        if not cobj.reentrant:
                            return
                else:
                    # Act like we actually we in the default cue, but allow reenter no matter what since
                    # We weren't in any cue
                    self.cue = self.cues["default"]
                    self.cueTagClaim.set(self.cue.name, annotation="SceneObject")

                self.entered_cue = cue_entered_time

                # Allow specifying an "Exact" time to enter for zero-drift stuff, so things stay in sync
                # I don't know if it's fully correct to set the timestamp before exit...
                # However we really don't want to queue up a bazillion transitions
                # If we can't keep up, so we limit that to 3s
                # if t and t>time.time()-3:
                # Also, limit to 500ms in the future, seems like there could be bugs otherwise
                #   self.entered_cue = min(t,self.entered_cue+0.5)

                entered = self.entered_cue

                if not (cue == self.cue.name):
                    if generateEvents:
                        if self.active and self.script_context:
                            self.event("cue.exit", value=[self.cue.name, cause])

                # We return if some the enter transition already
                # Changed to a new cue
                if not self.entered_cue == entered:
                    return

                self.cueHistory.append((cue, time.time()))
                self.cueHistory = self.cueHistory[-1024:]
                self.media_ended_at = 0

                try:
                    # Take rules from new cue, don't actually set this as the cue we are in
                    # Until we succeed in running all the rules that happen as we enter
                    # We do set the local variables for the incoming cue though.
                    self.refresh_ules(cobj)
                except Exception:
                    core.rl_log_exc("Error handling script")
                    print(traceback.format_exc(6))

                if self.active:
                    if self.cue.onExit:
                        self.cue.onExit(cue_entered_time)

                    if cobj.onEnter:
                        cobj.onEnter(cue_entered_time)

                    if generateEvents:
                        self.event("cue.enter", [cobj.name, cause])

                # We return if some the enter transition already
                # Changed to a new cue
                if not self.entered_cue == entered:
                    return

                # We don't fully reset until after we are done fading in and have rendered.
                # Until then, the affect list has to stay because it has stuff that prev cues affected.
                # Even if we are't tracking, we still need to know to rerender them without the old effects,
                # And the fade means we might still affect them for a brief time.

                # TODO backtracking these variables?
                cuevars = self.cues[cue].values.get("__variables__", {})
                for var_name in cuevars:
                    if isinstance(var_name, int):
                        print("Bad cue variable name, it's not a string", var_name)
                        continue
                    try:
                        self.script_context.setVar(var_name, self.evalExpr(cuevars[var_name]))
                    except Exception:
                        print(traceback.format_exc())
                        core.rl_log_exc("Error with cue variable " + str(var_name))

                if self.cues[cue].track:
                    self.apply_tracked_values(cue)

                self.media_link_socket.send(
                    [
                        "slide",
                        self.cues[cue].slide,
                        self.entered_cue,
                        max(0, self.cues[cue].fade_in or self.crossfade),
                    ]
                )

                self.media_link_socket.send(
                    [
                        "text",
                        self.cues[cue].markdown,
                    ]
                )

                # optimization, try to se if we can just increment if we are going to the next cue, else
                # we have to actually find the index of the new cue
                if self.cuePointer < (len(self.cues_ordered) - 1) and self.cues[cue] is self.cues_ordered[self.cuePointer + 1]:
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
                            stop_sound(str(self.id))
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
                            stop_sound(str(self.id))

                    self.allowed_remote_media_url = None

                    out: str | None = self.cues[cue].sound_output

                    if not out:
                        out = self.sound_output
                    if not out:
                        out = None

                    if oldSoundOut == "scenewebplayer" and not out == "scenewebplayer":
                        self.media_link_socket.send(["volume", self.alpha])
                        self.media_link_socket.send(
                            [
                                "mediaURL",
                                None,
                                self.entered_cue,
                                max(0, self.cues[cue].fade_in or self.crossfade),
                            ]
                        )

                    if self.cues[cue].sound and self.active:
                        sound = self.cues[cue].sound
                        try:
                            self.cueVolume = min(
                                5,
                                max(
                                    0,
                                    self.evalExprFloat(self.cues[cue].sound_volume or 1),
                                ),
                            )
                        except Exception:
                            self.event(
                                "script.error",
                                self.name + " in cueVolume eval:\n" + traceback.format_exc(),
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

                                spd = self.script_context.preprocessArgument(self.cues[cue].media_speed)
                                spd = spd or 1
                                spd = float(spd)

                                if not (
                                    (
                                        ((self.crossfade > 0) and not (self.cues[cue].sound_fade_in < 0))
                                        and kaithem.sound.is_playing(str(self.id))
                                    )
                                    or (self.cues[cue].fade_in > 0)
                                    or (self.cues[cue].sound_fade_in > 0)
                                    or self.cues[cue].media_wind_up
                                    or self.cue.media_wind_down
                                ):
                                    play_sound(
                                        sound,
                                        handle=str(self.id),
                                        volume=self.alpha * self.cueVolume,
                                        output=out,
                                        loop=self.cues[cue].sound_loops,
                                        start=self.evalExprFloat(self.cues[cue].sound_start_position or 0),
                                        speed=spd,
                                    )
                                else:
                                    fade = self.cues[cue].fade_in or self.cues[cue].sound_fade_in or self.crossfade
                                    # Odd cases where there's a wind up but specifically disabled fade
                                    if self.cues[cue].sound_fade_in < 0:
                                        fade = 0.1

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
                                        speed=spd,
                                    )

                            else:
                                self.allowed_remote_media_url = sound
                                self.media_link_socket.send(["volume", self.alpha])
                                self.media_link_socket.send(
                                    [
                                        "mediaURL",
                                        sound,
                                        self.entered_cue,
                                        max(0, self.cues[cue].fade_in or self.crossfade),
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
                                album_art = soundMeta.get_image()
                            except Exception:
                                # Not support, but it might just be an unsupported type.
                                # if mp3, its a real error, we should alert
                                if sound.endswith(".mp3"):
                                    self.event(
                                        "error",
                                        "Reading metadata for: " + sound + traceback.format_exc(),
                                    )
                                album_art = None
                                currentAudioMetadata = {
                                    "title": "",
                                    "artist": "",
                                    "album": "",
                                    "year": "",
                                }

                            self.cueInfoTag.value = {"audio.meta": currentAudioMetadata}

                            if album_art and len(album_art) < 3 * 10**6:
                                self.albumArtTag.value = "data:image/jpeg;base64," + base64.b64encode(album_art).decode()
                            else:
                                self.albumArtTag.value = ""

                        else:
                            self.event("error", "File does not exist: " + sound)
                sc = self.cues[cue].trigger_shortcut.strip()
                if sc:
                    shortcutCode(sc, exclude=self)
                self.cue = self.cues[cue]

                if self.cue.checkpoint:
                    if not cause == "start":
                        persistance.set_checkpoint(self.id, self.cue.name)

                self.cueTagClaim.set(self.cues[cue].name, annotation="SceneObject")

                self.recalc_randomize_modifier()
                self.recalc_cue_len()

                # Recalc what universes are affected by this scene.
                # We don't clear the old universes, we do that when we're done fading in.
                for i in self.cues[cue].values:
                    i = mapUniverse(i)
                    if i and i in universes.universes:
                        if i not in self.affect:
                            self.affect.append(i)

                    if i and i.startswith("/"):
                        self.on_demand_universes[i] = universes.get_on_demand_universe(i)

                self.cue_vals_to_numpy_cache(self.cue, not self.cue.track)
                self.fade_in_completed = False

                # We don't render here. Very short cues coupt create loops of rerendering and goto
                # self.render(force_repaint=True)

                # Instead we set the flag
                self.rerender = True
                self.pushMeta(statusOnly=True)

                self.preload_next_cue_sound()

                self.media_link_socket.send(["cue_ends", self.cuelen + self.entered_cue, self.cuelen])

            if self.cue.name == "__setup__":
                self.goto_cue("__checkpoint__")

            if self.cue.name == "__setup__":
                self.goto_cue("default", sendSync=False)

    def apply_tracked_values(self, cue) -> dict[str, Any]:
        # When jumping to a cue that isn't directly the next one, apply and "parent" cues.
        # We go backwards until we find a cue that has no parent. A cue has a parent if and only if it has either
        # an explicit parent or the previous cue in the numbered list either has the default next cue or explicitly
        # references this cue.

        # Returns a dict of backtracked variables for
        # the script context that should be set when entering
        # this cue, but that is nit supported yet
        cobj = self.cues[cue]

        vars: dict[str, Any] = {}

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
            self.randomizeModifier = random.triangular(-float(self.cue.length_randomize), +float(self.cue.length_randomize))

    def recalc_cue_len(self):
        "Calculate the actual cue len, without changing the randomizeModifier"
        if not self.active:
            return
        cuelen = self.script_context.preprocessArgument(self.cue.length)
        v = cuelen or 0
        cuelen_str = str(cuelen)

        if cuelen_str.startswith("@"):
            ref = datetime.datetime.now()
            selector = util.get_rrule_selector(cuelen_str[1:], ref)
            nextruntime = selector.after(ref, True)

            if nextruntime <= ref:
                nextruntime = selector.after(nextruntime, False)

            t2 = dt_to_ts(nextruntime, None)

            nextruntime = t2

            v = nextruntime - time.time()

        else:
            v = float(v)
            if len(self.cue.sound) and self.cue.rel_length:
                path = self.resolve_sound(self.cue.sound or self.cue.slide)
                if core.is_img_file(path):
                    v = 0
                else:
                    try:
                        # If we are doing crossfading, we have to stop slightly early for
                        # The crossfade to work
                        # TODO this should not stop early if the next cue overrides
                        duration = core.get_audio_duration(path) or 0
                        if duration > 0:
                            start = self.script_context.preprocessArgument(self.cue.sound_start_position) or 0
                            start = float(start)

                            # Account for media speed
                            spd = self.script_context.preprocessArgument(self.cue.media_speed) or 1
                            spd = float(spd)

                            windup = self.script_context.preprocessArgument(self.cue.media_speed) or 0
                            windup = float(spd)

                            avg_speed_during_windup = (0.1 + spd) / 2
                            covered_by_windup = avg_speed_during_windup * windup

                            duration = duration - start

                            duration = duration - covered_by_windup

                            duration = duration / spd

                            duration += windup

                            slen = (duration - self.crossfade) + float(cuelen)
                            v = max(0, self.randomizeModifier + slen)
                        else:
                            raise RuntimeError("Failed to get length")
                    except Exception:
                        logging.exception("Error getting length for sound " + str(path))
                        # Default to 5 mins just so it's obvious there is a problem, and so that the cue actually does end eventually
                        self.cuelen = 300.0
                        return

            if len(self.cue.slide) and self.cue.rel_length:
                path = self.resolve_sound(self.cue.slide)
                if core.is_img_file(path):
                    pass
                else:
                    try:
                        # If we are doing crossfading, we have to stop slightly early for
                        # The crossfade to work
                        # TODO this should not stop early if the next cue overrides
                        duration = core.get_audio_duration(path) or 0
                        if duration > 0:
                            slen = (duration - self.crossfade) + float(cuelen)
                            # Choose the longer of slide and main sound if both present
                            v = max(0, self.randomizeModifier + slen, v)
                        else:
                            raise RuntimeError("Failed to get length")
                    except Exception:
                        logging.exception("Error getting length for sound " + str(path))
                        # Default to 5 mins just so it's obvious there is a problem, and so that the cue actually does end eventually
                        self.cuelen = 300.0
                        return

        if v <= 0:
            self.cuelen = 0.0
        else:
            # never go below 0.1*the setting or else you could go to zero and get a never ending cue
            self.cuelen = max(0, float(v * 0.1), self.randomizeModifier + float(v))

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

            if universe.startswith("/"):
                self.on_demand_universes[i] = universes.get_on_demand_universe(universe)
                uobj = self.on_demand_universes[i]

            if not uobj:
                continue

            if universe not in self.cue_cached_vals_as_arrays:
                size = len(uobj.values)
                self.cue_cached_vals_as_arrays[universe] = numpy.array([0.0] * size, dtype="f4")
                self.cue_cached_alphas_as_arrays[universe] = numpy.array([0.0] * size, dtype="f4")

            if universe not in self.affect:
                self.affect.append(universe)

            self.rerenderOnVarChange = False

            # TODO stronger type
            dest: dict[str | int, Any] = {}

            for j in cuex.values[i]:
                if isinstance(j, str) and j.startswith("__dest__."):
                    dest[j[9:]] = self.evalExpr(cuex.values[i][j] if cuex.values[i][j] is not None else 0)

            for idx in range(repeats):
                for j in cuex.values[i]:
                    if isinstance(j, str) and j.startswith("__"):
                        continue

                    cuev = cuex.values[i][j]

                    evaled = self.evalExpr(cuev if cuev is not None else 0)
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
                            self.cue_cached_alphas_as_arrays[universe][channel + (idx * chCount)] = 1.0 if cuev is not None else 0
                            self.cue_cached_vals_as_arrays[universe][channel + (idx * chCount)] = evaled
                        except Exception:
                            print("err", traceback.format_exc())
                            self.event(
                                "script.error",
                                self.name + " cue " + cuex.name + " Val " + str((universe, channel)) + "\n" + traceback.format_exc(),
                            )

                    if isinstance(cuev, str) and cuev.startswith("="):
                        self.rerenderOnVarChange = True

    def make_script_context(self):
        scriptContext = DebugScriptContext(self, rootContext, variables=self.chandler_vars, gil=core.lock)

        scriptContext.addNamespace("pagevars")

        def sendMQTT(t, m):
            self.sendMqttMessage(t, m)
            return True

        self.wrMqttCmdSendWrapper = sendMQTT
        scriptContext.commands["sendMQTT"] = sendMQTT
        return scriptContext

    def refresh_ules(self, rulesFrom: Cue | None = None):
        with core.lock:
            # We copy over the event recursion depth so that we can detct infinite loops
            if not self.script_context:
                self.script_context = self.make_script_context()

            self.script_context.clearBindings()

            self.script_context.setVar("SCENE", self.name)
            self.runningTimers = {}

            if self.active:
                self.script_context.setVar("CUE", (rulesFrom or self.cue).name)

                # Actually add the bindings
                rules = (rulesFrom or self.cue).rules
                if rules:
                    self.script_context.addBindings(rules)

                loopPrevent = {(rulesFrom or self.cue.name): True}

                x = (rulesFrom or self.cue).inherit_rules
                while x and x.strip():
                    # Avoid infinite loop should the user define a cycle of cue inheritance
                    if x.strip() in loopPrevent:
                        break

                    if x == "__rules__":
                        break

                    loopPrevent[x.strip()] = True

                    self.script_context.addBindings(self.cues[x].rules)
                    x = self.cues[x].inherit_rules

                if "__rules__" in self.cues:
                    self.script_context.addBindings(self.cues["__rules__"].rules)

                self.script_context.startTimers()
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
            if isinstance(message, bytes):
                self.event("$mqtt:" + topic, json.loads(message.decode("utf-8")))
            else:
                raise TypeError("Not str or bytes")

    def onCueSyncMessage(self, topic: str, message: str):
        gn = self.mqtt_sync_features.get("syncGroup", False)
        if gn:
            # topic = f"/kaithem/chandler/syncgroup/{gn}"
            m = json.loads(message)

            if not self.mqttNodeSessionID == m["senderSessionID"]:
                # # Don't listen to old messages, those are just out of sync nonsense that could be
                # # some error.  However if the time is like, really old.  more than 10 hours, assume that
                # # It's because of an NTP issue and we're just outta sync.
                # if (not ((m['time'] < (time.time()-15) )  and (abs(m['time'] - time.time() )> 36000  ))):

                # TODO: Just ignore cues that do not have a sync match

                if m["cue"] in self.cues:
                    # Don't adjust out start time too much. It only exists to fix network latency.
                    self.goto_cue(
                        m["cue"],
                        cue_entered_time=max(min(time.time() + 0.5, m["time"]), time.time() - 0.5),
                        sendSync=False,
                        cause="MQTT Sync",
                    )

    def doMqttSubscriptions(self, keepUnused=120):
        if self.mqttConnection:
            if self.mqtt_sync_features.get("syncGroup", False):
                # In the future we will not use a leading slash
                self.mqttConnection.subscribe(f"/kaithem/chandler/syncgroup/{self.mqtt_sync_features.get('syncGroup',False)}")
                self.mqttConnection.subscribe(f"kaithem/chandler/syncgroup/{self.mqtt_sync_features.get('syncGroup',False)}")

        if self.mqttConnection and self.script_context:
            # Subscribe to everything we aren't subscribed to
            for i in self.script_context.event_listeners:
                if i.startswith("$mqtt:"):
                    x = i.split(":", 1)
                    if x[1] not in self.mqttSubscribed:
                        self.mqttConnection.subscribe(x[1])
                        self.mqttSubscribed[x[1]] = True

            # Unsubscribe from no longer used things
            torm = []

            for i in self.mqttSubscribed:
                if "$mqtt:" + i not in self.script_context.event_listeners:
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
            for i in self.display_tag_subscription_refs:
                i[0].unsubscribe(i[1])
            self.display_tag_subscription_refs = []
            self.display_tag_values = {}
            self.display_tag_meta = {}

    def make_display_tag_subscriber(self, tag: tagpoints.GenericTagPointClass) -> tuple[tagpoints.GenericTagPointClass, Callable]:
        "Create and return a subscriber to a display tag"
        tag_name = tag.name

        # Todo remove this as we now assume full authority
        if not self.script_context.canGetTagpoint(tag_name):
            raise ValueError("Not allowed tag " + tag_name)

        sn = tag_name[1]
        self.display_tag_meta[sn] = {}
        if isinstance(tag, kaithem.tags.NumericTagPointClass):
            self.display_tag_meta[sn]["min"] = tag.min
            self.display_tag_meta[sn]["max"] = tag.max
            self.display_tag_meta[sn]["hi"] = tag.hi
            self.display_tag_meta[sn]["lo"] = tag.lo
            self.display_tag_meta[sn]["unit"] = tag.unit
        self.display_tag_meta[sn]["subtype"] = tag.subtype

        self.pushMeta(keys=["displayTagMeta"])

        def f(v, t, a):
            self.display_tag_values[sn] = v
            self.pushMeta(keys=["displayTagValues"])

        tag.subscribe(f)
        self.display_tag_values[sn] = tag.value
        self.pushMeta(keys=["displayTagValues"])

        return tag, f

    def set_display_tags(self, dt):
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
                        i.append({"type": "auto"})

                    if "type" not in i[2]:
                        i[2]["type"] = "auto"

                    if i[2]["type"] == "auto":
                        logging.error("Auto type tag display no longer supported")
                        continue

                    t = None

                    if i[2]["type"] == "numeric_input":
                        t = kaithem.tags[i[1]]

                    elif i[2]["type"] == "switch_input":
                        t = kaithem.tags[i[1]]

                    elif i[2]["type"] == "string_input":
                        t = kaithem.tags.StringTag(i[1])

                    elif i[2]["type"] == "text":
                        t = kaithem.StringTag[i[1]]

                    elif i[2]["type"] == "meter":
                        t = kaithem.tags[i[1]]

                    if t:
                        self.display_tag_subscription_refs.append(self.make_display_tag_subscriber(t))
                    else:
                        raise ValueError("Bad tag type?")
            except Exception:
                logging.exception("Failed setting up display tags")
                self.event("board.error", traceback.format_exc())
            self.display_tags = dt

    def clear_configured_tags(self):
        with core.lock:
            for i in self.command_tagSubscriptions:
                i[0].unsubscribe(i[1])
            self.command_tagSubscriptions = []

    def command_tag_subscriber(self):
        def f(v, t, a):
            v = v[0]

            if v.startswith("launch:"):
                shortcutCode(str(v[len("launch:") :]), self)

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
                self.command_tagSubscriptions.append((t, s))
                t.subscribe(s)

    def rename_cue(self, old: str, new: str):
        disallow_special(new, allowedCueNameSpecials)
        if new[0] in "1234567890 \t_":
            new = "x" + new

        if self.cue.name == old:
            raise RuntimeError("Can't rename active cue")
        if new in self.cues:
            raise RuntimeError("Already exists")
        if old == "default":
            raise RuntimeError("Can't rename default cue")

        cue = self.cues.pop(old)
        cue.name = new
        cue.named_for_sound = False
        self.cues[new] = cue

        # Delete old, push new
        for board in core.iter_boards():
            if len(board.newDataFunctions) < 100:
                board.newDataFunctions.append(lambda s: s.linkSend(["delcue", cue.id]))

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
        self.set_display_tags(self.display_tags)

        with core.lock:
            if self in active_scenes:
                return

            # Not sure if we need to remake this, keep it for defensive
            # reasons, TODO
            self.canvas = FadeCanvas()

            self.manualAlpha = False
            self.active = True

            if "__setup__" in self.cues:
                self.goto_cue("__setup__", sendSync=False, cause="start")
            else:
                self.goto_cue("__checkpoint__", sendSync=False, cause="start")
                if not self.cue:
                    self.goto_cue("default", sendSync=False, cause="start")

            # Bug workaround for bug where scenes do nothing when first activated
            self.canvas.paint(
                0,
                vals=self.cue_cached_vals_as_arrays,
                alphas=self.cue_cached_alphas_as_arrays,
            )

            self.entered_cue = time.time()

            if self.blend in blendmodes.blendmodes:
                self._blend = blendmodes.blendmodes[self.blend](self)

            self.effectiveValues = None

            self.metadata_already_pushed_by = {}
            self.started = time.time()

            if self not in _active_scenes:
                _active_scenes.append(self)
            _active_scenes = sorted(_active_scenes, key=lambda k: (k.priority, k.started))
            active_scenes = _active_scenes[:]

            self.setMqttServer(self.mqtt_server)

            # Minor inefficiency rendering twice the first frame
            self.rerender = True
            # self.render()

    def is_active(self):
        return self.active

    @property
    def priority(self):
        return self._priority

    @priority.setter
    def priority(self, p: float):
        global active_scenes, _active_scenes
        self.metadata_already_pushed_by = {}
        self._priority = p
        with core.lock:
            _active_scenes = sorted(_active_scenes, key=lambda k: (k.priority, k.started))
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

    @beartype
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
            self.unusedMqttTopics: dict[str, float] = {}

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
            self.metadata_already_pushed_by = {}
            self.script_context.setVar("SCENE", self.name)

    def setMQTTFeature(self, feature: str, state):
        if state:
            self.mqtt_sync_features[feature] = state
        else:
            self.mqtt_sync_features.pop(feature, None)
        self.metadata_already_pushed_by = {}
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
            x = self.entered_cue
            self.goto_cue(self.cue.name)
            self.entered_cue = x
            self.rerender = True
        self.metadata_already_pushed_by = {}

    def setBPM(self, b):
        b = float(b)
        if self.bpm == b:
            return
        else:
            self.bpm = b
            self.rerender = True
        self.metadata_already_pushed_by = {}

    def tap(self, t: float | None = None):
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

        ts = t - self.entered_cue
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
            self.entered_cue = self.entered_cue * (1 - f) + x * f
        elif self.tapSequence:
            # Just change entered_cue to match the phase.
            self.entered_cue = x
        self.pushMeta(keys={"bpm"})

    def stop(self):
        global active_scenes, _active_scenes
        with core.lock:
            # No need to set rerender
            if self.script_context:
                self.script_context.clearBindings()
                self.script_context.clearState()

            # Use the cue as the marker of if we actually
            # Completed the stop, not just if we logically should be stopped
            # Because we want to be able to manually retry that if we failed.
            if not self.cue:
                return

            # Just using this to get rid of prev value
            self._blend = blendmodes.HardcodedBlendMode(self)
            self.metadata_already_pushed_by = {}

            try:
                for i in self.affect:
                    rerenderUniverse(i)
            except Exception:
                print(traceback.format_exc())

            self.affect = []
            self.on_demand_universes = {}
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
            self.cue = self.cues.get("default", list(self.cues.values())[0])
            self.cueTagClaim.set("__stopped__", annotation="SceneObject")
            self.doMqttSubscriptions(keepUnused=0)

            self.media_link_socket.send(["text", ""])

            self.media_link_socket.send(["mediaURL", "", 0, 0])
            self.media_link_socket.send(["slide", "", 0, 0])

            gc.collect()
            time.sleep(0.002)
            gc.collect()
            time.sleep(0.002)
            gc.collect()

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
                "/midi/" + s.replace(":", "_").replace("[", "").replace("]", "").replace(" ", ""),
                self.onMidiMessage,
            )
        else:
            kaithem.message.subscribe(
                "/midi/" + s.replace(":", "_").replace("[", "").replace("]", "").replace(" ", ""),
                self.onMidiMessage,
            )

        self._midi_source = s

    def onMidiMessage(self, t: str, v: list[Any]):
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
        self.media_link_socket.send(
            [
                "butterchurnfiles",
                [i.split("milkdrop:")[-1] for i in self.music_visualizations.split("\n") if i],
            ]
        )

    def setAlpha(self, val: float, sd: bool = False):
        val = min(1, max(0, val))
        try:
            self.cueVolume = min(5, max(0, float(self.evalExpr(self.cue.sound_volume))))
        except Exception:
            self.event(
                "script.error",
                self.name + " in cueVolume eval:\n" + traceback.format_exc(),
            )
            self.cueVolume = 1

        kaithem.sound.setvol(val * self.cueVolume, str(self.id))

        if not self.is_active() and val > 0:
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

        self.media_link_socket.send(["volume", val])

    def add_cue(self, name: str, **kw: Any):
        return Cue(self, name, **kw)

    def setBlend(self, blend: str):
        disallow_special(blend)
        blend = str(blend)[:256]
        self.blend = blend
        if blend in blendmodes.blendmodes:
            if self.is_active():
                self._blend = blendmodes.blendmodes[blend](self)
            self.blendClass = blendmodes.blendmodes[blend]
            self.setup_blend_args()
        else:
            self.blend_args = self.blend_args or {}
            self._blend = blendmodes.HardcodedBlendMode(self)
            self.blendClass = blendmodes.HardcodedBlendMode
        self.rerender = True
        self.metadata_already_pushed_by = {}

    def setBlendArg(self, key: str, val: float | bool | str):
        disallow_special(key, "_")
        # serializableness check
        json.dumps(val)
        if not hasattr(self.blendClass, "parameters") or key not in self.blendClass.parameters:
            raise KeyError("No such param")

        if val is None:
            del self.blend_args[key]
        else:
            if self.blendClass.parameters[key][1] == "number":
                val = float(val)
            self.blend_args[key] = val
        self.rerender = True
        self.metadata_already_pushed_by = {}

    def render(self, force_repaint: bool = False):
        "Calculate the current alpha value, handle stopping the scene and spawning the next one"
        if self.cue.fade_in:
            fadePosition: float = min(
                (time.time() - self.entered_cue) / (self.cue.fade_in * (60.0 / self.bpm)),
                1.0,
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
                odu = {}

                for i in self.cue_cached_vals_as_arrays:
                    u = mapUniverse(i)
                    if u and u in universes.universes:
                        if u not in self.affect:
                            self.affect.append(u)

                    if u and u.startswith("/"):
                        odu[u] = universes.get_on_demand_universe(u)

                self.on_demand_universes = odu

                # Remove unused universes from the cue
                self.canvas.clean(self.cue_cached_vals_as_arrays)
                self.fade_in_completed = True
                self.rerender = True

        if self.cuelen and (time.time() - self.entered_cue) > self.cuelen * (60 / self.bpm):
            # rel_length cues end after the sound in a totally different part of code
            # Calculate the "real" time we entered, which is exactly the previous entry time plus the len.
            # Then round to the nearest millisecond to prevent long term drift due to floating point issues.
            self.next_cue(round(self.entered_cue + self.cuelen * (60 / self.bpm), 3), cause="time")

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
            self.monitor_values_already_pushed_by = {}

    def new_cue_from_sound(self, snd, name=None):
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
                    s = s[len(i) :]
                    break
            if not s:
                raise RuntimeError("Unknown, linter said was possible")
            self.cues[bn].sound = s
            self.cues[bn].named_for_sound = True
