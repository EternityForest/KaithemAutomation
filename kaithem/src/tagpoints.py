# SPDX-FileCopyrightText: Copyright Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import copy
import functools
import json
import math
import random
import re
import threading
import time
import traceback
import types
import typing
import weakref
from collections.abc import Callable
from typing import (
    Any,
    Generic,
    TypeVar,
    final,
)

import beartype
import dateutil
import dateutil.parser
import structlog
from scullery import scheduling

from . import alerts, messagebus, pages, widgets, workers
from .unitsofmeasure import convert, unit_types

logger = structlog.get_logger(__name__)
# _ and . allowed
ILLEGAL_NAME_CHARS = "{}|\\<>,?-=+)(*&^%$#@!~`\n\r\t\0"


def replace_illegal_chars(name):
    for i in ILLEGAL_NAME_CHARS:
        name = name.replace(i, "")
    return name


def to_sk(s: str):
    s2 = ""
    last = "a"
    for i in s:
        if last.isalpha() and not last.isupper():
            if i.isupper():
                s2 += "_" + i.lower()
                continue
        s2 += i
    return s2


def _make_tag_info_helper(t: GenericTagPointClass[Any]):
    def f():
        x = t.current_source
        if x == "default":
            return ""
        else:
            return f"({x})"

    return f


def get_tag_meta(t):
    r = {}
    t = allTagsAtomic[t]()
    assert t

    try:
        pages.require(t.get_effective_permissions()[0])
    except PermissionError:
        return pages.loginredirect(pages.geturl())
    if not t:
        raise RuntimeError("Tag not found")

    if pages.canUserDoThis(t.get_effective_permissions()[1]):
        r["writePermission"] = True
    else:
        r["writePermission"] = False

    if not t.writable:
        r["writePermission"] = False

    if isinstance(t, NumericTagPointClass):
        r["min"] = t.min
        r["max"] = t.max
        r["high"] = t.hi
        r["low"] = t.lo
        r["unit"] = t.unit

        r["lastVal"] = t.value

    elif t.type == "string":
        r["lastVal"] = t.value
    elif t.type == "object":
        r["lastVal"] = t.value

    r["type"] = t.type
    r["subtype"] = t.subtype

    return r


# For the tag numbering feature.
# Maps assigned numbers to names,
# only for tags where someone has requested a number.
assigned_unique_numbers: dict[int, str] = {}

logger = structlog.get_logger(__name__)

exposedTags: weakref.WeakValueDictionary[str, GenericTagPointClass[Any]] = (
    weakref.WeakValueDictionary()
)

# This is used for messing with the set of tags.
# We just accept that creating and deleting tags and claims is slow.
lock = threading.RLock()

allTags: dict[str, weakref.ref[GenericTagPointClass[Any]]] = {}
allTagsAtomic: dict[str, weakref.ref[GenericTagPointClass[Any]]] = {}

subscriber_error_handlers: list[Callable[..., Any]] = []


_default_display_units = {
    "temperature": "degC|degF",
    "length": "m",
    "weight": "g",
    "pressure": "psi|Pa",
    "voltage": "V",
    "current": "A",
    "power": "W",
    "frequency": "Hz",
    "ratio": "%",
    "speed": "KPH|MPH",
}


class _Alert(alerts.Alert):
    def __init__(
        self,
        name: str,
        priority: str = "info",
        zone: str | None = None,
        trip_delay: int | float = 0,
        auto_ack: bool | float | int = False,
        permissions: list[str] = [],
        ackPermissions: list[str] = [],
        id: str | None = None,
        description: str = "",
        silent: bool = False,
    ):
        self.source_tags: dict[str, weakref.ref[GenericTagPointClass[Any]]] = {}
        self.recalcFunction: Callable[[Any, float, Any], Any]
        self.notificationHTML: Callable[[], str]

        # Eval context of the alarm expression
        self.context: dict[str, Any] = {}

        super().__init__(
            name,
            priority,
            zone,
            trip_delay,
            auto_ack,
            permissions,
            ackPermissions,
            id,
            description,
            silent,
        )


@functools.lru_cache(4096, False)
def normalize_tag_name(name: str, replacementChar: str | None = None) -> str:
    "Normalize hte name, and raise errors on anything just plain invalid, unless a replacement char is supplied"
    name = name.strip()
    if name == "":
        raise ValueError("Tag with empty name")

    if name[0] in "0123456789":
        raise ValueError("Begins with number")

    # Special case, these tags are expression tags.
    if not name.startswith("="):
        name = re.sub(r"\[(.*)\]", lambda x: f".{x.groups(1)[0]}", name)
        for i in ILLEGAL_NAME_CHARS:
            if i in name:
                if replacementChar:
                    name = name.replace(i, replacementChar)
                else:
                    raise ValueError(
                        f"Illegal char in tag point name: {i} in {name}"
                    )
        if not name.startswith("/"):
            name = f"/{name}"
        name = to_sk(name).replace("-", "_")
    else:
        if name.startswith("/="):
            name = name[1:]

    return name


T = TypeVar("T")


class GenericTagPointClass(Generic[T]):
    """
    A Tag Point is a named object that can be chooses from a set of data sources based on priority,
    filters that data, and returns it on a push or a pull basis.

    A data source here is called a "Claim", and can either be a number or a function. The highest
    priority claim is called the active claim.

    If the claim is a function, it will be called at most once per interval, which is set by tag.interval=N
    in seconds. However the filter function is called every time the data is requested.

    If there are any subscribed functions to the tag, they will automatically be called at the tag's interval,
    with the one parameter being the tag's value. Any getter functions will be called to get the value.


    One generally does not instantiate a tag this way, instead they use the Tag function
    which can get existing tags. This allows use of tags for cross=

    """

    # Random opaque indicator
    DEFAULT_ANNOTATION = "1d289116-b250-482e-a3d3-ffd9e8ac2b57"

    default_data: T
    type = "object"
    mqtt_encoding = "json"

    def __repr__(self):
        try:
            return f"<Tag Point: {self.name}={str(self._value)[:20]}>"
        except Exception:
            return f"<Tag Point: {self.name}>"

    @beartype.beartype
    def __init__(self, name: str):
        global allTagsAtomic
        _name: str = normalize_tag_name(name)
        if _name in allTags:
            raise RuntimeError(
                "Tag with this name already exists, use the getter function to get it instead"
            )

        # Used to store loggers sey elsewhere.
        self.configLoggers: weakref.WeakValueDictionary[str, object] = (
            weakref.WeakValueDictionary()
        )

        # Used for the fake buttons in the device page
        self._k_ui_fake: Claim[T]

        self.aliases: set[str] = set()

        # Where we store a ref for the widget
        self._gui_updateSubscriber: Callable[[T, float, Any], Any]

        # Dependency tracking, if a tag depends on other tags, such as =expression based ones
        self.source_tags: dict[str, GenericTagPointClass[Any]] = {}

        self._value: Callable[[], T | None] | T

        self._default: T

        self.data_source_widget: widgets.Widget | None = None

        # Used for pushing data to frontend
        self._data_source_ws_lock: threading.Lock

        self.description: str = ""
        # True if there is already a copy of the deadlock diagnostics running
        self._testingForDeadlock: bool = False

        self._alreadyPostedDeadlock: bool = False

        # This string is just used to stash some extra info
        self._subtype: str = ""

        self.unique_int = 0

        # Start timestamp at 0 meaning never been set
        # Value, timestamp, annotation.  This is the raw value,
        # and the value could actually be a callable returning a value
        self.vta: tuple[T | Callable[[], T | None], float, Any] = (
            copy.deepcopy(self.default_data),
            0,
            None,
        )

        self.alarms: dict[str, _Alert] = {}

        # Used to optionally record a list of allowed values
        self._enum: list[Any] | None = None

        # In unreliable mode the tag's acts like a simple UDP connection.
        # The only supported feature is that writing the tag notifies subscribers.
        # It is not guaranteed to store the last value, to error check the value,
        # To prevent multiple writes at the same time, and the claims may be ignored.

        # Subscribing the tag directly to another tga uses fast_push that bypasses all claims.
        # In unreliable mode you should only use fast_push to set values.

        self.unreliable: bool = False

        # Track the recalc function used by the poller, the poller itself, and the recalc alarm subscribe
        # function subscribed to us, respectively

        # The last is a function that is used as a subscriber which just causes the tag to be recalced.
        # We give that to other tags in case the alarm polling depends on other tags.

        # We need it so we don't get GCed
        self._alarmGCRefs: dict[
            str,
            tuple[
                Callable[[], Any],
                scheduling.RepeatingEvent,
                Callable[..., Any],
                Callable[..., Any],
            ],
        ] = {}

        self.name: str = _name
        # The cached actual value from the claims
        self._cachedRawClaimVal: T = copy.deepcopy(self.default_data)
        # The cached output of processValue
        self.last_value: T = self._cachedRawClaimVal
        # The real current in use val, after the config override logic
        self._interval: float | int = 0
        self.active_claim: None | Claim[T] = None
        self.claims: dict[str, Claim[T]] = {}
        self.lock = threading.RLock()
        self.subscribers: list[weakref.ref[Callable[..., Any]]] = []

        # This is only used for fast stream mode
        self.subscribers_atomic: list[weakref.ref[Callable[..., Any]]] = []

        self._poller: scheduling.RepeatingEvent | None = None

        # The "Owner" of a tag can use this to say if anyone else should write it
        self.writable = True

        # When was the last time we got *real* new data
        self.last_got_value: int | float = 0

        self.lastError: float | int = 0

        # String describing the "owner" of the tag point
        # This is not a precisely defined concept
        self.owner: str = ""

        self.handler: typing.Callable[..., Any] | None = None

        # Used for the expressions in alert conditions and such
        self.eval_context: dict[str, Any] = {
            "math": math,
            "time": time,
            # Cannot reference ourself strongly.  We want to avoid laking any references to tht tags
            # go away cleanly
            "tag": weakref.proxy(self),
            "re": re,
            "random": random,
            # It is perfect;y fine that these reference ourself, because when we pass this to an alarm,
            # We have alarm specific ones.
            "tv": self._context_get_numeric_tag_value,
            "stv": self._context_get_string_tag_value,
            "dateutil": dateutil,
        }
        try:
            import numpy as np

            self.eval_context["np"] = np
        except ImportError:
            pass

        self.lastPushedValue: T | None = None
        self.onSourceChanged: typing.Callable[..., Any] | None = None

        with lock:
            allTags[_name] = weakref.ref(self)
            allTagsAtomic = allTags.copy()

        # This pushes a value. That is fine because we know there are no listeners
        self.defaultClaim = self.claim(
            copy.deepcopy(self.default_data),
            "default",
            timestamp=0,
            annotation=self.DEFAULT_ANNOTATION,
        )

        # Reset this so that any future value sets actually do push.  First write should always push
        # Independent of change detection.
        self.lastPushedValue = None

        # What permissions are needed to
        # read or override this tag, as a tuple of 2 permission strings and an int representing the priority
        # that api clients can use.
        # As always, configured takes priority
        self.permissions = ("", "", 50)

        self.apiClaim: None | Claim[T] = None

        # This is where we can put a manual override
        # claim from the web UI.
        self.manualOverrideClaim: None | Claim[T] = None

        with lock:
            messagebus.post_message(
                "/system/tags/created", self.name, synchronous=True
            )

        if self.name.startswith("="):
            self.exprClaim = self.createGetterFromExpression(self.name)
            self.writable = False

    def get_unique_number(self):
        """Return a number uniquely representing this tag.
        It will
        """
        with lock:
            if self.unique_int:
                return self.unique_int
            else:
                for i in range(1000000):
                    if i not in assigned_unique_numbers:
                        assigned_unique_numbers[i] = self.name
                        self.unique_int = i
                        break
                    elif assigned_unique_numbers[i] == self.name:
                        self.unique_int = i
                        break

                return self.unique_int

    # In reality value, timestamp, annotation are all stored together as a tuple

    @property
    def timestamp(self) -> float:
        return self.vta[1]

    @property
    def annotation(self) -> Any:
        return self.vta[2]

    def isDynamic(self) -> bool:
        return callable(self.vta[0])

    @beartype.beartype
    def expose(
        self,
        read_perms: str | list[str] = "",
        write_perms: str | list[str] = "system_admin",
        expose_priority: str | int | float = 50,
    ):
        """If not r, disable web API.  Otherwise, set read and write permissions."""

        if isinstance(read_perms, list):
            read_perms = ",".join(read_perms)
        else:
            read_perms = read_perms.strip()
        if isinstance(write_perms, list):
            write_perms = ",".join(write_perms)
            write_perms = write_perms.strip()

        # Handle different falsy things someone might use to try and disable this
        if not read_perms:
            read_perms = ""
        if not write_perms:
            write_perms = "system_admin"

        # Just don't allow numberlike permissions so we can keep
        # pretending any config item that looks like a number, is.
        # Also, why would anyone do that?
        for i in read_perms.split(",") + write_perms.split(","):
            try:
                float(i)
                raise RuntimeError(f"Permission: {str(i)} looks like a number")
            except ValueError:
                pass

        if not expose_priority:
            expose_priority = 50
        # Make set we don't somehow save bad data and break everything
        expose_priority = float(expose_priority)
        write_perms = str(write_perms)
        read_perms = str(read_perms)

        if not read_perms or not write_perms:
            d = ["", "", 50]
        else:
            d = [read_perms, write_perms, expose_priority]

        with lock:
            with self.lock:
                self.permissions = tuple(d)

                d2 = self.get_effective_permissions()
                if d2[2]:
                    expose_priority = float(d2[2])

                perms_list = list(d2)

                assert isinstance(perms_list[0], str)
                assert isinstance(perms_list[1], str)

                # Be safe, only allow writes if user specifies a permission
                perms_list[1] = perms_list[1] or "system_admin"

                if not perms_list[0]:
                    self.data_source_widget = None
                    try:
                        del exposedTags[self.name]
                    except KeyError:
                        pass
                    if self.apiClaim:
                        self.apiClaim.release()
                else:
                    w = widgets.DataSource(id=f"tag:{self.name}")

                    if self.unreliable:
                        w.noOnConnectData = True

                    w.set_permissions(
                        [i.strip() for i in perms_list[0].split(",")],
                        [i.strip() for i in perms_list[1].split(",")],
                    )

                    w.value = self.value

                    exposedTags[self.name] = self
                    if self.apiClaim:
                        self.apiClaim.setPriority(expose_priority)
                    self._apiPush()

                    # We don't want the web connection to be able to keep the tag alive
                    # so don't give it a reference to us
                    self._weakApiHandler: Callable[[str, T | None], None] = (
                        self.makeWeakApiHandler(weakref.ref(self))
                    )
                    w.attach(self._weakApiHandler)

                    self.data_source_widget = w

    @staticmethod
    def makeWeakApiHandler(wr) -> Callable[[str, T | None], None]:
        def f(u: str, v: T | None):
            wr().apiHandler(u, v)

        return f

    def apiHandler(self, u, v: T | None):
        if v is None:
            if self.apiClaim:
                self.apiClaim.release()
        else:
            # No locking things up if the times are way mismatched and it sets a time way in the future
            self.apiClaim = self.claim(
                v,
                "WebAPIClaim",
                priority=float(self.get_effective_permissions()[2]),
                annotation=u,
            )

            # They tried to set the value but could not, so inform them of such.
            if not self.current_source == self.apiClaim.name:
                self._apiPush()

    def get_effective_permissions(self) -> tuple[str, str, float]:
        """
        Get the permissions that currently apply here. Configured ones override in-code ones

        Returns:
            list: [read_perms, write_perms, writePriority]. Priority determines the priority of web API claims.
        """
        d2 = (
            str(self.permissions[0]),
            str(self.permissions[1]),
            float(self.permissions[2]),
        )

        # Block exposure at all if the permission is never
        if "__never__" in self.permissions[0]:
            return ("", "", 0.0)

        return d2

    def _apiPush(self):
        "If the expose function was used, push this to the data_source_widget"
        if not self.data_source_widget:
            return

        # Immediate write, don't push yet, do that in a thread because TCP can block
        def pushFunction():
            # Set value immediately, for later page loads
            assert self.data_source_widget
            self.data_source_widget.value = self.value
            if self._data_source_ws_lock.acquire(timeout=1):
                try:
                    # Use the new literal computed value, not what we were passed,
                    # Because it could have changed by the time we actually get to push
                    self.data_source_widget.send(self.value)
                finally:
                    self._data_source_ws_lock.release()

        # Should there already be a function queued for this exact reason, we just let
        # That one do it's job
        if self._data_source_ws_lock.acquire(timeout=0.001):
            try:
                workers.do(pushFunction)
            finally:
                self._data_source_ws_lock.release()

    def testForDeadlock(self):
        "Run a check in the background to make sure this lock isn't clogged up"

        def f():
            # Approx check, more than one isn't the worst thing
            if self._testingForDeadlock:
                return

            self._testingForDeadlock = True

            if self.lock.acquire(timeout=30):
                self.lock.release()
            else:
                if not self._alreadyPostedDeadlock:
                    messagebus.post_message(
                        "/system/notifications/errors",
                        "Tag point: "
                        + self.name
                        + " has been unavailable for 30s and may be involved in a deadlock. see threads view.",
                    )
                    self._alreadyPostedDeadlock = True

            self._testingForDeadlock = False

        workers.do(f)

    def recalc(self, *a: Any, **k: Any):
        "Just re-get the value as needed"
        # It's a getter, ignore the mypy unused thing.
        self.poll()

    def _context_get_numeric_tag_value(self, n: str) -> float:
        "Get the tag value, adding it to the list of source tags. Creates tag if it isn't there"
        try:
            return self.source_tags[n].value
        except KeyError:
            self.source_tags[n] = Tag(n)
            # When any source tag updates, we want to recalculate.
            self.source_tags[n].subscribe(self.recalc)
            return self.source_tags[n].value
        return 0

    def _context_get_string_tag_value(self, n: str) -> str:
        "Get the tag value, adding it to the list of source tags. Creates tag if it isn't there"
        try:
            return self.source_tags[n].value
        except KeyError:
            self.source_tags[n] = StringTag(n)
            # When any source tag updates, we want to recalculate.
            self.source_tags[n].subscribe(self.recalc)
            return self.source_tags[n].value
        return 0

    # Note the black default condition, that lets us override a normal alarm while using the default condition.
    @beartype.beartype
    def set_alarm(
        self,
        name: str,
        condition: str | None = "",
        priority: str = "info",
        release_condition: str | None = "",
        auto_ack: bool | str = "no",
        trip_delay: float | int | str = "0",
    ) -> _Alert | None:
        with lock:
            if not name:
                raise RuntimeError("Empty string name")

            if auto_ack is True:
                auto_ack = "yes"
            if auto_ack is False:
                auto_ack = "no"

            trip_delay = str(trip_delay)

            d: dict[str, str | int | bool | float | None] = {
                "condition": condition,
                "priority": priority,
                "auto_ack": auto_ack,
                "trip_delay": trip_delay,
                "release_condition": release_condition,
            }

            # Remove empties to make way for defaults
            d = {i: d[i] for i in d if d[i]}

            self._alarm_from_data(name, d)

            if name in self.alarms:
                x = self.alarms[name]
                # Alarms have to have a reference to the config data
                x.tagpoint_config_data = d
                x.tagpoint_name = self.name
                return x
        return None

    @staticmethod
    def _makeTagAlarmHTMLFunc(selfwr: weakref.ref[GenericTagPointClass[T]]):
        def notificationHTML():
            s = selfwr()
            assert s
            try:
                if s.type in ("number", "string"):
                    return f'<ds-span source="tag:{s.name}"></ds-span>'
                else:
                    return "Binary or obj Tagpoint"
            except Exception as e:
                return str(e)

        return notificationHTML

    @staticmethod
    def _getAlarmContextGetters(
        obj: _Alert,
        context: dict[str, Any],
        recalc: weakref.ref[Callable[..., None]],
    ):
        # Note that it these go to an alarm which is held if active, or another tag that could be held elsewhere
        # It cannot reference any tag directly or preserve any references, we would not want that.

        # that could keep this tag alive long after it should be gone

        # Functions used for getting other tag values

        # You must keep a reference to recalc2 locally!!!!!!!!!

        #

        def recalc2(*a: Any, **k: Any):
            f = recalc()
            if f:
                f()

        def _context_get_numeric_tag_value(n):
            """Since an alarm can use values from other tags, we must track those values, and from there
            recalc the alarm whenever they should change.
            """
            if n in obj.source_tags:
                t = obj.source_tags[n]()
                if t:
                    return t.value

            t = Tag(n)
            obj.source_tags[n] = weakref.ref(t)
            # When any source tag updates, we want to recalculate.
            obj.source_tags[n]().subscribe(obj.recalcFunction)
            return t.value

        def context_get_string_tag_value(n):
            """Since an alarm can use values from other tags, we must track those values, and from there
            recalc the alarm whenever they should change.
            """
            if n in obj.source_tags:
                t = obj.source_tags[n]()
                if t:
                    return t.value

            t = StringTag(n)
            obj.source_tags[n] = weakref.ref(t)
            # When any source tag updates, we want to recalculate.
            obj.source_tags[n]().subscribe(obj.recalcFunction)
            return t.value

        context["tv"] = _context_get_numeric_tag_value
        context["stv"] = context_get_string_tag_value

        return recalc2

    @beartype.beartype
    def _alarm_from_data(
        self, name: str, d: dict[str, str | None | int | bool | float]
    ) -> Callable[..., None]:
        if not d.get("condition", ""):
            return

        if d.get("condition", "").strip() in ("False", "None", "0"):
            return
        tripCondition = d["condition"]

        release_condition: str | None = d.get("release_condition", None)

        priority: str = d.get("priority", "warning") or "warning"
        auto_ack: bool = d.get("auto_ack", "").lower() in (
            "yes",
            "true",
            "y",
            "auto",
        )
        trip_delay = float(d.get("trip_delay", 0) or 0)

        # Shallow copy, because we are going to override the tag getter
        context = copy.copy(self.eval_context)

        tripCondition = compile(
            tripCondition, f"{self.name}.alarms.{name}_trip", "eval"
        )
        if release_condition:
            release_condition = compile(
                release_condition, f"{self.name}.alarms.{name}_release", "eval"
            )

        n = self.name.replace("=", "expr_")
        for i in ILLEGAL_NAME_CHARS:
            n = n.replace(i, "_")

        # This is technically unnecessary, the weakref/GC based cleanup could handle it eventually,
        # But we want a real complete guarantee that it happens *right now*
        oldAlert = self.alarms.get(name, None)
        try:
            if oldAlert:
                for i in oldAlert.source_tags:
                    try:
                        t = oldAlert.source_tags[i]()
                        if t:
                            t.unsubscribe(oldAlert.recalcFunction)
                    except Exception:
                        logger.exception(
                            "cleanup err, could be because it was already deleted"
                        )

                refs = self._alarmGCRefs.pop(name, None)
                if refs:
                    self.unsubscribe(refs[2])

                    # This is the poller
                    try:
                        refs[1].unregister()
                    except Exception:
                        logger.exception("cleanup err!!!")

        except Exception:
            logger.exception("cleanup err")

        obj = _Alert(
            f"{n}.alarms.{name}",
            priority=priority,
            auto_ack=auto_ack,
            trip_delay=trip_delay,
        )

        obj.source_tags = {}

        # We don't need to weakref-ify this directly, as it just goes to the poller and the poller doesn't
        # keep strong references.

        def alarm_recalc_function(*a: Any, **k: Any) -> None:
            """Recalc with same val vor this tag, but perhaps
            a new value for
            other tags that may be fetched in the expression eval"""

            if not self:
                obj.release()
                return

            # To avoid false alarms and confusion, we never
            # trigger an alarm on missing or default data.
            if self.timestamp == 0:
                obj.release()
                return

            try:
                if eval(tripCondition, context, context):
                    obj.trip(f"Tag value:{str(context['value'])[:128]}")
                elif release_condition:
                    if eval(release_condition, context, context):
                        obj.release()
                else:
                    obj.release()
            except Exception as e:
                obj.error(str(e))
                raise

        def alarmPollFunction(value: T, timestamp: float, annotation: Any):
            "Given a new tag value, recalc the alarm expression"
            context["value"] = value
            context["timestamp"] = timestamp
            context["annotation"] = annotation

            alarm_recalc_function()

        obj.notificationHTML = self._makeTagAlarmHTMLFunc(weakref.ref(self))

        generatedRecalcFuncWeMustKeepARefTo = self._getAlarmContextGetters(
            obj, context, weakref.ref(alarm_recalc_function)
        )

        self._alarmGCRefs[name] = (
            alarm_recalc_function,
            scheduling.scheduler.schedule_repeating(
                alarm_recalc_function, 60, sync=False
            ),
            alarmPollFunction,
            generatedRecalcFuncWeMustKeepARefTo,
        )

        # Do it with this indirection so that it doesn't do anything
        # bad with some kind of race when we delete things, and so that it doesn't hold references
        def recalcPoll(*a: Any, **k: Any) -> None:
            if name in self._alarmGCRefs:
                try:
                    x = self._alarmGCRefs[name][0]
                except KeyError:
                    return
                x()

        obj.recalcFunction = recalcPoll

        # Store our new modified context.
        obj.context = context

        self.subscribe(alarmPollFunction)
        self.alarms[name] = obj

        try:
            alarmPollFunction(self.value, self.timestamp, self.annotation)
        except Exception:
            logger.exception(f"Error in test run of alarm function for :{name}")
            messagebus.post_message(
                "/system/notifications/errors",
                f"Error with tag point alarm\n{traceback.format_exc()}",
            )

        return alarmPollFunction

    def createGetterFromExpression(
        self: GenericTagPointClass[T], e: str, priority: int | float = 98
    ) -> Claim[T]:
        "Create a getter for tag self using expression e"
        try:
            for i in self.source_tags:
                self.source_tags[i].unsubscribe(self.recalc)
        except Exception:
            logger.exception(
                "Unsubscribe fail to old tag.  A subscription mau be leaked, wasting CPU. This should not happen."
            )

        self.source_tags = {}

        def recalc(*a):
            self()

        self.recalcHelper = recalc

        c = compile(e[1:], f"{self.name}_expr", "eval")

        def f():
            return eval(c, self.eval_context, self.eval_context)

        # Overriding these tags would be extremely confusing because the
        # Expression is right in the name, so don't make it easy
        # with priority 98 by default
        c2 = self.claim(f, "ExpressionTag", priority)
        self.pull()
        return c2

    @property
    def interval(self):
        return self._interval

    @interval.setter
    @beartype.beartype
    def interval(self, val: int | float | None):
        if val is not None:
            self._interval = val
        else:
            self._interval = 0

        messagebus.post_message(
            f"/system/tags/interval{self.name}",
            self._interval,
            synchronous=True,
        )
        with self.lock:
            self._manage_polling()

    @property
    def subtype(self):
        return self._subtype

    @subtype.setter
    def subtype(self, val: str):
        self._subtype = val
        if val == "bool":
            self.min = 0
            self.max = 1

    @property
    def default(self: GenericTagPointClass[T]) -> T:
        return self._default

    @default.setter
    def default(self: GenericTagPointClass[T], val: T):
        if val is not None:
            self._default = val
        else:
            self._default = self.default_data

        with self.lock:
            if self.timestamp == 0:
                # Set timestamp to 0, this marks the tag as still using a default
                # Which can be further changed
                self.set_claim_val("default", self._default, 0, "Code default")

    @classmethod
    def Tag(cls, name: str, defaults: dict[str, Any] = {}):
        name = normalize_tag_name(name)
        rval = None
        with lock:
            if name in allTags:
                x = allTags[name]()
                if x:
                    if x.__class__ is not cls:
                        raise TypeError(
                            "A tag of that name exists, but it is the wrong type. Existing: "
                            + str(x.__class__)
                            + " New: "
                            + str(cls)
                        )
                    rval = x

            if not rval:
                rval = cls(name)

            assert isinstance(rval, cls)
            return rval

    @property
    def current_source(self) -> str:
        # Avoid the lock by using retry in case claim disappears
        for i in range(10000):
            try:
                if self.active_claim:
                    return self.active_claim.name
            except Exception:
                time.sleep(0.001)
        raise RuntimeError("Corrupt state")

    def filterValue(self, v: T) -> T:
        "Pure function that returns a cleaned up or normalized version of the value"
        return v

    def __del__(self):
        # Since tags can't be deleted by the owner we rely on this
        # TODO some kind of config cleanup method?

        global allTagsAtomic
        with lock:
            try:
                del allTags[self.name]
                allTagsAtomic = allTags.copy()
            except Exception:
                logger.exception("Tag may have already been deleted")
            messagebus.post_message(
                "/system/tags/deleted", self.name, synchronous=True
            )

        for i in list(self._alarmGCRefs.keys()):
            pollStuff = self._alarmGCRefs.pop(i, None)

            if pollStuff:
                try:
                    scheduling.scheduler.unregister(pollStuff[1])
                except Exception:
                    logger.exception("Maybe already unsubbed?")

        if self._poller:
            try:
                # Scheduling is fully able to do this for us
                # But we do it ourselves because we want to add a warning later.
                self._poller.unregister()
                self._poller = None
            except Exception:
                pass

    def __call__(self, *args, **kwargs):
        if not args:
            return self.value
        else:
            return self.set_claim_val("default", *args, **kwargs)

    def _manage_polling(self):
        interval = self._interval or 0
        if (self.subscribers or self.handler) and interval > 0:
            if not self._poller or not (interval == self._poller.interval):
                if self._poller:
                    self._poller.unregister()
                    self._poller = None

                self._poller = scheduling.scheduler.schedule_repeating(
                    self.poll, interval, sync=False
                )
        else:
            if self._poller:
                self._poller.unregister()
                self._poller = None

    def fast_push(
        self, value: T, timestamp: float | None = None, annotation: Any = None
    ) -> None:
        """
        Push a value to all subscribers. Does not set the tag's value.  Ignores any and all
        overriding claims.
        Bypasses all claims. Does not guarantee to get any locks, multiples of this call can happen at once.
        Does not perform any checks on the value.  Might decide to do nothing if the system is too busy at the moment.

        Meant for streaming video and the like.
        """

        timestamp = timestamp or time.time()

        for i in self.subscribers_atomic:
            f = i()
            if f:
                f(value, timestamp, annotation)

        if not self.data_source_widget:
            return

        # Set value immediately, for later page loads
        if self._data_source_ws_lock.acquire(timeout=0.3):
            try:
                # Use the new literal computed value, not what we were passed,
                # Because it could have changed by the time we actually get to push
                self.data_source_widget.send(value)

            except Exception:
                raise
            finally:
                self._data_source_ws_lock.release()
        else:
            print("Timed out in the push function")

    @beartype.beartype
    def subscribe(
        self, f: Callable[[T, float, Any], Any], immediate: bool = False
    ):
        if isinstance(f, GenericTagPointClass) and (
            f.unreliable or self.unreliable
        ):
            f = f.fast_push

        timestamp = time.time()

        try:
            desc = str(f"{f} of {f.__module__}")

        except Exception:
            desc = str(f)

        def errcheck(*a: Any):
            if time.time() < timestamp - 0.5:
                logger.warning(
                    "Function: "
                    + desc
                    + " was deleted 0.5s after being subscribed.  This is probably not what you wanted."
                )

        if self.lock.acquire(timeout=20):
            try:
                ref: (
                    weakref.WeakMethod[Callable[[T, float, Any], Any]]
                    | weakref.ref[Callable[[T, float, Any], Any]]
                    | None
                ) = None

                if isinstance(f, types.MethodType):
                    ref = weakref.WeakMethod(f, errcheck)
                else:
                    ref = weakref.ref(f, errcheck)

                for i in self.subscribers:
                    if f == i():
                        logger.warning(
                            "Double subscribe detected, same function subscribed to "
                            + self.name
                            + " more than once.  Only the first takes effect."
                        )
                        self._manage_polling()
                        return

                self.subscribers.append(ref)

                to_rm = []
                for i in self.subscribers:
                    if not i():
                        to_rm.append(i)
                for i in to_rm:
                    self.subscribers.remove(i)
                messagebus.post_message(
                    f"/system/tags/subscribers{self.name}",
                    len(self.subscribers),
                    synchronous=True,
                )

                if immediate and self.timestamp:
                    f(self.value, self.timestamp, self.annotation)
                self._manage_polling()

                self.subscribers_atomic = copy.copy(self.subscribers)
            finally:
                self.lock.release()
        else:
            self.testForDeadlock()
            raise RuntimeError(
                "Cannot get lock to subscribe to this tag. Is there a long running subscriber?"
            )

    @beartype.beartype
    def unsubscribe(self, f: Callable[[T, float, Any], Any]):
        if self.lock.acquire(timeout=20):
            try:
                x = None
                for i in self.subscribers:
                    if i() == f:
                        x = i
                if x:
                    self.subscribers.remove(x)
                messagebus.post_message(
                    f"/system/tags/subscribers{self.name}",
                    len(self.subscribers),
                    synchronous=True,
                )
                self._manage_polling()
                self.subscribers_atomic = copy.copy(self.subscribers)
            finally:
                self.lock.release()
        else:
            self.testForDeadlock()
            raise RuntimeError(
                "Cannot get lock to subscribe to this tag. Is there a long running subscriber?"
            )

    @beartype.beartype
    def set_handler(self, f: Callable[[T, float, Any], Any]):
        self.handler = weakref.ref(f)

    def poll(self):
        if self.lock.acquire(timeout=5):
            try:
                self._get_value()
            finally:
                self.lock.release()
        else:
            self.testForDeadlock()

    def _push(self):
        """Push to subscribers. Only call under the same lock you changed value
        under. Otherwise the push might happen in the opposite order as the set, and
        subscribers would see the old data as most recent.

        Also, keep setting the timestamp and annotation under that lock, to stay atomic
        """

        # This compare must stay threadsafe.
        if self.last_value == self.lastPushedValue:
            if self.timestamp:
                return

        # Note the difference with the handler.
        # It is called synchronously, right then and there
        if self.handler:
            f = self.handler()
            if f:
                f(self.last_value, self.timestamp, self.annotation)
            else:
                self.handler = None

        self._apiPush()

        self.lastPushedValue = self.last_value

        for i in self.subscribers:
            f = i()
            if f:
                try:
                    f(self.last_value, self.timestamp, self.annotation)
                except Exception:
                    try:
                        extraData = str(
                            (
                                str(self.last_value)[:48],
                                self.timestamp,
                                str(self.annotation)[:48],
                            )
                        )
                    except Exception as e:
                        extraData = str(e)
                    logger.exception(
                        f"Tag subscriber error, val,time,annotation was: {extraData}"
                    )
                    # Return the error from whence it came to display in the proper place
                    for i in subscriber_error_handlers:
                        try:
                            i(self, f, self.last_value)
                        except Exception:
                            print(
                                "Failed to handle error: "
                                + traceback.format_exc(6)
                                + "\nData: "
                                + extraData
                            )
            del f

    def processValue(self, value) -> T:
        """Represents the transform from the claim input to the output.
        Must be a pure-ish function
        """
        return value

    @property
    def age(self):
        return time.time() - self.vta[1]

    @property
    def value(self) -> T:
        return self._get_value()

    @value.setter
    def value(self, v: T | Callable[..., T | None]):
        self.set_claim_val("default", v, time.time(), "Set via value property")

    def pull(self) -> T:
        if not self.lock.acquire(timeout=15):
            raise RuntimeError("Could not get lock")
        try:
            return self._get_value(True)
        finally:
            self.lock.release()

    def _get_value(self, force=False) -> T:
        "Get the processed value of the tag, and update last_value, It is meant to be called under lock."

        # Overrides not guaranteed to be instant
        if (self.last_got_value > time.time() - self.interval) and not force:
            return self.last_value

        active_claim = self.active_claim
        if active_claim is None:
            active_claim = self.getTopClaim()

        active_claim_value = active_claim.value

        if not callable(active_claim_value):
            # We no longer are aiming to support using the processor for impure functions

            self.last_got_value = time.time()
            self.last_value = self.processValue(active_claim_value)

        else:
            # Rate limited tag getter logic. We ignore the possibility for
            # Race conditions and assume that calling a little too often is fine, since
            # It shouldn't affect correctness

            # Note that this is on a per-claim basis.  Every claim has it's own cache.
            if (
                time.time() - active_claim.lastGotValue > self._interval
            ) or force:
                # Set this flag immediately, or else a function with an error could defeat the cacheing
                # And just flood everything with errors
                active_claim.lastGotValue = time.time()

                try:
                    # However, the actual logic IS ratelimited
                    # Note the lock is IN the try block so we don' handle errors under it and
                    # Cause bugs that way

                    # Viewing the state is pretty critical, we don't want to block
                    # that too long or we might interfere with manual recovery
                    if not self.lock.acquire(timeout=10 if force else 1):
                        self.testForDeadlock()
                        if force:
                            raise RuntimeError("Error getting lock")
                        # We extend the idea that cache is allowed to also
                        # mean we can fall back to cache in case of a timeout.
                        else:
                            logger.error(
                                "tag point:"
                                + self.name
                                + " took too long getting lock to get value, falling back to cache"
                            )
                            return self.last_value
                    try:
                        # None means no new data
                        x = active_claim_value()
                        t = time.time()

                        if x is not None:
                            # Race here. Data might not always match timestamp an annotation, if we weren't under lock
                            self.vta = (active_claim_value, t, None)

                            # Set the timestamp on the claim, so that it will not become expired
                            active_claim.vta = self.vta

                            active_claim.cachedValue = (x, t)

                            # This is just used to calculate the overall age of the tags data
                            self.last_got_value = time.time()
                            self.last_value = self.processValue(x)
                            self._push()

                    finally:
                        self.lock.release()

                except Exception:
                    # We treat errors as no new data.
                    logger.exception("Error getting tag value")

                    # The system logger is the one kaithem actually logs to file.
                    if self.lastError < (time.time() - (60 * 10)):
                        self.lastError = time.time()
                        logger.exception(
                            "Error getting tag value. This message will only be logged every ten minutes."
                        )
                    # If we can, try to send the exception back whence it came
                    try:
                        from .plugins import CorePluginEventResources

                        if hasattr(active_claim_value, "__module__"):
                            if (
                                active_claim_value.__module__
                                in CorePluginEventResources.eventsByModuleName
                            ):
                                CorePluginEventResources.eventsByModuleName[
                                    active_claim_value.__module__
                                ].handle_exception()
                    except Exception:
                        print(traceback.format_exc())

        return self.last_value

    @property
    def pushOnRepeats(self):
        return False

    @pushOnRepeats.setter
    def pushOnRepeats(self, v):
        raise AttributeError(
            "Push on repeats was causing too much trouble and too much confusion and has been removed"
        )

    def handleSourceChanged(self, name):
        if self.onSourceChanged:
            try:
                self.onSourceChanged(name)
            except Exception:
                logger.exception("Error handling changed source")

    def add_alias(self, alias: str):
        """Adds an alias of this tag, allowing access by another name."""
        global allTagsAtomic
        if "/" in alias[0:]:
            raise RuntimeError("Alias cannot contain /")

        for i in ILLEGAL_NAME_CHARS:
            if i in alias:
                raise RuntimeError(f"Alias cannot contain {i}")

        alias = normalize_tag_name(alias)
        with lock:
            self.aliases.add(alias)
            if alias in allTags:
                if allTags[alias]() is not self:
                    raise RuntimeError(f"Another tag exists with name {alias}")

            allTags[alias] = weakref.ref(self)
            allTagsAtomic = allTags.copy()

    def remove_alias(self, alias: str):
        """Removes an alias of this tag"""
        global allTagsAtomic

        alias = normalize_tag_name(alias)
        with lock:
            if alias in self.aliases:
                self.aliases.remove(alias)
            if alias in allTags:
                if allTags[alias]() is self:
                    del allTags[alias]
                    allTagsAtomic = allTags.copy()

    def claim(
        self: GenericTagPointClass[T],
        value: Any,
        name: str | None = None,
        priority: float | None = None,
        timestamp: float | None = None,
        annotation: Any = None,
        expiration: int | float = 0,
    ) -> Claim[T]:
        """Adds a 'claim', a request to set the tag's value either to a literal
        number or to a getter function.

        A tag's value is the highest priority claim that is currently
        active, or the value returned from the getter if the active claim is
        a function.
        """

        name = name or f"claim{str(time.time())}"
        if timestamp is None:
            timestamp = time.time()

        if priority and priority > 100:
            raise ValueError("Maximum priority is 100")

        if not callable(value):
            value = self.filterValue(value)

        if not self.lock.acquire(timeout=15):
            raise RuntimeError("Could not get lock")
        try:
            # we're changing the value of an existing claim,
            # We need to get the claim object, which we stored by weakref
            claim = None
            # try:
            #     ##If there's an existing claim by that name we're just going to modify it
            if name in self.claims:
                claim = self.claims[name]

            # If the weakref obj disappeared it will be None
            if claim is None:
                priority = priority or 50
                claim = self.claimFactory(
                    value, name, priority, timestamp, annotation, expiration
                )

            else:
                # It could have been released previously.
                claim.released = False
                # Inherit priority from the old claim if nobody has changed it
                if priority is None:
                    priority = claim.priority
                if priority is None:
                    priority = 50

            # Note  that we use the time, so that the most recent claim is
            # Always the winner in case of conflictsclaim

            self.claims[name] = claim

            if self.active_claim:
                ac = self.active_claim
            else:
                ac = None

            oldAcPriority = 0
            oldAcTimestamp = 0

            if ac:
                oldAcPriority = ac.priority
                oldAcTimestamp = ac.timestamp

            claim.priority = priority
            claim.vta = value, timestamp, annotation

            # If we have priority on them, or if we have the same priority but are newer
            if (
                (ac is None)
                or (priority > oldAcPriority)
                or (
                    (priority == oldAcPriority) and (timestamp > oldAcTimestamp)
                )
            ):
                self.active_claim = self.claims[name]
                self.handleSourceChanged(name)

                if callable(self.vta[0]) or callable(value):
                    needsManagePolling = True
                else:
                    needsManagePolling = False

                self.vta = (value, timestamp, annotation)

                if needsManagePolling:
                    self._manage_polling()

            # If priority has been changed on the existing active claim
            # We need to handle it
            elif name == ac.name:
                # Basically we find the highest priority claim

                c = [i for i in self.claims.values()]

                # Get the top one
                c = sorted(c, reverse=True)

                for i in c:
                    x = i
                    if x:
                        self.vta = (x.value, x.timestamp, x.annotation)

                        if not i == self.active_claim:
                            self.active_claim = i
                            self.handleSourceChanged(i.name)
                        else:
                            self.active_claim = i
                        break

            self._get_value(force=True)
            self._push()
            return claim
        finally:
            self.lock.release()

    # TODO: WHY does this have to be typed as Any????
    # Mypy seems to think different derived classes call each other
    def set_claim_val(
        self: GenericTagPointClass[T],
        claim: str,
        val: T | Callable[[], T | None] | Any,
        timestamp: float | None,
        annotation: Any,
    ):
        "Set the value of an existing claim"

        if timestamp is None:
            timestamp = time.time()

        valCallable = True
        if not callable(val):
            valCallable = False
            val = self.filterValue(val)  # type: ignore

        if not self.lock.acquire(timeout=10):
            raise RuntimeError("Could not get lock!")

        try:
            c = self.claims[claim]

            # If we're setting the active claim
            if c == self.active_claim:
                upd = True
            else:
                co = c
                ac = self.active_claim

                upd = False
                # We can "steal" control if we have the same priority
                # and are more recent, byt to do that we have to use
                #  the slower claim function that handles creating
                # and switching claims
                if (ac is None) or (
                    co.priority >= ac.priority and timestamp >= ac.timestamp
                ):
                    self.claim(val, claim, co.priority, timestamp, annotation)
                    return

            # Grab the claim obj and set it's val
            x = c
            if self._poller or valCallable:
                self._manage_polling()

            vta = val, timestamp, annotation

            x.vta = vta

            if upd:
                self.vta = vta
                if valCallable:
                    # Mark that we have not yet ever gotten this getter
                    # so the change becomes immediate.
                    # Note that we have both a tag and a claim level cache time
                    self.last_got_value = 0
                    # No need to call the function right away, that can happen when a getter calls it
                    # self._getValue()
                else:
                    self.last_got_value = time.time()
                    self.last_value = self.processValue(val)
                # No need to push is listening
                if self.subscribers or self.handler:
                    if timestamp:
                        self._push()
                    else:
                        # Even when it's the default, the dashboard
                        # Needs to know.
                        if self.data_source_widget:
                            self.data_source_widget.value = self.value
                            self.data_source_widget.send(self.value)
                else:
                    # Even when no subscribers yet, the dashboard
                    # Needs to know.
                    if self.data_source_widget:
                        self.data_source_widget.value = self.value
                        self.data_source_widget.send(self.value)
        finally:
            self.lock.release()

    # Get the specific claim object for this class
    def claimFactory(
        self,
        value: Any,
        name: str,
        priority: float,
        timestamp: float,
        annotation: Any,
        expiration: int | float = 0,
    ):
        return Claim[T](
            self, value, name, priority, timestamp, annotation, expiration
        )

    def getTopClaim(self) -> Claim[T]:
        x = [i for i in self.claims.values()]
        # Eliminate dead ones
        x = [i for i in x if i and not i.released]
        if not x:
            raise RuntimeError(
                f"Program state is corrupt, tag{self.name} has no claims"
            )
        # Get the top one
        x = sorted(x, reverse=True)
        return x[0]

    def release(self, name: str):
        if not self.lock.acquire(timeout=10):
            raise RuntimeError("Could not get lock!")

        try:
            if name not in self.claims:
                return

            if name == "default":
                raise ValueError("Cannot delete the default claim")

            self.claims[name].released = True
            o = self.getTopClaim()
            # All claims gone means this is probably in a __del__ function as it is disappearing
            if not o:
                return

            if self.active_claim:
                doChange = self.active_claim is not o
            else:
                raise RuntimeError("Corrupt state")

            self.vta = (o.value, o.timestamp, o.annotation)
            self.active_claim = o

            self._get_value()
            self._push()
            self._manage_polling()
            if doChange:
                self.handleSourceChanged(self.active_claim.name)
        finally:
            self.lock.release()


default_bool_enum = {-1: None, 0: False, 1: True}


@final
class NumericTagPointClass(GenericTagPointClass[float]):
    default_data = 0
    type = "number"

    @beartype.beartype
    def __init__(
        self, name: str, min: float | None = None, max: float | None = None
    ):
        self.vta: tuple[float, float, Any]  # type: ignore

        # Real backing vars for props

        self._hi: float | None = None
        self._lo: float | None = None
        self._min: float | None = min
        self._max: float | None = max
        # Pipe separated list of how to display value
        self._display_units: str | None = None
        self._unit: str = ""
        self._data_source_ws_lock = threading.Lock()
        self.enum = {}

        super().__init__(name)

    def processValue(self, value: float | int):
        if self._min is not None:
            value = max(self._min, value)

        if self._max is not None:
            value = min(self._max, value)

        return float(value)

    def filterValue(self, v: float) -> float:
        return float(v)

    def claimFactory(
        self,
        value: float | Callable[[], float | None],
        name: str,
        priority: float,
        timestamp: float,
        annotation: Any,
        expiration: int | float = 0,
    ):
        return NumericClaim(
            self, value, name, priority, timestamp, annotation, expiration
        )

    @property
    def min(self) -> float | int:
        return self._min if self._min is not None else -(10**18)

    @min.setter
    @beartype.beartype
    def min(self, v: float | int | None):
        self._min = v
        self.pull()

    @property
    def max(self) -> float | int:
        return self._max if self._max is not None else 10**18

    @max.setter
    @beartype.beartype
    def max(self, v: float | int | None):
        self._max = v
        self.pull()

    @property
    def hi(self) -> float | int:
        x = self._hi
        if x is None:
            return 10**18
        else:
            return x

    @hi.setter
    @beartype.beartype
    def hi(self, v: float | int | None):
        if v is None:
            v = 10**16
        self._hi = v

    @property
    def lo(self) -> float | int:
        if self._lo is None:
            return -(10**18)
        return self._lo

    @lo.setter
    @beartype.beartype
    def lo(self, v: float | int | None):
        if v is None:
            v = -(10**16)
        self._lo = v

    def convert_to(self, unit: str):
        "Return the tag's current vakue converted to the given unit"
        return convert(self.value, self.unit, unit)

    def convert_value(self, value: float | int, unit: str) -> float | int:
        "Convert a value in the tag's native unit to the given unit"
        return convert(value, self.unit, unit)

    @property
    def unit(self):
        return self._unit

    @unit.setter
    def unit(self, value: str):
        if not isinstance(value, str):
            raise TypeError("Unit must be str")

        if self._unit:
            if not self._unit == value:
                if value:
                    raise ValueError(
                        "Cannot change unit of tagpoint. To override this, set to None or '' first"
                    )
        # TODO race condition in between check, but nobody will be setting this from different threads
        # I don't think
        if not self._display_units:
            # Rarely does anyone want alternate views of dB values
            if "dB" not in value:
                try:
                    self._display_units = _default_display_units[
                        unit_types[value]
                    ]
                    # Always show the native unit
                    if value not in self._display_units:
                        self._display_units = f"{value}|{self._display_units}"
                except Exception:
                    self._display_units = value
            else:
                self._display_units = value

        self._unit = value

    @property
    def display_units(self):
        return self._display_units

    @display_units.setter
    def display_units(self, value):
        if value and not isinstance(value, str):
            raise RuntimeError("units must be str")

        self._display_units = value


@final
class StringTagPointClass(GenericTagPointClass[str]):
    default_data = ""
    unit = "string"
    type = "string"
    mqtt_encoding = "utf8"

    @beartype.beartype
    def __init__(self, name: str):
        self.vta: tuple[str, float, Any]  # type: ignore
        self._data_source_ws_lock = threading.Lock()
        super().__init__(name)

    def processValue(self, value):
        return str(value)

    def filterValue(self, v):
        return str(v)


@final
class ObjectTagPointClass(GenericTagPointClass[dict[str, Any]]):
    default_data: dict[str, Any] = {}
    type = "object"

    @beartype.beartype
    def __init__(self, name: str):
        self.vta: tuple[dict[str, Any], float, Any]  # type: ignore
        self._data_source_ws_lock = threading.Lock()

        self.validate = None
        super().__init__(name)

    def processValue(self, value):
        if isinstance(value, str):
            value = json.loads(value)
        else:
            value = copy.deepcopy(value)

        if self.validate:
            value = self.validate(value)

        return value

    def filterValue(self, v):
        if isinstance(v, str):
            v = json.loads(v)
        else:
            # test validity
            json.dumps(v)

        return v


@final
class BinaryTagPointClass(GenericTagPointClass[bytes]):
    default_data: bytes = b""
    type = "binary"

    @beartype.beartype
    def __init__(self, name: str):
        self.vta: tuple[bytes, float, Any]  # type: ignore
        self._data_source_ws_lock = threading.Lock()

        self.validate = None
        super().__init__(name)

    def processValue(self, value):
        if isinstance(value, bytes):
            value = value
        else:
            value = bytes(value)

        if self.validate:
            value = self.validate(value)

        return value

    def filterValue(self, v):
        return v


class Claim(Generic[T]):
    "Represents a claim on a tag point's value"

    @beartype.beartype
    def __init__(
        self: Claim,
        tag: GenericTagPointClass[T],
        value: T,
        name: str = "default",
        priority: int | float = 50.0,
        timestamp: int | float | None = None,
        annotation=None,
        expiration: int | float = 0,
    ):
        self.name = name
        self.tag = tag
        timestamp = timestamp or time.time()
        self.vta: tuple[T | Callable[[], T | None], float, Any] = (
            value,
            timestamp,
            annotation,
        )

        # If the value is a callable, this is the cached result plus the timestamp for the cache, separate
        # From the vta timestamp of when that callable actually got set.
        self.cachedValue = (None, timestamp)

        # Track the last *attempt* at reading the value if it is a callable, regardless of whether
        # it had new data or not.

        # It is in unix time.
        self.lastGotValue = 0.0

        self.priority = priority

        # The priority set in code, regardless of whether we expired or not
        self.realPriority = priority
        self.expired = False

        # What priority should we take on in the expired state.
        self.expiredPriority = 0

        # How long with no new data should we wait before declaring ourselves expired.
        self.expiration = expiration

        self.poller = None

        self.released = False
        self._managePolling()

    def __del__(self):
        if self.name != "default":
            # Must be self.release not self.tag.release or old claims with the same name would
            # mess up new ones. The class method has a check for that.
            self.release()

    def __lt__(self, other):
        if self.released:
            if not other.released:
                return True
        if (self.priority, self.timestamp) < (other.priority, other.timestamp):
            return True
        return False

    def __le__(self, other):
        if self.released:
            if not other.released:
                return True
        if (self.priority, self.timestamp) <= (other.priority, other.timestamp):
            return True
        return False

    def __gt__(self, other):
        if other.released:
            if not self.released:
                return True
        if (self.priority, self.timestamp) > (other.priority, other.timestamp):
            return True
        return False

    def __ge__(self, other):
        if other.released:
            if not self.released:
                return True
        if (self.priority, self.timestamp) >= (other.priority, other.timestamp):
            return True
        return False

    def expirePoll(self, force: bool = False):
        # Quick check and slower locked check.  If we are too old, set our effective
        # priority to the expired priority.

        # Expiry for callables is based on the function return value.
        # Expiry for  direct values is based on the timestamp of when external code set it.
        if callable(self.value):
            ts = self.cachedValue[1]
        else:
            ts = self.timestamp

        if not self.expired:
            if ts < (time.time() - self.expiration):
                # First we must try to refresh the callable.
                self.refreshCallable()
                if self.tag.lock.acquire(timeout=90):
                    try:
                        if callable(self.value):
                            ts = self.cachedValue[1]
                        else:
                            ts = self.timestamp

                        if ts < (time.time() - self.expiration):
                            self.setPriority(self.expiredPriority, False)
                            self.expired = True
                    finally:
                        self.tag.lock.release()
                else:
                    raise RuntimeError(
                        "Cannot get lock to set priority, waited 90s"
                    )
        else:
            # If we are already expired just refresh now.
            self.refreshCallable()

    def refreshCallable(self):
        # Only call the getter under lock in case it happens to not be threadsafe
        if callable(self.value):
            if self.tag.lock.acquire(timeout=90):
                self.lastGotValue = time.time()
                try:
                    x = self.value()
                    if x is not None:
                        self.cachedValue = (x, time.time())
                        self.unexpire()
                finally:
                    self.tag.lock.release()

            else:
                raise RuntimeError(
                    "Cannot get lock to set priority, waited 90s"
                )

    def set_expiration(
        self, expiration: float, expiredPriority: int | float = 1
    ):
        """Set the time in seconds before this claim is regarded as stale, and what priority to revert to in the stale state.
        Note that that if you use a getter with this, it will constantly poll in the background
        """
        if self.tag.lock.acquire(timeout=90):
            try:
                self.expiration = expiration
                self.expiredPriority = expiredPriority
                self._managePolling()

            finally:
                self.tag.lock.release()
        else:
            raise RuntimeError("Cannot get lock, waited 90s")

    def _managePolling(self):
        interval = self.expiration
        if interval:
            if not self.poller or not (interval == self.poller.interval):
                if self.poller:
                    self.poller.unregister()
                self.poller = scheduling.scheduler.schedule_repeating(
                    self.expirePoll, interval, sync=False
                )
        else:
            if self.poller:
                self.poller.unregister()
                self.poller = None

    def unexpire(self):
        # If we are expired, un-expire ourselves.
        if self.expired:
            if self.tag.lock.acquire(timeout=90):
                try:
                    if self.expired:
                        self.expired = False
                        self.setPriority(self.realPriority, False)
                finally:
                    self.tag.lock.release()
            else:
                raise RuntimeError(
                    "Cannot get lock to set priority, waited 90s"
                )

    @property
    def value(self):
        return self.vta[0]

    @property
    def timestamp(self):
        return self.vta[1]

    @property
    def annotation(self):
        return self.vta[2]

    def set(
        self, value, timestamp: float | None = None, annotation: Any = None
    ):
        # Not threadsafe here if multiple threads use the same claim, value, timestamp, and annotation can
        self.vta = (value, self.timestamp, self.annotation)

        # If we are expired, un-expi
        if self.expired:
            self.unexpire()

        # In the released state we must do it all over again
        elif self.released:
            if self.tag.lock.acquire(timeout=60):
                try:
                    self.tag.claim(
                        value=self.value,
                        timestamp=self.timestamp,
                        annotation=self.annotation,
                        priority=self.priority,
                        name=self.name,
                    )
                finally:
                    self.tag.lock.release()

            else:
                raise RuntimeError(
                    "Cannot get lock to re-claim after release, waited 60s"
                )
        else:
            self.tag.set_claim_val(self.name, value, timestamp, annotation)

    def release(self):
        try:
            # Stop any weirdness with an old claim double releasing and thus releasing a new claim
            if self.tag.claims[self.name] is not self:
                # If the old replaced claim is somehow the active omne we actually should handle that
                if self.tag.active_claim is not self:
                    return
        except KeyError:
            return

        self.tag.release(self.name)

        # Unregister the polling.
        if self.poller:
            self.poller.unregister()
            self.poller = None

    def setPriority(self, priority: float, realPriority: bool = True):
        if self.tag.lock.acquire(timeout=60):
            try:
                if realPriority:
                    self.realPriority = priority
                self.priority = priority
                self.tag.claim(
                    value=self.value,
                    timestamp=self.timestamp,
                    annotation=self.annotation,
                    priority=self.priority,
                    name=self.name,
                )
            finally:
                self.tag.lock.release()

        else:
            raise RuntimeError("Cannot get lock to set priority, waited 60s")

    def __call__(self, *args, **kwargs):
        if not args:
            raise ValueError("No arguments")
        else:
            return self.set(*args, **kwargs)


class NumericClaim(Claim[float]):
    "Represents a claim on a tag point's value"

    @beartype.beartype
    def __init__(
        self: NumericClaim,
        tag: NumericTagPointClass,
        value: float | Callable[[], float | None],
        name: str = "default",
        priority: int | float = 50,
        timestamp: int | float | None = None,
        annotation=None,
        expiration: int | float = 0,
    ):
        self.tag: NumericTagPointClass
        Claim.__init__(
            self, tag, value, name, priority, timestamp, annotation, expiration
        )

    def set_as(
        self,
        value: float,
        unit: str,
        timestamp: float | None = None,
        annotation: Any = None,
    ):
        "Convert a value in the given unit to the tag's native unit"
        self.set(convert(value, unit, self.tag.unit), timestamp, annotation)


Tag = NumericTagPointClass.Tag
ObjectTag = ObjectTagPointClass.Tag
StringTag = StringTagPointClass.Tag
BinaryTag = BinaryTagPointClass.Tag
