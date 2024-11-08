from __future__ import annotations

import base64
import collections
import copy
import datetime
import gc
import json
import os
import random
import threading
import time
import traceback
import urllib.parse
import uuid
import weakref
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

import icemedia.sound_player
import numpy
import structlog
from beartype import beartype
from scullery import workers

from .. import alerts, context_restrictions, schemas, tagpoints, util
from ..kaithemobj import kaithem
from . import core, group_media, mqtt, persistance
from .core import disallow_special
from .cue import (
    Cue,
    CueProvider,
    allowedCueNameSpecials,
    cue_provider_types,
    cues,
    get_cue_provider,
)
from .fs_cue_provider import FilesystemCueProvider
from .global_actions import cl_trigger_shortcut_code
from .group_context_commands import add_context_commands, rootContext
from .group_lighting import GroupLightingManager
from .mathutils import dt_to_ts, ease, number_to_note
from .signage import MediaLinkManager
from .universes import get_on_demand_universe, getUniverse, mapChannel

logger = structlog.get_logger(__name__)

if TYPE_CHECKING:
    from . import ChandlerConsole

# Locals for performance... Is this still a thing??
float = float
abs = abs
int = int
max = max
min = min

cue_provider_types["file"] = FilesystemCueProvider

# Indexed by ID
groups: weakref.WeakValueDictionary[str, Group] = weakref.WeakValueDictionary()

# This is only used on some functions.  We have an actual lock,
# It doesn't serve as the lock, it just makes sure we don't try to start a new core lock context,
# Or start a session with another group

# It can't be exclusive because we have lots of groups.
# We don't use it for every single time we get a group

# Get this lock after the core lock but before the render loop lock.
# No other ordering is acceptable.
slow_group_lock_context = context_restrictions.Context("Group Lock")

core.cl_context.opens_before(slow_group_lock_context)


def normalize_midi_name(t):
    "Same function as in the core plugin midi to tags"
    t = (
        t.lower()
        .replace(":", "_")
        .replace("[", "")
        .replace("]", "")
        .replace(" ", "_")
    )
    t = t.replace("-", "_")
    for i in tagpoints.ILLEGAL_NAME_CHARS:
        t = t.replace(i, "")

    return t


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


def makeWrappedConnectionClass(parent: Group):
    self_closure_ref = parent

    class Connection(mqtt.MQTTConnection):
        def on_connect(self):
            self_closure_ref.event("board.mqtt.connected")
            self_closure_ref.pushMeta(statusOnly=True)
            return super().on_connect()

        def on_disconnect(self):
            self_closure_ref.event("board.mqtt.disconnected")
            self_closure_ref.pushMeta(statusOnly=True)
            if self_closure_ref.mqtt_server:
                self_closure_ref.event("board.mqtt.error", "Disconnected")
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


class DebugScriptContext(kaithem.chandlerscript.ChandlerScriptContext):
    def __init__(self, groupObj: Group, *a, **k):
        self.groupObj = weakref.ref(groupObj)
        self.groupName: str = groupObj.name
        self.groupId = groupObj.id
        super().__init__(*a, **k)

    def onVarSet(self, k, v):
        group = self.groupObj()
        if group:
            try:
                if (k not in ("_", "event")) and group.rerenderOnVarChange:
                    group.lighting_manager.recalc_cue_vals()
                    group.poll_again_flag = True
                    group.lighting_manager.rerender()

            except Exception:
                core.rl_log_exc("Error handling var set notification")
                print(traceback.format_exc())

            try:
                if not k.startswith("_") and not k == "event":
                    for board in core.iter_boards():
                        if board:
                            if isinstance(v, (str, int, float, bool)):
                                board.linkSend(
                                    ["varchange", self.groupId, k, v]
                                )
                            elif isinstance(v, collections.defaultdict):
                                v = json.dumps(v)[:160]
                                board.linkSend(
                                    ["varchange", self.groupId, k, v]
                                )
                            else:
                                v = str(v)[:160]
                                board.linkSend(
                                    ["varchange", self.groupId, k, v]
                                )
            except Exception:
                core.rl_log_exc("Error handling var set notification")
                print(traceback.format_exc())

    @slow_group_lock_context.object_session_entry_point
    def event(
        self,
        evt: str,
        val: str | float | int | bool | None = None,
        timestamp=None,
    ):
        kaithem.chandlerscript.ChandlerScriptContext.event(
            self, evt, val, timestamp=timestamp
        )
        try:
            for board in core.iter_boards():
                board.pushEv(evt, self.groupName, time.time(), value=val)
        except Exception:
            core.rl_log_exc("error handling event")
            print(traceback.format_exc())

    def onTimerChange(self, timer, nextRunTime):
        group = self.groupObj()
        if group:
            group.runningTimers[timer] = nextRunTime
            try:
                for board in core.iter_boards():
                    board.linkSend(
                        ["grouptimers", group.id, group.runningTimers]
                    )
            except Exception:
                core.rl_log_exc("Error handling timer set notification")
                print(traceback.format_exc())

    def canGetTagpoint(self, t):
        if t not in self.tagpoints and len(self.tagpoints) > 128:
            raise RuntimeError("Too many tagpoints in one group")
        return t

    # def do_async(self, f):
    #     core.serialized_async_with_core_lock(f)


def checkPermissionsForGroupData(data: dict[str, Any], user: str):
    """Check if used can upload or edit the group, else raise an
      error if
        it uses advanced features that would prevent that action.
    We disallow delete because we don't want unprivileged users
    to delete something important that they can't fix.

    """
    if "mqtt_server" in data and data["mqtt_server"].strip():
        if not kaithem.users.check_permission(user, "system_admin"):
            raise ValueError(
                "You cannot do this action on this group without system_admin, because it uses advanced features: MQTT:"
                + str(kaithem.web.user(None))
            )


group_schema = schemas.get_schema("chandler/group")


class Group:
    "An objecting representing one group. If noe default cue present one is made"

    @slow_group_lock_context.object_session_entry_point
    def __init__(
        self,
        chandler_board: ChandlerConsole.ChandlerConsole,
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
        require_confirm: bool = False,
        mqtt_sync_features: dict[str, Any] | None = None,
        cue_providers: list[str] | None = [],
        **ignoredParams,
    ):
        """

        Raises:
            RuntimeError: _description_
            ValueError: _description_
        """

        self.board = chandler_board

        if name and name in self.board.groups_by_name:
            raise RuntimeError("Cannot have 2 groups sharing a name: " + name)

        if not name.strip():
            raise ValueError("Invalid Name")

        # Used by blend modes
        self.blend_args: dict[str, float | int | bool | str] = blend_args or {}

        self.media_player = group_media.GroupMediaPlayer(self)
        self.lighting_manager = GroupLightingManager(self)

        self._cue_providers: list[str] = cue_providers or []

        self._cue_provider_objects: list[CueProvider] = [
            get_cue_provider(cue_provider, self)
            for cue_provider in self._cue_providers
        ]

        # Get whatever defaults it sets up for the UI
        self.blend_args = copy.deepcopy(self.lighting_manager.blend_args)

        self.mqttConnection = None
        self.mqttSubscribed: dict[str, bool]

        self.require_confirm = require_confirm

        # he commands specific to this group for the scripting
        self.command_refs: dict[str, Callable[..., Any]] = {}

        disallow_special(name)

        self.mqtt_sync_features: dict[str, Any] = mqtt_sync_features or {}
        self.mqttNodeSessionID: str = base64.b64encode(os.urandom(8)).decode()

        self.event_buttons: list = event_buttons[:]
        self.info_display = info_display
        self.utility: bool = bool(utility)

        self.id: str = id or uuid.uuid4().hex

        self.media_link = MediaLinkManager(self)
        self.media_link_socket = self.media_link.media_link_socket

        self.slide_overlay_url: str = slide_overlay_url

        # Kind of long so we do it in the external file
        self.slideshow_layout: str = (
            slideshow_layout.strip()
            or group_schema["properties"]["slideshow_layout"]["default"]
        )

        # Audio visualizations
        self.music_visualizations = music_visualizations

        self.hide = hide

        self.lock = threading.RLock()
        self.randomizeModifier = 0

        self.command_tagSubscriptions: list[
            tuple[tagpoints.ObjectTagPointClass, Callable]
        ] = []
        self.command_tag = command_tag

        self.notes = notes
        self._midi_source: str = ""
        self.default_next = str(default_next).strip()

        # TagPoint for managing the current cue
        self.cueTag = kaithem.tags.StringTag(
            "/chandler/groups/" + name + ".cue"
        )
        self.cueTag.expose("view_status", "chandler_operator")

        self.cueTagClaim = self.cueTag.claim(
            "__stopped__", "Group", 50, annotation="GroupObject"
        )

        self.cueVolume = 1.0

        self.error_codes = {}

        self.error_code_alert = alerts.Alert(
            "/chandler/groups/" + name + ".error_codes", priority="error"
        )

        # Allow goto_cue
        def cueTagHandler(val, timestamp, annotation):
            # We generated this event, that means we don't have to respond to it
            if annotation == "GroupObject":
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
            "/chandler/groups/" + name + ".cueInfo"
        )
        self.cueInfoTag.value = {"audio.meta": {}}
        self.cueInfoTag.expose("view_status", "chandler_operator")

        self.albumArtTag = kaithem.tags.StringTag(
            "/chandler/groups/" + name + ".albumArt"
        )
        self.albumArtTag.expose("view_status")

        # Used to determine the numbering of added cues
        self.topCueNumber = 0
        # Only used for monitor groups

        self.alpha = alpha
        self.crossfade = crossfade

        self.cuelen = 0.0

        # TagPoint for managing the current alpha
        self.alphaTag = kaithem.tags["/chandler/groups/" + name + ".alpha"]
        self.alphaTag.min = 0
        self.alphaTag.max = 1
        self.alphaTag.expose("view_status", "chandler_operator")

        self.alphaTagClaim = self.alphaTag.claim(
            self.alpha, "Group", 50, annotation="GroupObject"
        )

        # Allow setting the alpha
        def alphaTagHandler(val, timestamp, annotation):
            # We generated this event, that means we don't have to respond to it
            if annotation == "GroupObject":
                return
            self.setAlpha(val)

        self.alphaTag.subscribe(alphaTagHandler)
        self.alphaTagHandler = alphaTagHandler

        self.active = False
        self.default_alpha = alpha
        self.name = name

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

        # A pointer into that list pointing at the current cue. We have to update all this
        # every time we change the lists
        self.cuePointer = 0

        # Used for storing when the sound file  or slide ended. 0 indicates a sound file end event hasn't
        # happened since the cue started
        self.media_ended_at = 0

        self.cueTagClaim.set(self.cue.name, annotation="GroupObject")

        # Used to avoid an excessive number of repeats in random cues
        self.cueHistory: list[tuple[str, float]] = []

        self.rerenderOnVarChange = False

        self.entered_cue: float = 0
        self.entered_cue_frame_number = 0

        # Map event name to runtime as unix timestamp
        self.runningTimers: dict[str, float] = {}

        self._priority = priority

        self.setBlend(blend)
        self.default_active = default_active

        # Used to indicate that the most recent frame has changed something about the group
        # Metadata that GUI clients need to know about.

        # An entry here means the board with that ID is all good
        # Clear this to indicate everything needs to be sent to web.
        self.metadata_already_pushed_by: dict[str, bool] = {}

        # Set to true every time the alpha value changes or a group value changes
        # set to false at end of rendering
        self.poll_again_flag = False

        # Last time the group was started. Not reset when stopped
        self.started = 0.0

        # Script engine variable space
        self.chandler_vars: dict[str, Any] = {}

        if name:
            self.board.groups_by_name[self.name] = self
        if not name:
            name = self.id
        groups[self.id] = self

        # The bindings for script commands that might be in the cue metadata
        # Used to be made on demand, now we just always have it
        self.script_context = self.make_script_context()

        add_context_commands(self)

        # Holds (tagpoint, subscribe function) tuples whenever we subscribe
        # to a tag to display it
        self.display_tag_subscription_refs: list[
            tuple[tagpoints.GenericTagPointClass, Callable]
        ] = []

        # Name, TagpointName, properties
        # This is the actual configured data.
        self.display_tags: list[tuple[str, str, dict[str, Any]]] = []

        # The most recent values of our display tags
        self.display_tag_values: dict[str, Any] = {}

        self.display_tag_meta: dict[str, dict[str, Any]] = {}
        self.set_display_tags(display_tags)

        self.refresh_rules()

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
            self.cueTagClaim.set("__stopped__", annotation="GroupObject")

        def f():
            with self.lock:
                self._nl_subscribe_command_tags()

        workers.do(f)

        workers.do(self.scan_cue_providers)

    def check_error_codes(self):
        if self.error_codes:
            self.error_code_alert.trip(str(self.error_codes))
        else:
            self.error_code_alert.clear()

    @property
    def cue_providers(self):
        return self._cue_providers

    @cue_providers.setter
    def cue_providers(self, value: list[str]):
        self._cue_providers = value
        self._cue_provider_objects = [
            get_cue_provider(cue_provider, self)
            for cue_provider in self._cue_providers
        ]
        workers.do(self.scan_cue_providers)

    def get_cue_provider(self, name: str) -> CueProvider:
        for i in self._cue_provider_objects:
            if i.url == name:
                return i
        raise RuntimeError("Cue provider does not exist in group")

    @slow_group_lock_context.object_session_entry_point
    def scan_cue_providers(self):
        discovered = {}
        try:
            for i in self._cue_provider_objects:
                c = i.scan_cues()
                for cue in c.values():
                    assert cue.provider == i.url
                    if cue.name not in self.cues:
                        self._add_cue(cue)
                    discovered[cue.id] = i

            for i in self.cues:
                if self.cues[i].provider:
                    if self.cues[i].id not in discovered:
                        self.rmCue(self.cues[i].name, allow_rm_external=True)

            self.error_codes.pop("cue_provider_error", None)
            self.check_error_codes()

        except Exception as e:
            self.error_codes["cue_provider_error"] = str(e)
            self.check_error_codes()
            logger.exception("Cue provider error")
            raise

    @slow_group_lock_context.object_session_entry_point
    def toDict(self) -> dict[str, Any]:
        # These are the properties that aren't just straight 1 to 1 copies
        # of props, but still get saved

        d = {
            "alpha": self.default_alpha,
            "cues": {
                j: self.cues[j].serialize()
                for j in self.cues
                if not self.cues[j].provider
            },
            "active": self.default_active,
            "uuid": self.id,
        }

        # Call the cue provider to self.cues[i].providerave any cues that aren't normal cues and are
        # Instead imported from somewhere.
        for i in self.cues:
            if self.cues[i].provider:
                p = (
                    self.cues[i]
                    .getGroup()
                    .get_cue_provider(self.cues[i].provider)
                )
                if p:
                    p.save_cue(self.cues[i])

        for i in group_schema["properties"]:
            if i not in d:
                d[i] = getattr(self, i)

        schemas.validate("chandler/group", d)

        return d

    def check_sound_state(self):
        if not self.active:
            return
        # If the cuelen isn't 0 it means we are using the newer version that supports randomizing lengths.
        # We keep this in case we get a sound format we can'r read the length of in advance
        if self.cuelen == 0:
            # Forbid any crazy error loopy business with too short sounds
            if (time.time() - self.entered_cue) > 1 / 5:
                if self.cue.sound and self.cue.rel_length:
                    if not self.media_ended_at:
                        if not icemedia.sound_player.is_playing(str(self.id)):
                            self.media_ended_at = time.time()
                    cuelen = self.evalExprFloat(self.cue.length)
                    if self.media_ended_at and (
                        time.time() - self.media_ended_at > (cuelen * self.bpm)
                    ):
                        self.next_cue(cause="sound")

    def __del__(self):
        pass

    def getStatusString(self):
        x = ""
        if self.mqttConnection:
            if not self.mqttConnection.is_connected:
                x += "MQTT Disconnected "
        return x

    @slow_group_lock_context.object_session_entry_point
    def close(self):
        "Unregister the group and delete it from the lists"

        def f():
            if self.board.groups_by_name.get(self.name, None) is self:
                del self.board.groups_by_name[self.name]

            if groups.get(self.id, None) is self:
                del groups[self.id]

        core.serialized_async_with_core_lock(f)

        with self.lock:
            self.stop()
            self.mqtt_server = ""
            x = self.mqttConnection
            if x:
                x.disconnect()

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

    def _nl_insert_cue_sorted(self, c: Cue | None):
        "Insert a None to just recalt the whole ordering"
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
        with self.lock:
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

    @slow_group_lock_context.object_session_entry_point
    def rmCue(self, cue: str, allow_rm_external: bool = False):
        with self.lock:
            if not len(self.cues) > 1:
                raise RuntimeError("Cannot have group with no cues")

            if cue in cues:
                if cues[cue].name == "default":
                    raise RuntimeError("Cannot delete the cue named default")

                if cues[cue].provider:
                    if not allow_rm_external:
                        raise RuntimeError(
                            "Cannot delete the cue with a provider"
                        )

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
                self.cues[cues[cue].name].shortcut = ""
                del self.cues[cues[cue].name]
            elif cue in self.cues:
                id = self.cues[cue].id
                self.cues[cue].shortcut = ""
                del self.cues[cue]

            for board in core.iter_boards():
                if len(board.newDataFunctions) < 100:
                    board.newDataFunctions.append(
                        lambda s: s.linkSend(["delcue", id])
                    )
            try:
                self.cuePointer = self.cues_ordered.index(self.cue)
            except Exception:
                print(traceback.format_exc())
        # Regenerate linked list by brute force when a new cue is added.
        for i in range(len(self.cues_ordered) - 1):
            self.cues_ordered[i].next_ll = self.cues_ordered[i + 1]
        self.cues_ordered[-1].next_ll = None

    @slow_group_lock_context.object_session_entry_point
    def _add_cue(self, cue: Cue, forceAdd=True):
        name = cue.name
        with self.lock:
            self._nl_insert_cue_sorted(cue)
            if name in self.cues and not forceAdd:
                if self.cues[name] is cue:
                    return
                raise RuntimeError("Cue would overwrite existing.")
            self.cues[name] = cue

        core.add_data_pusher_to_all_boards(
            lambda s: s.pushCueMeta(self.cues[name].id)
        )
        core.add_data_pusher_to_all_boards(lambda s: s.pushCueData(cue.id))

    def pushMeta(
        self,
        cue: str | bool = False,
        statusOnly: bool = False,
        keys: None | Iterable[str] = None,
    ):
        # Push cue first so the client already has that data when we jump to the new display
        if cue and self.cue:
            core.add_data_pusher_to_all_boards(
                lambda s: s.pushCueMeta(self.cue.id)
            )

        core.add_data_pusher_to_all_boards(
            lambda s: s.pushMeta(self.id, statusOnly=statusOnly, keys=keys)
        )

    @slow_group_lock_context.object_session_entry_point
    def event(
        self,
        s: str,
        value: Any = True,
        info: str = "",
        exclude_errors: bool = True,
        ts=None,
    ):
        # No error loops allowed!
        if (not s == "script.error") and exclude_errors:
            self._event(s, value, info, ts=ts)

    def _event(self, s: str, value: Any, info: str = "", ts=None):
        "Manually trigger any script bindings on an event"
        try:
            if self.script_context:
                self.script_context.event(s, value, timestamp=ts)
        except Exception:
            core.rl_log_exc("Error handling event: " + str(s))
            print(traceback.format_exc(6))

    def pick_random_cue_from_names(
        self, cues: list[str] | set[str] | dict[str, Any]
    ) -> str:
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
                weights.append(
                    self.evalExprFloat(
                        str(self.cues[i].probability).strip() or 1
                    )
                )
                names.append(i)

        return random.choices(names, weights=weights)[0]

    def _parseCueName(self, cue_name: str) -> tuple[str, float | int]:
        """
        Take a raw cue name and find an actual matching cue. Handles things like shuffle
        Returns a tuple of cuename, entered_time because some special cues are things
        like stored checkpoints which may have an old entered_time.
        """
        if cue_name == "__shuffle__":
            x = [
                i.name
                for i in self.cues_ordered
                if not (i.name == self.cue.name)
            ]

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

            # Avoid confusing stuff even though we technically could implement it.
            if self.default_next.strip():
                raise RuntimeError(
                    "Group's default next is not empty, __schedule__ doesn't work here."
                )

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
                nxt = (
                    pointer.next_cue
                    if not pointer.next_cue == "__schedule__"
                    else nextname
                ) or nextname

                if pointer is not self.cue:
                    if str(pointer.next_cue).startswith("__"):
                        raise RuntimeError(
                            "Found special __ cue, fast forward not possible"
                        )

                    if str(pointer.length).startswith("="):
                        raise RuntimeError(
                            "Found special =expression length cue, fast forward not possible"
                        )

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
                    selector = util.get_rrule_selector(
                        processlen(cue.length)[1:], ref
                    )
                    a: datetime.datetime = selector.before(ref)

                    # Hasn't happened yet, can't fast forward past it
                    if not a:
                        break

                    if not a.tzinfo:
                        a = a.astimezone()

                    a2 = dt_to_ts(a)

                    # We found the end time of the cue.
                    # If that turns out to be the most recent,
                    # We go to the one after that if it has a next,
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
            x = [
                i.name for i in self.cues_ordered if not i.name == self.cue.name
            ]
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

    @slow_group_lock_context.object_session_entry_point
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

        # Wait until a full frame has passed since the last cue change
        # So the previous cue's effects can propagate.
        # There is a big problem here in that this cue transition
        # itself could be what is blocking everything up
        if core.completed_frame_number < self.entered_cue_frame_number + 1:
            for i in range(10):
                if (
                    core.completed_frame_number
                    < self.entered_cue_frame_number + 1
                ):
                    time.sleep(0.05)

        # Ignore old cue transitions, but with some slop margin for bad time sync
        if cue_entered_time and cue_entered_time < self.entered_cue - 60:
            return

        # Exact match is definitely a repeat
        if cue_entered_time and cue_entered_time == self.entered_cue:
            return

        # Not really in a cue, reentrancy doesn't apply
        skip_reentrant_check = self.entered_cue == 0

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

        kwargs_var: collections.defaultdict[str, str] = collections.defaultdict(
            lambda: ""
        )
        kwargs_var.update(k2)

        with self.lock:
            cue_entered_time = cue_entered_time or time.time()

            if not self.active:
                return

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

                if cue == "__stop__":
                    self.stop()
                    return

            cue, cuetime = self._parseCueName(cue)

            cue_entered_time = cuetime or cue_entered_time

            if not cue:
                return

            self.script_context.setVar("KWARGS", kwargs_var)

            cobj = self.cues[cue]

            if self.cue:
                if cobj == self.cue:
                    if not (cobj.reentrant or skip_reentrant_check):
                        return
            else:
                # Act like we actually we in the default cue, but allow reenter no matter what since
                # We weren't in any cue
                self.cue = self.cues["default"]
                self.cueTagClaim.set(self.cue.name, annotation="GroupObject")

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
                self.refresh_rules(cobj)
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

            # optimization, try to se if we can just increment if we are going to the next cue, else
            # we have to actually find the index of the new cue
            if (
                self.cuePointer < (len(self.cues_ordered) - 1)
                and self.cues[cue] is self.cues_ordered[self.cuePointer + 1]
            ):
                self.cuePointer += 1
            else:
                self.cuePointer = self.cues_ordered.index(self.cues[cue])

            sc = self.cues[cue].trigger_shortcut.strip()
            if sc:

                def f():
                    cl_trigger_shortcut_code(sc, exclude=self)

                core.serialized_async_with_core_lock(f)
            self.cue = self.cues[cue]

            if self.cue.checkpoint:
                if not cause == "start":
                    persistance.set_checkpoint(self.id, self.cue.name)

            self.cueTagClaim.set(self.cues[cue].name, annotation="GroupObject")

            self.recalc_randomize_modifier()
            self.recalc_cue_len()

            self.lighting_manager.next(self.cues[cue])

            # We don't render here. Very short cues coupt create loops of rerendering and goto
            # self.render(force_repaint=True)

            # Instead we set the flag
            self.poll_again_flag = True
            self.pushMeta(statusOnly=True)

            self.preload_next_cue_sound()
            self.media_player.next(self.cues[cue])
            self.media_link.next(self.cues[cue])

            # Do this last because it's what we use for the rate limiting
            self.entered_cue_frame_number = core.started_frame_number

        if self.cue.name == "__setup__":
            self.goto_cue("__checkpoint__")

        if self.cue.name == "__setup__":
            self.goto_cue("default", sendSync=False)

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
                sound = self.resolve_media(sound, c)
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

    def resolve_media(self, sound, cue_scope: Cue | None = None) -> str:
        f = copy.copy(self.board.media_folders)

        if cue_scope:
            if cue_scope.provider:
                p = self.get_cue_provider(cue_scope.provider)
                d = p.get_dir_for_cue(cue_scope)
                if d:
                    f.append(d)

        return core.resolve_sound(sound, extra_folders=f)

    def recalc_randomize_modifier(self):
        "Recalculate the random variance to apply to the length"
        if self.cue:
            self.randomizeModifier = random.triangular(
                -float(self.cue.length_randomize),
                +float(self.cue.length_randomize),
            )

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

            t2 = dt_to_ts(nextruntime)

            nextruntime = t2

            v = nextruntime - time.time()

        else:
            v = float(v)
            if len(self.cue.sound) and self.cue.rel_length:
                path = self.resolve_media(
                    self.cue.sound or self.cue.slide, self.cue
                )
                if core.is_img_file(path):
                    v = 0
                else:
                    try:
                        # If we are doing crossfading, we have to stop slightly early for
                        # The crossfade to work
                        # TODO this should not stop early if the next cue overrides
                        duration = core.get_audio_duration(path) or 0

                        loops: int = (
                            int(
                                self.script_context.preprocessArgument(
                                    self.cue.sound_loops
                                )
                            )
                            or 0
                        )
                        if loops > 1:
                            duration = duration * loops

                        # Dummy very long time for endless looping.
                        if loops < 0:
                            duration = 2**31

                        if duration > 0:
                            start = (
                                self.script_context.preprocessArgument(
                                    self.cue.sound_start_position
                                )
                                or 0
                            )
                            start = float(start)

                            # Account for media speed
                            spd = (
                                self.script_context.preprocessArgument(
                                    self.cue.media_speed
                                )
                                or 1
                            )
                            spd = float(spd)

                            windup = (
                                self.script_context.preprocessArgument(
                                    self.cue.media_speed
                                )
                                or 0
                            )
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
                        logger.exception(
                            "Error getting length for sound " + str(path)
                        )
                        # Default to 5 mins just so it's obvious there is a problem, and so that the cue actually does end eventually
                        self.cuelen = 300.0
                        return

            if len(self.cue.slide) and self.cue.rel_length:
                path = self.resolve_media(self.cue.slide, self.cue)
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
                        logger.exception(
                            "Error getting length for sound " + str(path)
                        )
                        # Default to 5 mins just so it's obvious there is a problem, and so that the cue actually does end eventually
                        self.cuelen = 300.0
                        return

        if v <= 0:
            self.cuelen = 0.0
        else:
            # never go below 0.1*the setting or else you could go to zero and get a never ending cue
            self.cuelen = max(
                0, float(v * 0.1), self.randomizeModifier + float(v)
            )

    @slow_group_lock_context.object_session_entry_point
    def make_script_context(self):
        scriptContext = DebugScriptContext(
            self,
            parentContext=rootContext,
            variables=self.chandler_vars,
            gil=self.lock,
        )

        scriptContext.addNamespace("pagevars")

        def sendMQTT(t, m):
            self.sendMqttMessage(t, m)
            return True

        self.wrMqttCmdSendWrapper = sendMQTT
        scriptContext.commands["sendMQTT"] = sendMQTT
        return scriptContext

    @slow_group_lock_context.object_session_entry_point
    def refresh_rules(self, rulesFrom: Cue | None = None):
        with self.lock:
            # We copy over the event recursion depth so that we can detect infinite loops
            if not self.script_context:
                self.script_context = self.make_script_context()

            self.script_context.clearBindings()

            self.script_context.setVar("GROUP", self.name)
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
                    self.script_context.addBindings(
                        self.cues["__rules__"].rules
                    )

                self.script_context.startTimers()
                self.doMqttSubscriptions()

            try:
                for board in core.iter_boards():
                    board.linkSend(["grouptimers", self.id, self.runningTimers])
            except Exception:
                core.rl_log_exc("Error handling timer set notification")

    def onMqttMessage(self, topic: str, message: str | bytes):
        try:
            self.event("$mqtt:" + topic, message)
        except Exception:
            if isinstance(message, bytes):
                self.event(
                    "$mqtt:" + topic, json.loads(message.decode("utf-8"))
                )
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
                        cue_entered_time=max(
                            min(time.time() + 0.5, m["time"]), time.time() - 0.5
                        ),
                        sendSync=False,
                        cause="MQTT Sync",
                    )

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

        if self.mqttConnection and self.script_context:
            # Subscribe to everything we aren't subscribed to
            for i in self.script_context.event_listeners:
                if i.startswith("$mqtt:"):
                    x = i.split(":", 1)
                    if x[1] not in self.mqttSubscribed:
                        self.mqttConnection.subscribe(x[1])
                        self.mqttSubscribed[x[1]] = True

            # Unsubscribe from no longer used things
            to_rm = []

            for i in self.mqttSubscribed:
                if "$mqtt:" + i not in self.script_context.event_listeners:
                    if i not in self.unusedMqttTopics:
                        self.unusedMqttTopics[i] = time.monotonic()
                        continue
                    elif (
                        self.unusedMqttTopics[i] > time.monotonic() - keepUnused
                    ):
                        continue
                    self.mqttConnection.unsubscribe(i)
                    del self.unusedMqttTopics[i]
                    to_rm.append(i)
                else:
                    if i in self.unusedMqttTopics:
                        del self.unusedMqttTopics[i]

            for i in to_rm:
                del self.mqttSubscribed[i]

    def sendMqttMessage(self, topic, message):
        "JSON encodes message, and publishes it to the group's MQTT server"
        if self.mqttConnection:
            self.mqttConnection.publish(topic, json.dumps(message))

    def _nl_clear_display_tags(self):
        """Must be called under lock.  Clear all the display tags"""
        for i in self.display_tag_subscription_refs:
            i[0].unsubscribe(i[1])
        self.display_tag_subscription_refs = []
        self.display_tag_values = {}
        self.display_tag_meta = {}

    def make_display_tag_subscriber(
        self, tag: tagpoints.GenericTagPointClass
    ) -> tuple[tagpoints.GenericTagPointClass, Callable]:
        "Create and return a subscriber to a display tag"
        tag_name = tag.name

        # Todo remove this as we now assume full authority
        if not self.script_context.canGetTagpoint(tag_name):
            raise ValueError("Not allowed tag " + tag_name)

        sn = tag_name
        self.display_tag_meta[sn] = {}
        if isinstance(tag, kaithem.tags.NumericTagPointClass):
            self.display_tag_meta[sn]["min"] = tag.min
            self.display_tag_meta[sn]["max"] = tag.max
            self.display_tag_meta[sn]["hi"] = tag.hi
            self.display_tag_meta[sn]["lodisplayTagValues"] = tag.lo
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

    @slow_group_lock_context.object_session_entry_point
    def set_display_tags(self, dt):
        dt = dt[:]
        with self.lock:
            self._nl_clear_display_tags()
            gc.collect()
            gc.collect()
            gc.collect()

            try:
                for i in dt:
                    i[1] = tagpoints.normalize_tag_name(i[1])
                    # Upgrade legacy format
                    if len(i) == 2:
                        i.append({"type": "auto"})

                    if "type" not in i[2]:
                        i[2]["type"] = "auto"

                    if "width" not in i[2]:
                        i[2]["width"] = "4"

                    if i[2]["type"] == "auto":
                        logger.error(
                            "Auto type tag display no longer supported"
                        )
                        continue

                    t = None

                    if not i[2]["type"] == "led":
                        i[2].pop("color", None)
                        i[2].pop("pattern", None)

                    if i[2]["type"] == "numeric_input":
                        t = kaithem.tags[i[1]]

                    elif i[2]["type"] == "switch_input":
                        t = kaithem.tags[i[1]]

                    elif i[2]["type"] == "string_input":
                        t = kaithem.tags.StringTag(i[1])

                    elif i[2]["type"] == "text":
                        t = kaithem.tags.StringTag(i[1])

                    elif i[2]["type"] == "meter":
                        t = kaithem.tags[i[1]]

                    elif i[2]["type"] == "led":
                        t = kaithem.tags[i[1]]

                    if t:
                        self.display_tag_subscription_refs.append(
                            self.make_display_tag_subscriber(t)
                        )
                    else:
                        raise ValueError("Bad tag type?")
            except Exception:
                logger.exception("Failed setting up display tags")
                self.event("board.error", traceback.format_exc())
            self.display_tags = dt

            self.pushMeta(keys=["display_tags"])

    def _nl_clear_configured_tags(self):
        for i in self.command_tagSubscriptions:
            i[0].unsubscribe(i[1])
        self.command_tagSubscriptions = []

    def command_tag_subscriber(self):
        def f(v, t, a):
            v = v[0]

            if v.startswith("launch:"):

                def f():
                    cl_trigger_shortcut_code(str(v[len("launch:") :]), self)

                core.serialized_async_with_core_lock(f)

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

    def _nl_subscribe_command_tags(self):
        if not self.command_tag.strip():
            return

        for i in [self.command_tag]:
            t = kaithem.tags.ObjectTag(i)
            s = self.command_tag_subscriber()
            self.command_tagSubscriptions.append((t, s))
            t.subscribe(s)

    @slow_group_lock_context.object_session_entry_point
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
                board.newDataFunctions.append(
                    lambda s: s.linkSend(["delcue", cue.id])
                )

        cue.push()

    @slow_group_lock_context.object_session_entry_point
    def set_command_tag(self, tag_name: str):
        tag_name = tag_name.strip()

        with self.lock:
            self._nl_clear_configured_tags()

            self.command_tag = tag_name

            if tag_name:
                tag = kaithem.tags.ObjectTag(tag_name)
                if tag.subtype and not tag.subtype == "event":
                    raise ValueError("That tag does not have the event subtype")

                self._nl_subscribe_command_tags()

    @slow_group_lock_context.object_session_entry_point
    def next_cue(self, t=None, cause="generic"):
        cue = self.cue
        if not cue:
            return

        with self.lock:
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

    @slow_group_lock_context.object_session_entry_point
    def prev_cue(self, cause="generic"):
        with self.lock:
            if len(self.cueHistory) > 1:
                c = self.cueHistory[-2]
                c = c[0]
                self.goto_cue(c, cause=cause)

    def __repr__(self):
        return f"<Group {self.name}>"

    @slow_group_lock_context.object_session_entry_point
    def go(self):
        with self.lock:
            if self.active:
                return

            self.set_display_tags(self.display_tags)

            self.active = True

            if "__setup__" in self.cues:
                self.goto_cue("__setup__", sendSync=False, cause="start")
            else:
                self.goto_cue("__checkpoint__", sendSync=False, cause="start")
                if not self.entered_cue:
                    self.goto_cue("default", sendSync=False, cause="start")

            self.entered_cue = time.time()

            self.setBlend(self.blend)
            self.metadata_already_pushed_by = {}
            self.started = time.time()

            self.setMqttServer(self.mqtt_server)

            # Minor inefficiency rendering twice the first frame
            self.poll_again_flag = True
            self.lighting_manager.rerender()

            self.active = True

            def f():
                self.board.cl_add_to_active_groups(self)

            core.serialized_async_with_core_lock(f)

    def is_active(self):
        return self.active

    @property
    def priority(self):
        return self._priority

    @priority.setter
    @slow_group_lock_context.object_session_entry_point
    def priority(self, p: float):
        self.metadata_already_pushed_by = {}
        self._priority = p
        with self.lock:
            self.lighting_manager.refresh()

        core.serialized_async_with_core_lock(
            self.board.cl_update_group_priorities
        )

    def mqttStatusEvent(self, value: str, timestamp: float, annotation: Any):
        if value == "connected":
            self.event("board.mqtt.connect")
        else:
            self.event("board.mqtt.disconnect")

        self.pushMeta(statusOnly=True)

    @slow_group_lock_context.object_session_entry_point
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
                if self.active:
                    self.mqttConnection = makeWrappedConnectionClass(self)(
                        server,
                        port,
                    )

                    self.mqttSubscribed = {}
                # Do after so we can get the err on bad format first
                self.mqtt_server = self.activeMqttServer = mqtt_server
            else:
                self.mqttConnection = None
                self.mqttSubscribed = {}
                # Do after so we can get the err on bad format first
                self.mqtt_server = self.activeMqttServer = mqtt_server

            self.doMqttSubscriptions()

    @slow_group_lock_context.object_session_entry_point
    def setName(self, name: str):
        """May not take effect instantly"""
        disallow_special(name)
        if self.name == "":
            raise ValueError("Cannot name group an empty string")
        if not isinstance(name, str):
            raise TypeError("Name must be str")

        if name in self.board.groups_by_name:
            raise ValueError("Name in use")

        with self.lock:
            self.script_context.setVar("GROUP", self.name)

        def f():
            if name in self.board.groups_by_name:
                raise ValueError("Name in use")
            if self.name in self.board.groups_by_name:
                del self.board.groups_by_name[self.name]
            self.name = name
            self.board.groups_by_name[name] = self
            self.metadata_already_pushed_by = {}

        core.serialized_async_with_core_lock(f)

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
            self.poll_again_flag = True
            self.lighting_manager.rerender()

        self.metadata_already_pushed_by = {}

    def setBPM(self, b):
        b = float(b)
        if self.bpm == b:
            return
        else:
            self.bpm = b
            self.poll_again_flag = True
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
        # Start again
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

    @slow_group_lock_context.object_session_entry_point
    def stop(self):
        with self.lock:
            # No need to set rerender
            if self.script_context:
                self.script_context.clearBindings()
                self.script_context.clearState()

            # Use the cue as the marker of if we actually
            # Completed the stop, not just if we logically should be stopped
            # Because we want to be able to manually retry that if we failed.
            if not self.cue:
                return

            self.metadata_already_pushed_by = {}

            self.lighting_manager.stop()

            self.active = False

            self.media_player.stop()
            self.runningTimers.clear()

            try:
                for board in core.iter_boards():
                    board.linkSend(["grouptimers", self.id, self.runningTimers])
            except Exception:
                core.rl_log_exc("Error handling timer set notification")
                print(traceback.format_exc())

            def f():
                self.board.cl_rm_from_active_groups(self)

            core.serialized_async_with_core_lock(f)

            # fALLBACK
            self.cue = self.cues.get("default", list(self.cues.values())[0])
            # the real thing that means we aren't really in a cue
            self.entered_cue = 0
            self.cueTagClaim.set("__stopped__", annotation="GroupObject")
            self.doMqttSubscriptions(keepUnused=0)

            self.media_link.stop()

            gc.collect()
            time.sleep(0.002)
            gc.collect()
            time.sleep(0.002)
            gc.collect()

    @slow_group_lock_context.object_session_entry_point
    def refresh_lighting(self):
        with self.lock:
            if self.active:
                self.lighting_manager.refresh()

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
                "/midi/" + normalize_midi_name(s),
                self.onMidiMessage,
            )
        else:
            kaithem.message.subscribe(
                "/midi/" + normalize_midi_name(s),
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
        self.media_link.sendVisualizations()
        self.pushMeta(keys={"music_visualizations"})

    def setAlpha(self, val: float, sd: bool = False):
        val = min(1, max(0, val))
        try:
            self.cueVolume = min(
                5, max(0, float(self.evalExpr(self.cue.sound_volume)))
            )
        except Exception:
            self.event(
                "script.error",
                self.name + " in cueVolume eval:\n" + traceback.format_exc(),
            )
            self.cueVolume = 1

        kaithem.sound.setvol(val * self.cueVolume, str(self.id))

        if not self.is_active() and val > 0:
            self.go()
        self.alpha = val
        self.alphaTagClaim.set(val, annotation="GroupObject")
        if sd:
            self.default_alpha = val
            self.pushMeta(keys={"alpha", "default_alpha"})
        else:
            self.pushMeta(keys={"alpha", "default_alpha"})
        self.poll_again_flag = True
        self.lighting_manager.rerender()

        self.media_link_socket.send(["volume", val])

    def add_cue(self, name: str, **kw: Any):
        return Cue(self, name, **kw)

    def setBlend(self, blend: str):
        disallow_special(blend)
        blend = str(blend)[:256]
        self.blend = blend
        self.lighting_manager.setBlend(blend)
        self.poll_again_flag = True
        self.metadata_already_pushed_by = {}

    def setBlendArg(self, key: str, val: float | bool | str):
        disallow_special(key, "_")
        # serializableness check
        json.dumps(val)
        self.lighting_manager.setBlendArg(key, val)

        if val is None:
            del self.blend_args[key]
        else:
            try:
                val = float(val)
            except Exception:
                pass
            self.blend_args[key] = val

        self.poll_again_flag = True
        self.metadata_already_pushed_by = {}

    def poll(self, force_repaint: bool = False):
        """
        Periodically called if poll_again_flag is set
        Handles misc tasks.
        Calculate the current alpha value, handle stopping the cue and going to the next one
        """

        # We don't use the slow group lock context in this function
        # For performance, but lets still do a basic check.
        # If core.cl_context is active then the group lock comes after,
        # if the group lock context is active then core lock context
        # Can handle avoiding opening after.
        # I think these two check handle all the cases without having to use a wrapper.
        assert core.cl_context.active or slow_group_lock_context.active

        with self.lock:
            if not self.active:
                return

            assert self.cue

            if self.cue.fade_in:
                fadePosition: float = min(
                    (time.time() - self.entered_cue)
                    / (self.cue.fade_in * (60.0 / self.bpm)),
                    1.0,
                )
                fadePosition = ease(fadePosition)

                if fadePosition < 1:
                    self.poll_again_flag = True
                    self.lighting_manager.rerender()

            else:
                fadePosition = 1

            # Remember, we can and do the next cue thing and still need to repaint, because sometimes the next cue thing does nothing
            if force_repaint or (not self.lighting_manager.fade_in_completed):
                self.lighting_manager.paint_canvas(fadePosition)
                if fadePosition >= 1.0:
                    self.lighting_manager.fade_complete()

            if self.active and self.cue_time_finished():
                self.next_cue(
                    round(self.entered_cue + self.cuelen * (60 / self.bpm), 3),
                    cause="time",
                )

    def cue_time_finished(self):
        if self.cuelen and (time.time() - self.entered_cue) > self.cuelen * (
            60 / self.bpm
        ):
            return True

    @slow_group_lock_context.object_session_entry_point
    def set_cue_value(
        self,
        cue_name: str,
        universe: str,
        channel: str | int,
        value: str | int | float | None,
    ):
        with self.lock:
            reset = False

            # Allow [] for range effects
            disallow_special(universe, allow="_@./[]")

            cue = self.cues[cue_name]

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
                        "Channel name cannot begin or end with whitespace"
                    )

                # If it looks like an int, cast it even if it's a string,
                # We get a lot of raw user input that looks like that.
                try:
                    channel = int(channel)
                except ValueError:
                    pass

            reset = cue.set_value(universe, channel, value)

            unmappeduniverse = universe

            mapped_channel = mapChannel(universe, channel)

            if self.cue == cue and self.is_active():
                self.poll_again_flag = True
                self.lighting_manager.rerender()

                # If we change something in a pattern effect we just do a full recalc since those are complicated.
                if (
                    unmappeduniverse in cue.values
                    and "__length__" in cue.values[unmappeduniverse]
                ):
                    self.lighting_manager.update_state_from_cue_vals(cue, False)

                    # The FadeCanvas needs to know about this change
                    self.poll(force_repaint=True)

                # Otherwise if we are changing a simple mapped channel we optimize
                elif mapped_channel:
                    universe, channel = mapped_channel[0], mapped_channel[1]

                    uobj = None

                    if universe.startswith("/"):
                        uobj = get_on_demand_universe(universe)
                        self.lighting_manager.on_demand_universes[universe] = (
                            uobj
                        )

                    if (
                        universe not in self.lighting_manager.state_alphas
                    ) and value is not None:
                        # GetUniverse might not actually be working yet because
                        # It takes up to a frame for things to be added
                        if not uobj:
                            uobj = getUniverse(universe)
                        reset = True
                        if uobj:
                            self.lighting_manager.state_vals[universe] = (
                                numpy.array(
                                    [0.0] * len(uobj.values), dtype="f4"
                                )
                            )
                            self.lighting_manager.state_alphas[universe] = (
                                numpy.array(
                                    [0.0] * len(uobj.values), dtype="f4"
                                )
                            )

                    if universe in self.lighting_manager.state_alphas:
                        if (
                            channel
                            not in self.lighting_manager.state_alphas[universe]
                        ):
                            reset = True
                        self.lighting_manager.state_alphas[universe][
                            channel
                        ] = 1 if value is not None else 0
                        self.lighting_manager.state_vals[universe][channel] = (
                            self.evalExpr(value if value is not None else 0)
                        )

                    # The FadeCanvas needs to know about this change
                    self.poll(force_repaint=True)

                self.poll_again_flag = True
                self.lighting_manager.rerender()

                # For blend modes that don't like it when you
                # change the list of values without resetting
                if reset:
                    self.setBlend(self.blend)
