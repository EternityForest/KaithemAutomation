# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import base64
import copy
import functools
import gc
import json
import re
import threading
import time
import traceback
import types
import warnings
import weakref
from collections.abc import Callable
from typing import (
    Any,
    Generic,
    TypeVar,
    final,
)

import structlog
from scullery import scheduling, snake_compat
from scullery.units import convert, unit_types

from kaithem.src.validation_util import validate_args

from . import alerts, messagebus, pages, widgets, workers

logger = structlog.get_logger(__name__)
# _ and . allowed
ILLEGAL_NAME_CHARS = "{}|\\<>,?-=+)(*&^%$#@!~`\n\r\t\0"


def get_tag_meta(tag_name: str) -> dict[str, Any]:
    r: dict[str, Any] = {}
    t = allTagsAtomic[tag_name]()
    assert t

    try:
        pages.require(t.get_effective_permissions()[0])
    except PermissionError:
        raise
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


@functools.lru_cache(4096, False)
def normalize_tag_name(name: str, replacementChar: str | None = None) -> str:
    "Normalize hte name, and raise errors on anything just plain invalid, unless a replacement char is supplied"
    name = name.strip()
    if name == "":
        raise ValueError("Tag with empty name")

    if name[0] in "0123456789":
        raise ValueError("Begins with number")

    # Special case, these tags are expression tags.
    if not name.startswith(("=", "/=")):
        name = re.sub(r"\[(.*)\]", lambda x: f".{x.groups(1)[0]}", name)
        name = snake_compat.any_to_snake(name)
        name = name.lower()

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
    in seconds.

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
            return f"<Tag Point: {self.name}={str(self._vta[0])[:20]}>"
        except Exception:
            try:
                return f"<Tag Point: {self.name}>"
            except Exception:  # pragma: no cover
                return f"<Tag Point: No name, not initialzed yet at {hex(id(self))}>"

    @validate_args
    def __init__(self, name: str):
        global allTagsAtomic
        _name: str = normalize_tag_name(name)

        # If the tag already exists it could just need
        # garbage collection
        if _name in allTags:
            gc.collect()
            gc.collect()

        if _name in allTags:
            raise RuntimeError(
                "Tag with this name already exists, use the getter function to get it instead"
            )

        self.name: str = _name
        """The normalized name of the tag"""

        self.configLoggers: weakref.WeakValueDictionary[str, object] = (
            weakref.WeakValueDictionary()
        )
        """Internal use only, holds references to logger objects"""

        # Used for the fake buttons in the device page
        self._k_ui_fake: Claim[T]

        self.aliases: set[str] = set()

        # Where we store a ref for the widget
        self._gui_updateSubscriber: Callable[[T, float, Any], Any]

        # Dependency tracking, if a tag depends on other tags, such as =expression based ones
        self._source_tags: dict[str, GenericTagPointClass[Any]] = {}

        self._default: T

        self._data_source_widget: widgets.Widget | None = None

        # Used for pushing data to frontend
        self._data_source_ws_lock: threading.Lock

        self.description: str = ""
        """User settable description in free text"""

        # True if there is already a copy of the deadlock diagnostics running
        self._testingForDeadlock: bool = False

        self._alreadyPostedDeadlock: bool = False

        # This string is just used to stash some extra info
        self._subtype: str = ""

        self._unique_int = 0

        # Same, but represents the most recent output of getter if it's a getter
        self._vta: tuple[T, float, Any] = (
            self._process_value_for_tag_type(copy.deepcopy(self.default_data)),
            0,
            None,
        )

        self._getter_cache_time = 0

        # Used to optionally record a list of allowed values
        self._enum: list[Any] | None = None
        """
        In unreliable mode the tag's acts like a simple UDP connection.
        The only supported feature is that writing the tag notifies subscribers.
        It is not guaranteed to store the last value, to error check the value,
        To prevent multiple writes at the same time, and the claims may be ignored.

        Subscribing the tag directly to another tga uses fast_push that bypasses all claims.
        In unreliable mode you should only use fast_push to set values.
        """
        self.unreliable: bool = False

        # Read, write, priority
        self._permissions: tuple[str, str, float] = (
            "__never__",
            "__never__",
            0.0,
        )

        self._can_post_alert_error = True
        # Our alerts and the callbacks to check them
        self._alerts: dict[str, alerts.Alert] = {}
        self._alert_poll_functions: dict[str, Callable[[], Any]] = {}

        # The cached actual value from the claims
        self._cachedRawClaimVal: T = copy.deepcopy(self.default_data)

        # The real current in use val, after the config override logic
        self._interval: float | int = 0
        self.active_claim: None | Claim[T] = None

        self._claims: dict[str, Claim[T]] = {}
        self._lock = threading.RLock()
        self._subscribers: list[weakref.ref[Callable[..., Any]]] = []

        # This is only used for fast stream mode
        self._subscribers_atomic: list[weakref.ref[Callable[..., Any]]] = []

        self._poller: scheduling.RepeatingEvent | None = None

        # The "Owner" of a tag can use this to say if anyone else should write it
        self.writable = True

        self.eval_context: dict[str, Any] = {
            "tv": self._context_get_numeric_tag_value,
            "stv": self._context_get_string_tag_value,
            "tag": self,
        }
        """Dict used as globals and locals for evaluating
        alarm conditions and expression tags."""

        self._lastError: float | int = 0

        self.owner: str = ""
        """Free text user settable string describing the "owner" of the tag point
        This is not a precisely defined concept"""

        self._lastPushedValue: T | None = None

        with lock:
            allTags[_name] = weakref.ref(self)
            allTagsAtomic = allTags.copy()

        self.default_claim = self.claim(
            self._process_value_for_tag_type(copy.deepcopy(self.default_data)),
            "default",
            timestamp=0,
            annotation=self.DEFAULT_ANNOTATION,
        )
        """The claim named default which is normally the only one that ever gets used"""

        # Reset this so that any future value sets actually do push.  First write should always push
        # Independent of change detection.
        self._lastPushedValue = None

        # What permissions are needed to
        # read or override this tag, as a tuple of 2 permission strings and an int representing the priority
        # that api clients can use.
        # As always, configured takes priority
        self._permissions = ("", "", 50)

        self._apiClaim: None | Claim[T] = None

        # This is where we can put a manual override
        # claim from the web UI.
        self._manualOverrideClaim: None | Claim[T] = None

        with lock:
            messagebus.post_message(
                "/system/tags/created", self.name, synchronous=True
            )

        if self.name.startswith("="):
            self.exprClaim = self.createGetterFromExpression(self.name)
            self.writable = False

        assert len(self._claims) > 0

    # In reality value, timestamp, annotation are all stored together as a tuple

    @property
    def timestamp(self) -> float:
        return self._vta[1]

    @property
    def annotation(self) -> Any:
        return self._vta[2]

    def is_dynamic(self) -> bool:
        """True if the tag has a getter instead of a set value"""
        return self.get_top_claim().getter is not None

    @validate_args
    def expose(
        self,
        read_perms: str | list[str] = "",
        write_perms: str | list[str] = "system_admin",
        expose_priority: str | int | float = 50,
    ):
        """
        Expose the tag to web APIs, with the permissions specified. Permissions must be
        strings, but can use commas for multiple.

        Priority must be an integer, and determines the priority at which the web
        API may set the tag's value.  The web API cannot control the priority, but
        can release the claim entirely by sending a null, or reclaim by sending real
        data again.


        The way this works is that tag.data_source_widget is created, a
        Widgets.DataSource instance having id "tag:TAGNAME", with the given
        permissions.

        Messages TO the server will set a claim at the permitted priority, or release any
        claim if the data is None. Data FROM the server indicates the actual current
        value of the tag.



        You must always have at least one read permission, and write_perms defaults
        to `__admin__`.   Note that if the user sets or configures any permissions
        via the web API, they will override those set in code.

        If read_perms or write_perms is empty, disable exposure.

        You cannot have different priority levels for different users this way, that
        would be highly confusing. Use multiple tags or code your own API for that.
        """

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
            d: tuple[str, str, float] = ("", "", 50)
        else:
            d: tuple[str, str, float] = (
                read_perms,
                write_perms,
                expose_priority,
            )

        with lock:
            with self._lock:
                self._permissions = d

                d2 = self.get_effective_permissions()
                if d2[2]:
                    expose_priority = float(d2[2])

                perms_list = list(d2)

                assert isinstance(perms_list[0], str)
                assert isinstance(perms_list[1], str)

                # Be safe, only allow writes if user specifies a permission
                perms_list[1] = perms_list[1] or "system_admin"

                if not perms_list[0]:
                    self._data_source_widget = None
                    try:
                        del exposedTags[self.name]
                    except KeyError:
                        pass
                    if self._apiClaim:
                        self._apiClaim.release()
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
                    if self._apiClaim:
                        self._apiClaim.set_priority(expose_priority)
                    self._apiPush()

                    # We don't want the web connection to be able to keep the tag alive
                    # so don't give it a reference to us
                    self._weakApiHandler: Callable[[str, T | None], None] = (
                        self._makeWeakApiHandler(weakref.ref(self))
                    )
                    w.attach(self._weakApiHandler)

                    self._data_source_widget = w

    @staticmethod
    def _makeWeakApiHandler(
        wr: weakref.ref[GenericTagPointClass[T]],
    ) -> Callable[[str, T | None], None]:
        def f(u: str, v: T | None):
            x = wr()
            if x:
                x._apiHandler(u, v)

        return f

    def get_alerts(self) -> list[alerts.Alert]:
        """Return a list of all alert objects for this tag, including ones that are not active"""
        with lock:
            return list(self._alerts.values())

    def _apiHandler(self, acting_user: str, v: T | None):
        if v is None:
            if self._apiClaim:
                self._apiClaim.release()
        else:
            # No locking things up if the times are way mismatched and it sets a time way in the future
            self._apiClaim = self.claim(
                v,
                "WebAPIClaim",
                priority=float(self.get_effective_permissions()[2]),
                annotation=acting_user,
            )

            # They tried to set the value but could not, so inform them of such.
            if not self.current_source == self._apiClaim.name:
                self._apiPush()

    def get_effective_permissions(self) -> tuple[str, str, float]:
        """
        Get the permissions that currently apply here. Configured ones override in-code ones

        Returns:
            list: [read_perms, write_perms, writePriority]. Priority determines the priority of web API claims.
        """
        d2: tuple[str, str, float] = (
            str(self._permissions[0]),
            str(self._permissions[1]),
            float(self._permissions[2]),
        )

        # Block exposure at all if the permission is never
        if "__never__" in self._permissions[0]:
            return ("", "", 0.0)

        return d2

    def _apiPush(self):
        "If the expose function was used, push this to the data_source_widget"
        if not self._data_source_widget:
            return

        # Immediate write, don't push yet, do that in a thread because TCP can block
        def pushFunction():
            # Set value immediately, for later page loads
            assert self._data_source_widget
            self._data_source_widget.value = self.value
            if self._data_source_ws_lock.acquire(timeout=1):
                try:
                    # Use the new literal computed value, not what we were passed,
                    # Because it could have changed by the time we actually get to push
                    self._data_source_widget.send(self.value)
                finally:
                    self._data_source_ws_lock.release()

        # Should there already be a function queued for this exact reason, we just let
        # That one do it's job
        if self._data_source_ws_lock.acquire(timeout=0.001):
            try:
                workers.do(pushFunction)
            finally:
                self._data_source_ws_lock.release()

    def _testForDeadlock(self):
        "Run a check in the background to make sure this lock isn't clogged up"

        def f():
            # Approx check, more than one isn't the worst thing
            if self._testingForDeadlock:
                return

            self._testingForDeadlock = True

            if self._lock.acquire(timeout=30):
                self._lock.release()
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

    def _recalc(self, *a: Any, **k: Any):
        "Handler for exoression tag dependencies"
        # It's a getter, ignore the mypy unused thing.
        self.pull(sync=True)
        # These can need recalc even if the tag val doesn't
        # change because another dependency tag might have
        # It might mean doing it twice but that's fine.
        self.recalc_alerts()

    def _context_get_numeric_tag_value(self, n: str) -> float:
        "Get the tag value, adding it to the list of source tags. Creates tag if it isn't there"
        try:
            return self._source_tags[n].value
        except KeyError:
            self._source_tags[n] = Tag(n)
            # When any source tag updates, we want to recalculate.
            self._source_tags[n].subscribe(self._recalc)
            return self._source_tags[n].value

    def _context_get_string_tag_value(self, n: str) -> str:
        "Get the tag value, adding it to the list of source tags. Creates tag if it isn't there"
        try:
            return self._source_tags[n].value
        except KeyError:
            self._source_tags[n] = StringTag(n)
            # When any source tag updates, we want to recalculate.
            self._source_tags[n].subscribe(self._recalc)
            return self._source_tags[n].value

    # Note the black default condition, that lets us override a normal alarm while using the default condition.
    @validate_args
    def set_alarm(
        self,
        name: str,
        condition: str | None = "",
        priority: str = "info",
        release_condition: str | None = "",
        auto_ack: bool = False,
        trip_delay: float | int | str = "0",
        enabled: bool = True,
    ) -> alerts.Alert | None:
        self._can_post_alert_error = True
        with lock:
            if condition is None:
                if name in self._alerts:
                    self._alerts[name].close()
                    self._alerts.pop(name, None)
                    self._alert_poll_functions.pop(name, None)
                return

            if not name:
                raise RuntimeError("Empty string name")

            trip_delay = float(trip_delay)

            trip_code = compile(condition, "<string>", "eval")
            if release_condition:
                release_code = compile(release_condition, "<string>", "eval")
            else:
                release_code = None

            alert = alerts.Alert(
                f"{self.name}:{name}",
                priority=priority,
                trip_delay=float(trip_delay),
                auto_ack=auto_ack,
                enabled=enabled,
            )

            def poll_alerts():
                # Only trip on real data, not defaults.
                if self.timestamp > 0:
                    trip = eval(trip_code, self.eval_context)
                    if trip:
                        v = self.value
                        if isinstance(v, (int | float)) or (
                            isinstance(v, str) and len(v) < 64
                        ):
                            alert.trip(f"Value: {v}, Condition: {condition}")
                        else:
                            alert.trip()
                        return
                if release_code:
                    release = eval(release_code, self.eval_context)
                    if release:
                        alert.release()
                        return
                else:
                    alert.release()

            self._alerts[name] = alert
            self._alert_poll_functions[name] = poll_alerts
            self.recalc_alerts()
            return alert

        self.recalc_alerts()

    def recalc_alarm_self_subscriber(
        self, value: T, timestamp: float, annotation: Any
    ):
        self.recalc_alerts()

    def recalc_alerts(self):
        self.eval_context["value"] = self.value
        try:
            with self._lock:
                for i in self._alert_poll_functions:
                    self._alert_poll_functions[i]()
        except Exception:
            if self._can_post_alert_error:
                self._can_post_alert_error = False
                messagebus.post_message(
                    "/system/notifications/errors",
                    "Error in tag alarm expression",
                )
                logger.exception("Error in tag alarm")

    def createGetterFromExpression(
        self: GenericTagPointClass[T], e: str, priority: int | float = 98
    ) -> Claim[T]:
        "Create a getter for tag self using expression e"
        try:
            for i in self._source_tags:
                self._source_tags[i].unsubscribe(self._recalc)
        except Exception:
            logger.exception(
                "Unsubscribe fail to old tag.  A subscription mau be leaked, wasting CPU. This should not happen."
            )

        self._source_tags = {}

        c = compile(e[1:], f"{self.name}_expr", "eval")

        def f(claim: Claim[T]):
            x = eval(c, self.eval_context, self.eval_context)
            claim.set(x, annotation=e)

        initial = eval(c, self.eval_context, self.eval_context)

        # Overriding these tags would be extremely confusing because the
        # Expression is right in the name, so don't make it easy
        # with priority 98 by default
        c2 = self.claim(initial, "ExpressionTag", priority)
        c2.getter = f

        self.pull()
        return c2

    @property
    def interval(self):
        """
        Set the sample rate of the tags data in seconds.
        Affects polling and cacheing if getters are used.
        """
        return self._interval

    @interval.setter
    @validate_args
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

    @property
    def subtype(self):
        """
        A string that determines a more specific type.  Use a com.site.x name, or
        something like that, to avoid collisions.

        "Official" ones include bool, which can be 1 or 0, or tristate, which can be
        -1 for unset/no effect, 0, or 1.
        """
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

        with self._lock:
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
    def data_source_widget(self) -> None | widgets.Widget:
        return self._data_source_widget

    @property
    def current_source(self) -> str:
        """Return the Claim object that is currently
        controlling the tag"""

        # Avoid the lock by using retry in case claim disappears
        for i in range(10000):
            try:
                if self.active_claim:
                    return self.active_claim.name
            except Exception:
                time.sleep(0.001)
        raise RuntimeError("Corrupt state")

    def __del__(self):
        # Since tags can't be deleted by the owner we rely on this
        # TODO some kind of config cleanup method?

        global allTagsAtomic
        with lock:
            if not hasattr(self, "name"):
                logger.error("Tag deleted before it even got initialized")
                return
            try:
                del allTags[self.name]
                allTagsAtomic = allTags.copy()
            except Exception:
                logger.exception("Tag may have already been deleted")
            messagebus.post_message(
                "/system/tags/deleted", self.name, synchronous=True
            )

            for i in self.aliases:
                try:
                    if i in allTags:
                        if allTags[i]() is self or allTags[i]() is None:
                            del allTags[i]
                            allTagsAtomic = allTags.copy()
                except Exception:
                    logger.exception("Tag may have already been deleted")

        if self._poller:
            try:
                # Scheduling is fully able to do this for us
                # But we do it ourselves because we want to add a warning later.
                self._poller.unregister()
                self._poller = None
            except Exception:
                pass

    def __call__(
        self,
        value: T | None = None,
        timestamp: float | None = None,
        annotation: Any = None,
        **kwargs: Any,
    ):
        """
        Equivalent to calling set() on the default handler. If
        no args are provided, just returns the tag's value.
        """
        if (value is None) and not kwargs and not timestamp and not annotation:
            return self.value
        else:
            if value is None:
                raise ValueError("Must provide a value to set")
            return self.set_claim_val(
                "default", value, timestamp, annotation, **kwargs
            )

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

        for i in self._subscribers_atomic:
            f = i()
            if f:
                f(value, timestamp, annotation)

        if not self._data_source_widget:
            return

        # Set value immediately, for later page loads
        if self._data_source_ws_lock.acquire(timeout=0.3):
            try:
                # Use the new literal computed value, not what we were passed,
                # Because it could have changed by the time we actually get to push
                self._data_source_widget.send(value)

            except Exception:
                raise
            finally:
                self._data_source_ws_lock.release()
        else:
            print("Timed out in the push function")

    @validate_args
    def subscribe(
        self, f: Callable[[T, float, Any], Any], immediate: bool = False
    ):
        """
        f will be called whe the value changes, as long
        as the function f still exists.

        It will also be called the first time you set a tag's value, even if the
        value has not changed.

        It should very very rarely be called on repeated values otherwise, but this
        behavior is not absolutelu guaranteed and should not be relied on.

        All subscribers are called synchronously in the same thread that set the
        value, however any errors are logged and ignored.

        They will all be called under the tagpoint's lock. To avoid various problems
        like endless loops, one should be careful when accessing the tagpoint itself
        from within this function.

        """
        if isinstance(f, GenericTagPointClass) and (
            f.unreliable or self.unreliable
        ):
            f = f.fast_push

        timestamp = time.time()

        try:
            desc = str(f"{f} of {f.__module__}")

        except Exception:
            desc = str(f)

        def errcheck(r: weakref.ref[Any]):
            # Handle shutdown cleanup
            if not time:
                return
            if time.time() < timestamp - 0.5:
                logger.warning(
                    "Function: "
                    + desc
                    + " was deleted <0.5s after being subscribed.  This is probably not what you wanted."
                )
            try:
                if r in self._subscribers:
                    logger.warning(
                        f"Tag point subscriber {desc} on tag {self.name} was not explicitly unsubscribed."
                    )
            # Could be iteration errors or something here,
            # this check isn't that important
            except Exception:
                print(traceback.format_exc())

        if self._lock.acquire(timeout=60):
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

                for i in self._subscribers:
                    if f == i():
                        logger.warning(
                            "Double subscribe detected, same function subscribed to "
                            + self.name
                            + " more than once.  Only the first takes effect."
                        )
                        return

                self._subscribers.append(ref)

                to_rm = []
                for i in self._subscribers:
                    if not i():
                        to_rm.append(i)
                for i in to_rm:
                    self._subscribers.remove(i)
                messagebus.post_message(
                    f"/system/tags/subscribers{self.name}",
                    len(self._subscribers),
                    synchronous=True,
                )

                if immediate and self.timestamp:
                    f(self.value, self.timestamp, self.annotation)

                self._subscribers_atomic = copy.copy(self._subscribers)
            finally:
                self._lock.release()
        else:  # pragma: no cover
            self._testForDeadlock()
            raise RuntimeError(
                "Cannot get lock to subscribe to this tag. Is there a long running subscriber?"
            )

    @validate_args
    def unsubscribe(self, f: Callable[[T, float, Any], Any]):
        if self._lock.acquire(timeout=20):
            try:
                x = None
                for i in self._subscribers:
                    if i() == f:
                        x = i
                if x:
                    self._subscribers.remove(x)
                messagebus.post_message(
                    f"/system/tags/subscribers{self.name}",
                    len(self._subscribers),
                    synchronous=True,
                )
                self._subscribers_atomic = copy.copy(self._subscribers)
            finally:
                self._lock.release()

        else:  # pragma: no cover
            self._testForDeadlock()
            raise RuntimeError(
                "Cannot get lock to subscribe to this tag. Is there a long running subscriber?"
            )

    def poll(self):
        if self._lock.acquire(timeout=5):
            try:
                self._get_value()
            finally:
                self._lock.release()
        else:  # pragma: no cover
            self._testForDeadlock()

    @property
    def last_value(self):
        return self._vta[0]

    def _push(self):
        """Push to subscribers and recalc alerts.
        Only call under the same lock you changed value
        under. Otherwise the push might happen in the opposite order
        as the set, and subscribers would see the old data as most recent.

        Also, keep setting the timestamp and annotation under that
        lock, to stay atomic
        """

        # This compare must stay threadsafe.
        if self.last_value == self._lastPushedValue:
            if self.timestamp:
                return

        self._apiPush()

        self._lastPushedValue = self.last_value

        if self._alerts:
            self.recalc_alerts()

        for i in self._subscribers:
            f = i()
            if f:
                try:
                    f(*self._vta)
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

    def _process_value_for_tag_type(self, value: T) -> T:
        """Represents the transform from the claim input to the output.
        Must be a pure-ish function.
        """
        return value

    @property
    def age(self):
        return time.time() - self._vta[1]

    @property
    def value(self) -> T:
        return self._get_value()[0]

    @value.setter
    def value(self, v: T):
        self.set_claim_val("default", v, time.time(), "Set via value property")

    def pull(self, sync=False) -> None:
        """
        Request that any getter in the active claim produce a new value if it has a getter.
        Note that we do not automatically poll or run the getters anymore,
        getters must be explicitly requested.
        """
        if not self._lock.acquire(timeout=15):
            raise RuntimeError("Could not get lock")
        try:
            x = self.get_top_claim()
            if x.getter:

                def f():
                    try:
                        c = x.getter
                        if c:
                            c(x)
                    except Exception:
                        logger.exception(
                            "Error getting tag value for %s", self.name
                        )

                if not sync:
                    workers.do(f)
                else:
                    f()
        finally:
            self._lock.release()

    def get_vta(self, force=False) -> tuple[T, float, Any]:
        """Get the current value, timestamp and annotation.
        If force is true and the value is a getter, then force a new update.
        """
        if force:
            warnings.warn(
                "get_vta(force=True) is deprecated, use get_value() instead",
            )
        if not self._lock.acquire(timeout=240):
            raise RuntimeError("Could not get lock")
        try:
            return self._get_value()
        finally:
            self._lock.release()

    def _get_value(self) -> tuple[T, float, Any]:
        "Get the processed value of the tag, and update last_value, It is meant to be called under lock."

        active_claim = self.active_claim
        if active_claim is None:
            active_claim = self.get_top_claim()

        active_claim_value: T | None = active_claim.value

        if not active_claim_value:
            return self._vta

        # We no longer are aiming to support using the processor for impure functions

        self._getter_cache_time = time.time()
        self._vta = (
            self._process_value_for_tag_type(active_claim_value),
            self._vta[1],
            self._vta[2],
        )

        return self._vta

    def add_alias(self, alias: str):
        """Adds an alias of this tag, allowing access by another name."""
        global allTagsAtomic
        if "/" in alias[0:]:
            raise ValueError("Alias cannot contain /")

        for i in ILLEGAL_NAME_CHARS:
            if i in alias:
                raise ValueError(f"Alias cannot contain {i}")

        if not alias.strip():
            raise ValueError("Alias cannot be empty")

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
        value: T,
        name: str | None = None,
        priority: float | None = None,
        timestamp: float | None = None,
        annotation: Any = None,
    ) -> Claim[T]:
        """
        Adds a claim to the tag and returns the Claim object. The claim will
        dissapear if the returned Claim object ever does. Value may be a function
        that can be polled to return a float, or a number.

        If a function is provided, it may return None to indicate no new data has
        arrived. This will not update the tags age.

        Should a claim already exist by that name, the exact same claim object as
        the previous claim is returned.

        Rather than using multiple claims, consider whether it's really needed, lots
        of builtin functionality in the UI is mean to just work with the default
        claim, for ease of use.
        """

        name = name or f"claim{str(time.time())}"
        if timestamp is None:
            timestamp = time.time()

        if priority and priority > 100:
            raise ValueError("Maximum priority is 100")

        if not self._lock.acquire(timeout=15):
            raise RuntimeError("Could not get lock")
        try:
            # we're changing the value of an existing claim,
            # We need to get the claim object, which we stored by weakref
            claim = None
            # try:
            #     ##If there's an existing claim by that name we're just going to modify it
            if name in self._claims:
                claim = self._claims[name]

            # If the weakref obj disappeared it will be None
            if claim is None:
                priority = priority or 50
                claim = self.claimFactory(
                    value, name, priority, timestamp, annotation
                )

            else:
                # It could have been released previously.
                claim.released = False
                # Inherit priority from the old claim if nobody has changed it
                if priority is None:
                    priority = claim.effective_priority
                if priority is None:
                    priority = 50

            # Note  that we use the time, so that the most recent claim is
            # Always the winner in case of conflictsclaim

            self._claims[name] = claim

            if self.active_claim:
                active_claim = self.active_claim
            else:
                active_claim = None

            oldAcPriority = 0
            oldAcTimestamp = 0

            if active_claim:
                oldAcPriority = active_claim.effective_priority
                oldAcTimestamp = active_claim.timestamp

            claim.effective_priority = priority
            claim.vta = value, timestamp, annotation

            # If we have priority on them, or if we have the same priority but are newer
            if (
                (active_claim is None)
                or (priority > oldAcPriority)
                or (
                    (priority == oldAcPriority) and (timestamp > oldAcTimestamp)
                )
            ):
                self.active_claim = self._claims[name]

                self._vta = (value, timestamp, annotation)

            # If priority has been changed on the existing active claim
            # We need to handle it
            elif name == active_claim.name:
                # Basically we find the highest priority claim

                c = [i for i in self._claims.values()]

                # Get the top one
                c = sorted(c, reverse=True)

                for i in c:
                    x = i

                    if x:
                        v, t, a = x.vta
                        if v is not None:
                            self._vta = v, t, a

                        if not i == self.active_claim:
                            self.active_claim = i
                        else:
                            self.active_claim = i
                        break

            self._get_value()
            self._push()
            return claim
        finally:
            self._lock.release()

    # TODO: WHY does this have to be typed as Any????
    # Mypy seems to think different derived classes call each other
    def set_claim_val(
        self: GenericTagPointClass[T],
        claim: str,
        val: T,
        timestamp: float | None,
        annotation: Any,
    ):
        "Set the value of an existing claim"

        if timestamp is None:
            timestamp = time.time()

        if not self._lock.acquire(timeout=10):
            raise RuntimeError("Could not get lock!")

        try:
            c = self._claims[claim]

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
                    co.effective_priority >= ac.effective_priority
                    and timestamp >= ac.timestamp
                ):
                    self.claim(
                        val, claim, co.effective_priority, timestamp, annotation
                    )
                    return

            # Grab the claim obj and set it's val
            x = c

            vta = val, timestamp, annotation

            x.vta = vta

            if upd:
                self._vta = vta
                # No need to push is listening
                if self._subscribers or self._alerts:
                    if timestamp:
                        self._push()
                    else:
                        # Even when it's the default, the dashboard
                        # Needs to know.
                        if self._data_source_widget:
                            self._data_source_widget.value = self.value
                            self._data_source_widget.send(self.value)
                else:
                    # Even when no subscribers yet, the dashboard
                    # Needs to know.
                    if self._data_source_widget:
                        self._data_source_widget.value = self.value
                        self._data_source_widget.send(self.value)
        finally:
            self._lock.release()

    # Get the specific claim object for this class
    def claimFactory(
        self,
        value: Any,
        name: str,
        priority: float,
        timestamp: float,
        annotation: Any,
    ):
        return Claim[T](self, value, name, priority, timestamp, annotation)

    def get_top_claim(self) -> Claim[T]:
        x = [i for i in self._claims.values()]
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
        if not self._lock.acquire(timeout=10):
            raise RuntimeError("Could not get lock!")

        try:
            if name not in self._claims:
                return

            if name == "default":
                raise ValueError("Cannot delete the default claim")

            self._claims[name].released = True
            o = self.get_top_claim()
            # All claims gone means this is probably in a __del__ function as it is disappearing
            if not o:
                return
            v, t, a = o.vta

            if not self.active_claim:
                raise RuntimeError("Corrupt state")

            if v is not None:
                self._vta = v, t, a

            self.active_claim = o

            self._get_value()
            self._push()

        finally:
            self._lock.release()

    @property
    def subscribers(self) -> list[Callable[[T, float, Any], Any]]:
        if self._lock.acquire(timeout=15):
            try:
                x: list[Callable[[T, float, Any], Any]] = []
                for i in self._subscribers:
                    y = i()
                    if y:
                        x.append(y)
                return x
            finally:
                self._lock.release()
        else:
            raise RuntimeError("failed to get lock to list subscribers")


default_bool_enum = {-1: None, 0: False, 1: True}


@final
class NumericTagPointClass(GenericTagPointClass[float]):
    default_data = 0
    type = "number"

    @validate_args
    def __init__(
        self, name: str, min: float | None = None, max: float | None = None
    ):
        self._vta: tuple[float, float, Any]  # type: ignore

        # Real backing vars for props

        self.default_claim: NumericClaim
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

    def trigger(self):
        """Used for tags with subtype: trigger, for
        things that are triggered on changes to nonzero values.

        this just increments the value, wrapping at
        2**20, and wrapping to 1 instead of 0.
        """

        if self._lock.acquire(timeout=15):
            try:
                v, _t, _a = self._get_value()
                v = v + 1
                if v > self.max:
                    v = 1
                if v > 2**20:
                    v = 1

                self.value = v

            finally:
                self._lock.release()
        else:  # pragma: no cover
            raise RuntimeError(
                "Could not get lock to trigger tagpoint: " + self.name
            )

    def _process_value_for_tag_type(self, value: float | int) -> float:
        value = float(value)

        if self._min is not None:
            value = max(self._min, value)

        if self._max is not None:
            value = min(self._max, value)

        return value

    def claimFactory(
        self,
        value: float,
        name: str,
        priority: float,
        timestamp: float,
        annotation: Any,
    ):
        return NumericClaim(self, value, name, priority, timestamp, annotation)

    @property
    def min(self) -> float | int:
        """Set the range of the tag point. Out of range
        values are clipped. Default is None."""
        return self._min if self._min is not None else -(10**18)

    @min.setter
    @validate_args
    def min(self, v: float | int | None):
        self._min = v
        self.pull()

    @property
    def max(self) -> float | int:
        """Set the range of the tag point. Out of range
        values are clipped. Default is None."""
        return self._max if self._max is not None else 10**18

    @max.setter
    @validate_args
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
    @validate_args
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
    @validate_args
    def lo(self, v: float | int | None):
        if v is None:
            v = -(10**16)
        self._lo = v

    def convert_to(self, unit: str):
        "Return the tag's current value converted to the given unit"
        return convert(self.value, self.unit, unit)

    def convert_value(self, value: float | int, unit: str) -> float | int:
        "Convert a value in the tag's native unit to the given unit"
        return convert(value, self.unit, unit)

    @property
    def unit(self):
        """
        A string that determines the unit of a tag. Units are
        expressed in strings like "m" or "degF". Currently only a small number of
        unit conversions are supported natively and others use pint, which is not as
        fast.

        SI prefixes should not be used in units, as it interferes with
        auto-prefixing for display that meter widgets can do, and generally
        complicates coding.

        This includes kilograms, Grams should be used for internal calculations instead despite Kg being the
        base unit according to SI.


        Note that operations involving units raise an error if the unit is not set.
        To prevent this, both the "sending" and "recieving" code should set the unit
        before using the tag.

        To prevent the very obvious classes of errors where different code thinks a
        unit is a different thing, this property will not allow changes once it has
        been set. You can freely write the same string to it, and you can set it to
        None and then to a new value if you must, but you cannot change between two
        strings without raising an exception.

        For some units, meters will become "unit aware" on the display page.
        """
        return self._unit

    @unit.setter
    def unit(self, value: str):
        value = value.strip()
        if not isinstance(value, str):
            raise TypeError("Unit must be str")

        if self._unit and value:
            if not self._unit == value:
                if value:
                    raise ValueError(
                        "Cannot change unit of tagpoint. To override this, set to None or '' first"
                    )
        # TODO race condition in between check,
        # but nobody will be setting this from different threads
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

    def set_as(
        self,
        value: float,
        unit: str,
        timestamp: float | None = None,
        annotation: Any = None,
    ):
        "Set the default claim, with unit conversion."
        self.default_claim.set_as(value, unit, timestamp, annotation)

    @property
    def display_units(self):
        """
        This can be None, or a pipe-separated string listing one or more units that
        the tag's value should be displayed in. Base SI units imply that the correct
        prefix should be used for readability, but units that contain a prefix imply
        fixed display only in that unit.
        """
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

    @validate_args
    def __init__(self, name: str):
        self._vta: tuple[str, float, Any]  # type: ignore
        self._data_source_ws_lock = threading.Lock()
        super().__init__(name)

    def _process_value_for_tag_type(self, value):
        return str(value)


@final
class ObjectTagPointClass(GenericTagPointClass[dict[str, Any]]):
    default_data: dict[str, Any] = {}
    type = "object"

    @validate_args
    def __init__(self, name: str):
        self._vta: tuple[dict[str, Any], float, Any]  # type: ignore
        self._data_source_ws_lock = threading.Lock()

        self.validate = None
        super().__init__(name)

    def _process_value_for_tag_type(self, value):
        if isinstance(value, str):
            value = json.loads(value)
        else:
            # Just to raise error on invalid JSON
            json.dumps(value)
            value = copy.deepcopy(value)

        return value


@final
class BinaryTagPointClass(GenericTagPointClass[bytes]):
    default_data: bytes = b""
    type = "binary"

    @validate_args
    def __init__(self, name: str):
        self._vta: tuple[bytes, float, Any]  # type: ignore
        self._data_source_ws_lock = threading.Lock()

        super().__init__(name)

    def as_base64(self) -> str:
        return base64.b64encode(self.get_vta()[0]).decode("utf-8")

    def _process_value_for_tag_type(self, value):
        if isinstance(value, bytes):
            value = value
        else:
            value = bytes(value)

        return value


@functools.total_ordering
class Claim(Generic[T]):
    "Represents a claim on a tag point's value"

    @validate_args
    def __init__(
        self,
        tag: GenericTagPointClass[T],
        value: T,
        name: str = "default",
        priority: int | float = 50.0,
        timestamp: int | float | None = None,
        annotation=None,
    ):
        self.name = name
        self.tag = tag
        timestamp = timestamp or time.time()
        self.vta: tuple[T | None, float, Any] = (
            value,
            timestamp,
            annotation,
        )

        # Track the last *attempt* at reading the value if it is a callable, regardless of whether
        # it had new data or not.

        # It is in unix time.
        self.lastGotValue = 0.0

        self.effective_priority = priority

        # The priority set in code, regardless of whether we released or not
        self.priority = priority

        self.poller = None

        self.getter: Callable[[Claim[T]], None] | None = None
        """Getter function for this claim"""

        self.released = False

    def __del__(self):
        if self.name != "default":
            # Must be self.release not self.tag.release or old claims with the same name would
            # mess up new ones. The class method has a check for that.
            self.release()

    def __lt__(self, other):
        if self.released:
            if not other.released:
                return True
        if (self.effective_priority, self.timestamp) < (
            other.priority,
            other.timestamp,
        ):
            return True
        return False

    def __eq__(self, other) -> bool:
        if not self.released == other.released:
            return False
        if not self.effective_priority == other.priority:
            return False
        if not self.timestamp == other.timestamp:
            return False
        return True

    @property
    def value(self) -> T | None:
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
        if timestamp is None:
            timestamp = time.time()
        # Not threadsafe here if multiple threads use the same claim, value, timestamp, and annotation can
        self.vta = (value, timestamp, annotation)

        # In the released state we must do it all over again
        if self.released:
            if self.tag._lock.acquire(timeout=60):
                try:
                    v, t, a = self.vta
                    if v is not None:
                        self.tag.claim(
                            value=v,
                            timestamp=t,
                            annotation=a,
                            priority=self.effective_priority,
                            name=self.name,
                        )
                finally:
                    self.tag._lock.release()
            else:
                raise RuntimeError(
                    "Cannot get lock to re-claim after release, waited 60s"
                )
        else:
            self.tag.set_claim_val(self.name, value, timestamp, annotation)

    def release(self):
        try:
            # Stop any weirdness with an old claim double releasing and thus releasing a new claim
            if self.tag._claims[self.name] is not self:
                # If the old replaced claim is somehow the active omne we actually should handle that
                if self.tag.active_claim is not self:
                    return
        except KeyError:
            return

        self.tag.release(self.name)

    def set_priority(self, priority: float, realPriority: bool = True):
        if self.tag._lock.acquire(timeout=60):
            try:
                if realPriority:
                    self.priority = priority
                self.effective_priority = priority
                v, t, a = self.vta
                if v is not None:
                    self.tag.claim(
                        value=v,
                        timestamp=t,
                        annotation=a,
                        priority=self.effective_priority,
                        name=self.name,
                    )
            finally:
                self.tag._lock.release()

        else:
            raise RuntimeError("Cannot get lock to set priority, waited 60s")

    def __call__(self, *args, **kwargs):
        if not args:
            raise ValueError("No arguments")
        else:
            return self.set(*args, **kwargs)


class NumericClaim(Claim[float]):
    "Represents a claim on a tag point's value"

    @validate_args
    def __init__(
        self,
        tag: NumericTagPointClass,
        value: float | int,
        name: str = "default",
        priority: int | float = 50,
        timestamp: int | float | None = None,
        annotation=None,
    ):
        self.tag: NumericTagPointClass
        Claim.__init__(
            self, tag, float(value), name, priority, timestamp, annotation
        )

    def set_as(
        self,
        value: float | int,
        unit: str,
        timestamp: float | int | None = None,
        annotation: Any = None,
    ):
        "Convert a value in the given unit to the tag's native unit"
        self.set(
            convert(float(value), unit, self.tag.unit), timestamp, annotation
        )


Tag = NumericTagPointClass.Tag
ObjectTag = ObjectTagPointClass.Tag
StringTag = StringTagPointClass.Tag
BinaryTag = BinaryTagPointClass.Tag
