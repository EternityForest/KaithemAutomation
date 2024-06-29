"""
This is largely a data class and indexing for Cue objects.
Cues always belongs to groups, they are very much tightly coupled.
Be aware of the circular import with groups.py

The class loads its __slots__ from a schema at runtime.

"""

from __future__ import annotations

import copy
import json
import logging
import random
import traceback
import uuid
import weakref
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable

import numpy
from beartype import beartype
from scullery import workers

from .. import schemas
from . import core
from .core import disallow_special
from .global_actions import normalize_shortcut, shortcut_codes
from .universes import get_on_demand_universe, getUniverse, mapChannel

if TYPE_CHECKING:
    from .groups import Group


cues: weakref.WeakValueDictionary[str, Cue] = weakref.WeakValueDictionary()

# All the properties that can be saved and loaded are actually defined in the schema,
cue_schema = schemas.get_schema("chandler/cue")

stored_as_property = ["markdown"]

slots = list(cue_schema["properties"].keys()) + [
    "id",
    "changed",
    "next_ll",
    "name",
    "group",
    "inherit",
    "onEnter",
    "onExit",
    "__weakref__",
]
s2 = []
for i in slots:
    if i not in stored_as_property:
        s2.append(i)
    else:
        s2.append("_" + i)
slots = s2


allowedCueNameSpecials = "_~."


def number_to_shortcut(number: int | float | str):
    s = str((Decimal(number) / 1000).quantize(Decimal("0.001")))
    # https://stackoverflow.com/questions/11227620/drop-trailing-zeros-from-decimal
    s = s.rstrip("0").rstrip(".") if "." in s else s
    return s


def fnToCueName(fn: str):
    """
    Convert the given file name to a cue name that is more human-readable
     And suitable for use as a cue name
    Takes a string `fn` as input and returns a processed cue name string.
    """
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


class Cue:
    "A static set of values with a fade in and out duration"

    __slots__ = slots

    def __init__(
        self,
        parent: Group,
        name: str,
        number: int | None = None,
        forceAdd: bool = False,
        shortcut: str = "",
        id: str | None = None,
        onEnter: Callable[..., Any] | None = None,
        onExit: Callable[..., Any] | None = None,
        **kw: Any,
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
        self.sound_start_position: str | int | float
        self.media_speed: str
        self.media_wind_up: str
        self.media_wind_down: str
        self.probability: float | str
        self.values: dict[str, dict[str | int, str | int | float | None]]
        self.checkpoint: bool
        self.label_image: str

        self._markdown: str = kw.get("markdown", "").strip()

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
        for i in cue_schema["properties"]:
            # number is special because of auto increment
            if not i == "number":
                if i in kw:
                    setattr(self, i, kw[i])
                else:
                    setattr(self, i, copy.deepcopy(cue_schema["properties"][i]["default"]))

        for i in kw:
            if i not in cue_schema["properties"]:
                logging.error("Unknown cue data key " + str(i) + " loading anyway but data may be lost")

        self.rules = self.validate_rules(self.rules)

        # Now unused
        # self.script = script
        self.onEnter = onEnter
        self.onExit = onExit

        cues[self.id] = self

        self.next_ll: Cue | None = None
        parent._add_cue(self, forceAdd=forceAdd)

        self.group: weakref.ref[Group] = weakref.ref(parent)
        self.setShortcut(shortcut, False)

        self.push()

    def serialize(self):
        x2 = {}
        # The schema decides what properties we save
        for i in schemas.get_schema("chandler/cue")["properties"]:
            x2[i] = getattr(self, i)

        schemas.supress_defaults("chandler/cue", x2)

        return x2

    def getGroup(self):
        s = self.group()
        if not s:
            raise RuntimeError("Group must have been deleted")
        return s

    def push(self):
        core.add_data_pusher_to_all_boards(lambda s: s.pushCueMeta(self.id))

    def pushData(self):
        core.add_data_pusher_to_all_boards(lambda s: s.pushCueData(self.id))

    def pushoneval(self, u: str, ch: str | int, v: str | float | int | None):
        core.add_data_pusher_to_all_boards(lambda s: s.linkSend(["scv", self.id, u, ch, v]))

    def clone(self, name: str):
        if name in self.getGroup().cues:
            raise RuntimeError("Cannot duplicate cue names in one group")

        c = Cue(
            self.getGroup(),
            name,
            fade_in=self.fade_in,
            length=self.length,
            length_randomize=self.length_randomize,
            values=copy.deepcopy(self.values),
            next_cue=self.next_cue,
            rel_length=self.rel_length,
            track=self.track,
        )

        core.add_data_pusher_to_all_boards(lambda s: s.pushCueMeta(c.id))
        core.add_data_pusher_to_all_boards(lambda s: s.pushCueData(c.id))

    def setTrack(self, val):
        self.track = bool(val)
        self.getGroup().poll_again_flag = True

        def f():
            with self.getGroup().lock:
                self.getGroup().lighting_manager.refresh()

        workers.do(f)

    def setNumber(self, n):
        "Can take a string representing a decimal number for best accuracy, saves as *1000 fixed point"
        if self.shortcut == number_to_shortcut(self.number):
            self.setShortcut(number_to_shortcut(int((Decimal(n) * Decimal(1000)).quantize(1))))
        self.number = int((Decimal(n) * Decimal(1000)).quantize(1))

        # re-sort the cuelist
        self.getGroup().insertSorted(None)

        self.push()

    @property
    def markdown(self):
        return self._markdown

    @markdown.setter
    def markdown(self, s: str):
        s = s.strip().replace("\r", "")
        if not s == self._markdown:
            self._markdown = s
            self.push()
            group = self.group()
            if group:
                group.media_link_socket.send(
                    [
                        "text",
                        self._markdown,
                    ]
                )

    def validate_rules(self, r: list[list[str | list[list[str]]]]):
        r = r or []
        s = json.dumps(r, ensure_ascii=False)
        # Legacy name fix
        s = s.replace('"=SCENE"', '"=GROUP"')
        return json.loads(s)

    def setRules(self, r: list[list[str | list[list[str]]]]):
        r = self.validate_rules(r)
        self.rules = r or []
        self.getGroup().refresh_rules()

    def setInheritRules(self, r):
        self.inherit_rules = r
        self.getGroup().refresh_rules()

    def setShortcut(self, code: str, push: bool = True):
        code = normalize_shortcut(code)

        disallow_special(code, allow="._")

        if code == "__generate__from__number__":
            code = number_to_shortcut(self.number)

        def f():
            if self.shortcut in shortcut_codes:
                try:
                    shortcut_codes[self.shortcut].remove(self)
                except ValueError:
                    pass
                except Exception:
                    print(traceback.format_exc())

            if random.random() < 1:
                # Do a full GC pass of the shortcut codes list
                to_rm = []
                for i in shortcut_codes:
                    if not shortcut_codes[i]:
                        to_rm.append(i)
                    else:
                        for j in list(shortcut_codes[i]):
                            if not j.group():
                                shortcut_codes[i].remove(j)
                for i in to_rm:
                    del shortcut_codes[i]

            if code:
                if code in shortcut_codes:
                    shortcut_codes[code].append(self)
                else:
                    shortcut_codes[code] = [self]

        core.serialized_async_with_core_lock(f)

        self.shortcut = code
        if push:
            self.push()

    @beartype
    def set_value(self, universe: str, channel: str | int, value: str | int | float | None):
        # Allow [] for range effects
        disallow_special(universe, allow="_@./[]")

        group = self.getGroup()

        if not group:
            raise RuntimeError("The group doesn't exist")
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
                raise Exception("Channel name cannot begin or end with whitespace")

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

        with self.getGroup().lock:
            reset = False
            if value is not None:
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

            mapped_channel = mapChannel(universe, channel)

            if group.cue == self and group.is_active():
                group.poll_again_flag = True
                group.lighting_manager.rerender()

                # If we change something in a pattern effect we just do a full recalc since those are complicated.
                if unmappeduniverse in self.values and "__length__" in self.values[unmappeduniverse]:
                    group.lighting_manager.update_state_from_cue_vals(self, False)

                    # The FadeCanvas needs to know about this change
                    group.poll(force_repaint=True)

                # Otherwise if we are changing a simple mapped channel we optimize
                elif mapped_channel:
                    universe, channel = mapped_channel[0], mapped_channel[1]

                    uobj = None

                    if universe.startswith("/"):
                        uobj = get_on_demand_universe(universe)
                        group.lighting_manager.on_demand_universes[universe] = uobj

                    if (universe not in group.lighting_manager.state_alphas) and value is not None:
                        uobj = getUniverse(universe)
                        if uobj:
                            group.lighting_manager.state_vals[universe] = numpy.array([0.0] * len(uobj.values), dtype="f4")
                            group.lighting_manager.state_alphas[universe] = numpy.array([0.0] * len(uobj.values), dtype="f4")
                    if universe in group.lighting_manager.state_alphas:
                        group.lighting_manager.state_alphas[universe][channel] = 1 if value is not None else 0
                        group.lighting_manager.state_vals[universe][channel] = group.evalExpr(value if value is not None else 0)

                    # The FadeCanvas needs to know about this change
                    group.poll(force_repaint=True)

            group.poll_again_flag = True
            group.lighting_manager.rerender()

            # For blend modes that don't like it when you
            # change the list of values without resetting
            if reset:
                group.setBlend(group.blend)
