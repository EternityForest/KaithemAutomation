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

from beartype import beartype
from scullery import snake_compat

from .. import schemas
from ..kaithemobj import kaithem
from . import core
from .core import disallow_special
from .global_actions import normalize_shortcut, shortcut_codes

if TYPE_CHECKING:
    from .groups import Group


cues: weakref.WeakValueDictionary[str, Cue] = weakref.WeakValueDictionary()

# All the properties that can be saved and loaded are actually defined in the schema,
cue_schema = schemas.get_schema("chandler/cue")

# These are in the schema but the corresponding entry on the object has
# an underscore and there's getters and setters.
stored_as_property = [
    "markdown",
    "track",
    "sound",
    "slide",
    "shortcut",
    "length_randomize",
    "rules",
    "inherit_rules",
]

slots = list(cue_schema["properties"].keys()) + [
    "id",
    "changed",
    "next_ll",
    "name",
    "group",
    "inherit",
    "onEnter",
    "onExit",
    "_provider",
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

    if fn[0] in "1234567890":
        fn = "x" + fn

    return fn


cue_provider_types: dict[str, type[CueProvider]] = {}


class CueProvider:
    def __init__(self, url: str, group: Group, *a, **k):
        self.discovered_cues: dict[str, Cue] = {}
        self.url = url
        self.group = group
        # Some subclasses may import from a dire and we also want that to
        # be a media dir
        self.dir: str = ""

    def get_dir_for_cue(self, cue: Cue) -> str | None:
        """If cue is from filesystem, return the folder it came from"""
        return None

    def save_cue(self, cue: Cue):
        # Save user changes to a cue
        raise NotImplementedError

    def scan_cues(self) -> dict[str, Cue]:
        """Given a group, return a list of the cues we
        provide to that group, indexed by ID.

        Also updates the `discovered_cues` attribute with the new cues.

        This method must not blow away user changes to cues, it must just return
        the same old cue for ones that still exists, however it can
        just not return a certain cue if it doesn't exist.
        """
        raise NotImplementedError

    def delete_saved_user_cue_data(self, cue: Cue):
        raise NotImplementedError

    def validate_property_update(self, cue: Cue, prop: str, value: Any):
        return value


def get_cue_provider(url: str, group: Group) -> CueProvider:
    scheme = url.split(":")[0]
    return cue_provider_types[scheme](url, group)


class Cue:
    "A static set of values with a fade in and out duration"

    __slots__ = slots

    def __init__(
        self,
        parent: Group,
        name: str,
        number: int | None = None,
        forceAdd: bool = False,
        id: str | None = None,
        onEnter: Callable[..., Any] | None = None,
        onExit: Callable[..., Any] | None = None,
        provider: str | None = None,
        **kw: Any,
    ):
        # declare vars.
        self.name: str
        self.number: int
        self._inherit_rules: str
        self.reentrant: bool
        self.sound_volume: float | str
        self.sound_loops: int
        self.named_for_sound: bool
        self.notes: str
        self.alpha: float
        self.fade_in: float
        self.sound_fade_out: float
        self.sound_fade_in: float
        self.length: float | str = 0
        self.rel_length: bool = False
        self._length_randomize: float
        self.next_cue: str
        self._track: bool = False
        self._shortcut: str
        self.trigger_shortcut: str
        self._sound: str = ""
        self._slide: str = ""
        self.sound_output: str
        self.sound_start_position: str | int | float
        self.media_speed: str
        self.media_wind_up: str
        self.media_wind_down: str
        self.probability: float | str
        self.values: dict[str, dict[str | int, str | int | float | None]]
        self.checkpoint: bool
        self.label_image: str
        self.metadata: dict[str, str | int | float | bool | None]

        # If a Cue Provider is specified, we do not save it to
        # The show file like normal, the provider will tell us how to save it
        self._provider: str = (provider or "").strip()

        self.group: weakref.ref[Group] = weakref.ref(parent)

        self._markdown: str = kw.get("markdown", "").strip()

        self._sound = ""
        self._rules: list[list[str | list[list[str]]]] = []

        if id:
            disallow_special(id)

        disallow_special(name, allowedCueNameSpecials)
        if name[0] in "1234567890":
            name = "x" + name

        # This is so we can loop through them and push to gui
        self.id: str = id or uuid.uuid4().hex
        self.name = name

        # Odd circular dependency
        try:
            self.number = number or parent.cues_ordered[-1].number + 5000
        except Exception:
            self.number = 5000

        # Set up all the underscore internal vals for the properties before settingthe actual
        # properties
        for i in cue_schema["properties"]:
            if i in stored_as_property:
                setattr(
                    self,
                    "_" + i,
                    copy.deepcopy(cue_schema["properties"][i]["default"]),
                )

        # Most of the data is loaded here based on what's in the schema
        for i in cue_schema["properties"]:
            # number is special because of auto increment
            if not i == "number":
                if i in kw:
                    setattr(self, i, kw[i])
                else:
                    setattr(
                        self,
                        i,
                        copy.deepcopy(cue_schema["properties"][i]["default"]),
                    )

        for i in kw:
            if i not in cue_schema["properties"]:
                logging.error(
                    "Unknown cue data key "
                    + str(i)
                    + " loading anyway but data may be lost"
                )

        self._rules = self.validate_rules(self._rules)

        # Now unused
        # self.script = script
        self.onEnter = onEnter
        self.onExit = onExit

        self.next_ll: Cue | None = None
        parent._add_cue(self, forceAdd=forceAdd)

        cues[self.id] = self
        self.push()

    @property
    def is_active(self):
        g = self.group()
        if hasattr(g, "cue"):
            if g and g.cue is self:
                return True
        return False

    @property
    def provider(self):
        return self._provider

    @provider.setter
    def provider(self, value):
        value = value or ""
        value = value.strip()
        if value not in self.getGroup().cue_providers:
            raise RuntimeError("Cue provider does not exist in parent group")
        if value and self.name == "default":
            raise RuntimeError("Cannot set a cue provider on the default cue")
        old = self._provider
        self._provider = value
        if old and old != value:
            try:
                self.getGroup().get_cue_provider(
                    old
                ).delete_saved_user_cue_data(self)
            except Exception:
                logging.exception("Failed to delete old cue data")

    def __repr__(self):
        gr = None
        if hasattr(self, "group"):
            gr = self.group()
        ac = False
        if gr:
            g = gr.name
            if hasattr(gr, "cue") and gr.cue is self:
                ac = gr.cue is self
        else:
            g = "None"
        try:
            return f"Cue({self.name}, id={self.id}, group={g}, active={ac})"
        except Exception:
            return "Cue(init not done or data corrupted)"

    def serialize(self):
        x2 = {}
        # The schema decides what properties we save
        for i in schemas.get_schema("chandler/cue")["properties"]:
            x2[i] = getattr(self, i)

        schemas.suppress_defaults("chandler/cue", x2)

        return x2

    def getGroup(self):
        s = self.group()
        if not s:
            raise RuntimeError("Group must have been deleted")
        return s

    def clone(self, name: str):
        if name in self.getGroup().cues:
            raise RuntimeError("Cannot duplicate cue names in one group")

        c = Cue(
            self.getGroup(),
            name,
            fade_in=self.fade_in,
            length=self.length,
            length_randomize=self._length_randomize,
            values=copy.deepcopy(self.values),
            next_cue=self.next_cue,
            rel_length=self.rel_length,
            track=self.track,
        )

        core.add_data_pusher_to_all_boards(lambda s: s.pushCueMeta(c.id))
        core.add_data_pusher_to_all_boards(lambda s: s.pushCueData(c.id))

    @property
    def track(self):
        return self._track

    @track.setter
    def track(self, val: bool):
        v = bool(val)
        if v == self._track:
            return
        self._track = v
        self.getGroup().poll_again_flag = True

        def f():
            with self.getGroup().lock:
                self.getGroup().lighting_manager.refresh()

        core.serialized_async_with_core_lock(f)

    def setNumber(self, n):
        "Can take a string representing a decimal number for best accuracy, saves as *1000 fixed point"
        if self.shortcut == number_to_shortcut(self.number):
            self.shortcut = number_to_shortcut(
                int((Decimal(n) * Decimal(1000)).quantize(1))
            )
        self.number = int((Decimal(n) * Decimal(1000)).quantize(1))

        # re-sort the cuelist
        self.getGroup()._nl_insert_cue_sorted(None)

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

    @property
    def rules(self) -> list[list[str | list[list[str]]]]:
        return self._rules

    @rules.setter
    def rules(self, r: list[list[str | list[list[str]]]]):
        r = self.validate_rules(r)
        self._rules = r or []
        if self.is_active:
            self.getGroup().refresh_rules()

    @property
    def inherit_rules(self) -> str:
        return self._inherit_rules

    @inherit_rules.setter
    def inherit_rules(self, r: str):
        self._inherit_rules = r
        if self.is_active:
            self.getGroup().refresh_rules()

    @property
    def length_randomize(self) -> float:
        return self._length_randomize

    @length_randomize.setter
    def length_randomize(self, val: float):
        changed = val != self._length_randomize
        self._length_randomize = float(val or 0)

        if changed and self.is_active:
            g = self.group()
            if g:
                g.recalc_randomize_modifier()
            self.push()

    @property
    def slide(self):
        return self._slide

    @slide.setter
    def slide(self, val: str):
        kaithem.assetpacks.ensure_file(val)
        g = self.getGroup()
        b = g.board

        soundfolders = core.getSoundFolders(extra_folders=b.media_folders)

        s = val
        for i in soundfolders:
            s = val
            # Make paths relative.
            if not i.endswith("/"):
                i = i + "/"
            if s.startswith(i):
                s = s[len(i) :]
                break

        self._slide = s
        self.push()

    @property
    def sound(self):
        return self._sound

    @sound.setter
    def sound(self, val: str):
        # If it's a cloud asset, get it first
        kaithem.assetpacks.ensure_file(val)

        g = self.getGroup()
        b = g.board

        soundfolders = core.getSoundFolders(extra_folders=b.media_folders)
        s = ""
        if val:
            for i in soundfolders:
                s = val
                # Make paths relative.
                if not i.endswith("/"):
                    i = i + "/"
                if s.startswith(i):
                    s = s[len(i) :]
                    break
            assert s

        if s.strip() and self.sound and self.named_for_sound:
            self.push()
            raise RuntimeError(
                """This cue was named for a specific sound file,
                forbidding change to avoid confusion.
                To override, set to no sound first"""
            )

        self._sound = s

        self.push()

    @property
    def shortcut(self):
        return self._shortcut

    @shortcut.setter
    def shortcut(self, code: str):
        code = normalize_shortcut(code)

        disallow_special(code, allow="._")

        if code == "__generate__from__number__":
            code = number_to_shortcut(self.number)

        def f():
            if self._shortcut in shortcut_codes:
                try:
                    shortcut_codes[self._shortcut].remove(self)
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

        if not code == self._shortcut:
            core.serialized_async_with_core_lock(f)
            push = True
        else:
            push = False

        self._shortcut = code
        if push:
            self.push()

    def set_value_immediate(
        self, universe: str, channel: str | int, value: str | int | float | None
    ):
        gr = self.getGroup()
        if gr:
            gr.set_cue_value(self.name, universe, channel, value)

    @beartype
    def set_value(
        self, universe: str, channel: str | int, value: str | int | float | None
    ):
        # Allow [] for range effects
        disallow_special(universe, allow="_@./[]")

        group = self.getGroup()

        if not group:
            raise RuntimeError("The group doesn't exist")

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

        return reset

    def get_ui_data(self):
        group = self.group()
        if not group:
            raise RuntimeError("Cue belongs to nonexistant group")

        # Stuff that never gets saved, it's runtime UI stuff
        d2 = {
            "id": self.id,
            "name": self.name,
            "next": self.next_cue if self.next_cue else "",
            "group": group.id,
            "number": self.number / 1000.0,
            "prev": group.getParent(self.name),
            "hasLightingData": len(self.values),
            "default_next": group.getAfter(self.name),
            "labelImageTimestamp": self.getGroup().board.get_file_timestamp_if_exists(
                self.label_image
            ),
            "provider": self.provider,
        }

        d = {}
        # All the stuff that's just a straight 1 to 1 copy of the attributes
        # are the same as whats in the save file
        for i in schemas.get_schema("chandler/cue")["properties"]:
            d[i] = getattr(self, i)

        # Important that d2 takes priority
        d.update(d2)

        # not metadata, sent separately
        d.pop("values")

        # Web frontend still uses ye olde camel case
        d = snake_compat.camelify_dict_keys(d)

        return d

    def push(self):
        # Not even set up yet don't bother
        if self.id in cues:
            core.add_data_pusher_to_all_boards(lambda s: s.pushCueMeta(self.id))

    def pushData(self):
        core.add_data_pusher_to_all_boards(lambda s: s.pushCueData(self.id))

    def pushoneval(self, u: str, ch: str | int, v: str | float | int | None):
        core.add_data_pusher_to_all_boards(
            lambda s: s.linkSend(["scv", self.id, u, ch, v])
        )
