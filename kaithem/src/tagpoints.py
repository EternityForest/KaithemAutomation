from __future__ import annotations
import typing
from . import widgets
from .unitsofmeasure import convert, unit_types
from . import scheduling, workers, messagebus, directories, persist, alerts, taghistorian, util
import time
import threading
import weakref
import logging
import types
import traceback
import math
import os
import gc
import functools
import re
import random
import json
import copy

import dateutil
import dateutil.parser

from typing import Callable, Tuple, Union, Dict, List, Any, Optional, TypeVar, Type, Generic
from typeguard import typechecked


def makeTagInfoHelper(t: GenericTagPointClass[Any]):
    def f():
        x = t.currentSource
        if x == 'default':
            return ''
        else:
            return '(' + x + ')'
    return f


logger = logging.getLogger("tagpoints")
syslogger = logging.getLogger("system")

exposedTags: weakref.WeakValueDictionary[str,
                                         GenericTagPointClass[Any]] = weakref.WeakValueDictionary()

# These are the atrtibutes of a tag that can be overridden by configuration.
# Setting tag.hi sets the runtime property, but we ignore it if the configuration takes precedence.
configAttrs = {'hi', 'lo', 'min', 'max', 'interval', 'displayUnits'}
softConfigAttrs = {
    'overrideName', 'overrideValue', 'overridePriority', 'type', 'value'
}

t = time.monotonic

# This is used for messing with the set of tags.
# We just accept that creating and deleting tags and claims is slow.
lock = threading.RLock()

allTags: Dict[str, weakref.ref[GenericTagPointClass[Any]]] = {}
allTagsAtomic: Dict[str, weakref.ref[GenericTagPointClass[Any]]] = {}

subscriberErrorHandlers: List[Callable[..., Any]] = []

hasUnsavedData = [0]

default_display_units = {
    "temperature": "degC|degF",
    "length": "m",
    "weight": "g",
    "pressure": "psi|Pa",
    "voltage": "V",
    "current": "A",
    "power": "W",
    "frequency": "Hz",
    "ratio": "%",
    "speed": "KPH|MPH"
}


@functools.lru_cache(500, False)
def normalizeTagName(name: str, replacementChar: Optional[str] = None) -> str:
    "Normalize hte name, and raise errors on anything just plain invalid, unless a replacement char is supplied"
    name = name.strip()
    if name == "":
        raise ValueError("Tag with empty name")

    if name[0] in '0123456789':
        raise ValueError("Begins with number")

    # Special case, these tags are expression tags.
    if not name.startswith("="):
        for i in ILLEGAL_NAME_CHARS:
            if i in name:
                if replacementChar:
                    name = name.replace(i, replacementChar)
                else:
                    raise ValueError("Illegal char in tag point name: " + i +
                                     " in " + name)
        if not name.startswith("/"):
            name = "/" + name
    else:
        if name.startswith("/="):
            name = name[1:]

    return name


configTags: Dict[str, object] = {}
configTagData: Dict[str, persist.SharedStateFile | Dict[str, Any]] = {}


def getFilenameForTagConfig(i: str):
    "Given the name of a tag, get the name of it's config file"
    if i.startswith("/"):
        n = i[1:]
    else:
        n = i
    if n.startswith("="):
        n = "=/" + util.url(n[1:])
    return os.path.join(directories.vardir, "tags", n + ".yaml")


def gcEmptyConfigTags():
    torm: List[str] = []
    # Empty dicts can be deleted from disk, letting us just revert to defaultsP
    for i in configTagData:
        if not configTagData[i].getAllData():
            # Can't delete the actual data till the file on disk is gone,
            # Which is handled by the persist libs
            if not os.path.exists(configTagData[i].filename):
                torm.append(i)

    # Note that this is pretty much the only way something can ever be deleted,
    # When it is empty we garbarge collect it.
    # This means we never need to worry about what to keep config data for.
    for i in torm:
        configTagData.pop(i, 0)


# _ and . allowed
ILLEGAL_NAME_CHARS = "{}|\\<>,?-=+)(*&^%$#@!~`\n\r\t\0"

T = TypeVar('T')


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
    DEFAULT_ANNOTATION = '1d289116-b250-482e-a3d3-ffd9e8ac2b57'

    defaultData: T
    type = 'object'
    mqttEncoding = 'json'

    def __repr__(self):
        try:
            return "<Tag Point: " + self.name + "=" + str(
                self._value)[:20] + ">"
        except Exception:
            return "<Tag Point: " + self.name + ">"

    @typechecked
    def __init__(self, name: str):
        global allTagsAtomic
        _name: str = normalizeTagName(name)
        if _name in allTags:
            raise RuntimeError(
                "Tag with this name already exists, use the getter function to get it instead"
            )

        self.kweb_manualOverrideClaim: Optional[Claim]

        # Dependancu tracking, if a tag depends on other tags, such as =expression based ones
        self.sourceTags: Dict[str, GenericTagPointClass[Any]] = {}

        self._value: Callable[..., Optional[T]] | T

        self.dataSourceWidget: Optional[widgets.Widget] = None
        self.dataSourceAutoControl: Optional[widgets.Widget] = None

        # Used for pushing data to frontend
        self.guiLock: threading.Lock
        self.spanWidget: Optional[widgets.DynamicSpan]

        self.description: str = ''
        # True if there is already a copy of the deadlock diagnostics running
        self.testingForDeadlock: bool = False

        self.alreadyPostedDeadlock: bool = False

        # This string is just used to stash some extra info
        self._subtype: str = ''

        # If true, the tag represents an input not meant to be written to except by the owner.
        # It can however still be overridden.  This is just a widget advisory.
        self.is_input_only = False

        # Start timestamp at 0 meaning never been set
        # Value, timestamp, annotation.  This is the raw value,
        # and the value could actually be a callable returning a value
        self.vta: Tuple[T, float, Any] = (copy.deepcopy(self.defaultData), 0, None)

        # Used to track things like min and max, what has been changed by manual setting.
        # And should not be overridden by code.

        # We use excel-style "if it looks loke a number, it is", to simplify web based input for this one.
        self.configOverrides: Dict[str, object] = {}

        self._dynConfigValues: Dict[str, object] = {}
        self.dynamicAlarmData: Dict[str, object] = {}
        self.configuredAlarmData: Dict[str, persist.SharedStateFile] = {}
        # The merged combo of both of those
        self.effectiveAlarmData: Dict[str, object] = {}

        self.alarms: Dict[str, alerts.Alert] = {}

        self._configuredAlarms: Dict[str, object] = {}

        # In unreliable mode the tag's acts like a simple UDP connection.
        # The only supported feature is that writing the tag notifies subscribers.
        # It is not guaranteed to store the last value, to error check the value,
        # To prevent multiple writes at the same time, and the claims may be ignored.

        # Subscribing the tag directly to another tga uses fastPush that bypasses all claims.
        # In unreliable mode you should only use fastPush to set values.

        self.unreliable: bool = False

        # Track the recalc function used by the poller, the poller itself, and the recalc alarm subscrie
        # function subscribed to us, respectively

        # The last is a function that is used as a subscriber which just causes the tag to be recalced.
        # We give that to other tags in case the alarm polling depends on other tags.

        # We need it so we don't get GCed
        self._alarmGCRefs: Dict[str, Tuple[Callable[..., Any], object, Callable[..., Any],
                                           Callable[..., Any]]] = {}

        self.name: str = _name
        # The cached actual value from the claims
        self.cachedRawClaimVal: T = copy.deepcopy(self.defaultData)
        # The cached output of processValue
        self.lastValue: T = self.cachedRawClaimVal
        # The real current in use val, after the config override logic
        self._interval: Union[float, int] = 0
        self.activeClaim: Union[None, Claim] = None
        self.claims: Dict[str, Claim] = {}
        self.lock = threading.RLock()
        self.subscribers: List[weakref.ref[Callable[..., Any]]] = []

        # This is only used for fast stream mode
        self.subscribers_atomic: List[weakref.ref[Callable[..., Any]]] = []

        self.poller: Union[None, Callable[..., Any]] = None

        # The "Owner" of a tag can use this to say if anyone else should write it
        self.writable = True

        # When was the last time we got *real* new data
        self.lastGotValue: Union[int, float] = 0

        self.lastError: Union[float, int] = 0

        # String describing the "owner" of the tag point
        # This is not a precisely defined concept
        self.owner: str = ""

        self.handler: typing.Optional[typing.Callable[..., Any]] = None

        from . import kaithemobj

        if hasattr(kaithemobj.kaithem.context, 'event'):
            self.originEvent = kaithemobj.kaithem.context.event
        else:
            self.originEvent = None

        # Used for the expressions in alert conditions and such
        self.evalContext: Dict[str, Any] = {
            "math": math,
            "time": time,
            # Cannot reference ourself strongly.  We want to avoid laking any references to tht tags
            # go away cleanly
            'tag': weakref.proxy(self),
            're': re,
            'kaithem': kaithemobj.kaithem,
            'random': random,

            # It is perfect;y fine that these reference ourself, because when we pass this to an alarm,
            # We have alarm specific ones.
            'tv': self.contextGetNumericTagValue,
            'stv': self.contextGetStringTagValue,
            'dateutil': dateutil
        }
        try:
            import numpy as np
            self.evalContext['np'] = np
        except ImportError:
            pass

        self.lastPushedValue: Optional[float] = None
        self.onSourceChanged: Union[typing.Callable[..., Any], None] = None

        with lock:
            allTags[_name] = weakref.ref(self)
            allTagsAtomic = allTags.copy()

        # This pushes a value. That is fine because we know there are no listeners
        self.defaultClaim = self.claim(copy.deepcopy(self.defaultData),
                                       'default',
                                       timestamp=0,
                                       annotation=self.DEFAULT_ANNOTATION)

        # Reset this so that any future value sets actually do push.  First write should always push
        # Independent of change detection.
        self.lastPushedValue = None

        # What permissions are needed to
        # read or override this tag, as a tuple of 2 permission strings and an int representing the priority
        # that api clients can use.
        # As always, configured takes priority
        self.permissions = ['', '', 50]
        self.configuredPermissions = ['', '', 50]

        self.apiClaim: Union[None, Claim] = None

        # This is where we can put a manual override
        # claim from the web UI.
        self.manualOverrideClaim: Union[None, Claim] = None

        self._alarms: Dict[str, object] = {}

        # Used for storing the full config data set including stuff we shouldn't save
        self._runtimeConfigData = {}

        with lock:
            messagebus.post_message("/system/tags/created",
                                   self.name,
                                   synchronous=True)

        if self.name.startswith("="):
            self.exprClaim = createGetterFromExpression(self.name, self)
            self.writable = False
        with lock:
            d: Any = configTagData.get(self.name, {})
            if hasattr(d, 'data'):
                d = d.data.copy()
            self.setConfigData(d)

    @property
    def meterWidget(self):
        """Hack to get around code that calls meterWidget 
        but that should have been able to handle span widgets. Will look bad but not break"""
        return self.spanWidget

    # In reality value, timestamp, annotation are all stored together as a tuple

    @property
    def timestamp(self) -> float:
        return self.vta[1]

    @property
    def annotation(self) -> Any:
        return self.vta[2]

    def isDynamic(self) -> bool:
        return callable(self.vta[0])

    @typechecked
    def expose(self,
               read_perms: str | List[str] = '',
               write_perms: str | List[str] = '__never__',
               expose_priority: Union[str, int] = 50,
               configured: bool = False):
        """If not r, disable web API.  Otherwise, set read and write permissions.
           If configured permissions are set, they totally override code permissions.
           Empty configured perms fallback tor runtime

        """

        if isinstance(read_perms, list):
            read_perms = ','.join(read_perms)
        else:
            read_perms = read_perms.strip()
        if isinstance(write_perms, list):
            write_perms = ','.join(write_perms)
            write_perms = write_perms.strip()

        # Handle different falsy things someone might use to try and disable this
        if not read_perms:
            read_perms = ''
        if not write_perms:
            write_perms = '__never__'

        # Just don't allow numberlike permissions so we can keep
        # pretending any config item that looks like a number, is.
        # Also, why would anyone do that?
        for i in read_perms.split(",") + write_perms.split(","):
            try:
                float(i)
                raise RuntimeError("Permission: " + str(i) +
                                   " looks like a number")
            except ValueError:
                pass

        if not expose_priority:
            expose_priority = 50
        # Make set we don't somehow save bad data and break everything
        expose_priority = int(expose_priority)
        write_perms = str(write_perms)
        read_perms = str(read_perms)

        if not read_perms or not write_perms:
            d = ['', '', 50]
            emptyPerms = True
        else:
            emptyPerms = False
            d = [read_perms, write_perms, expose_priority]

        with lock:
            with self.lock:
                if configured:
                    self.configuredPermissions = d

                    self._recordConfigAttr('permissions',
                                           d if not emptyPerms else None)
                    hasUnsavedData[0] = True
                else:
                    self.permissions = d

                # Merge config and direct
                d2 = self.getEffectivePermissions()

                # Be safe, only allow writes if user specifies a permission
                d2[1] = d2[1] or '__never__'

                if not d2[0]:
                    self.dataSourceWidget = None
                    self.dataSourceAutoControl = None
                    try:
                        del exposedTags[self.name]
                    except KeyError:
                        pass
                    if self.apiClaim:
                        self.apiClaim.release()
                else:
                    w = widgets.DataSource(id="tag:" + self.name)

                    if self.unreliable:
                        w.noOnConnectData = True

                    # The tag.control version is exactly the same but output-only,
                    #  so you can have a synced UI widget that
                    # can store the UI setpoint state even when the actual tag is overriden.
                    self.dataSourceAutoControl = widgets.DataSource(
                        id="tag.control:" + self.name)
                    self.dataSourceAutoControl.write(None)
                    w.set_permissions([i.strip() for i in d2[0].split(",")],
                                     [i.strip() for i in d2[1].split(",")])

                    self.dataSourceAutoControl.set_permissions(
                        [i.strip() for i in d2[0].split(",")],
                        write=[i.strip() for i in d2[1].split(",")])
                    w.value = self.value

                    exposedTags[self.name] = self
                    if self.apiClaim:
                        self.apiClaim.setPriority(expose_priority)
                    self._apiPush()

                    # We don't want the web connection to be able to keep the tag alive
                    # so don't give it a reference to us
                    self._weakApiHandler = self.makeWeakApiHandler(
                        weakref.ref(self))
                    w.attach(self._weakApiHandler)
                    self.dataSourceAutoControl.attach(self._weakApiHandler)

                    self.dataSourceWidget = w

    @staticmethod
    def makeWeakApiHandler(wr):
        def f(u, v):
            wr().apiHandler(u, v)

        return f

    def apiHandler(self, u, v: Optional[T]):
        if v is None:
            if self.apiClaim:
                self.apiClaim.release()
        else:
            # No locking things up if the times are way mismatched and it sets a time way in the future
            self.apiClaim = self.claim(
                v,
                'WebAPIClaim',
                priority=(self.getEffectivePermissions())[2],
                annotation=u)

            # They tried to set the value but could not, so inform them of such.
            if not self.currentSource == self.apiClaim.name:
                self._apiPush()

    def controlApiHandler(self, u, v: Optional[T]):
        assert self.dataSourceAutoControl

        if v is None:
            if self.apiClaim:
                self.apiClaim.release()
        else:
            # No locking things up if the times are way mismatched and it sets a time way in the future
            self.apiClaim = self.claim(
                v,
                'WebAPIClaim',
                priority=(self.getEffectivePermissions())[2],
                annotation=u)

            # They tried to set the value but could not, so inform them of such.
            if not self.currentSource == self.apiClaim.name:
                self._apiPush()

        self.dataSourceAutoControl.write(v)

    def getEffectivePermissions(self) -> List[str]:
        """
        Get the permissions that currently apply here. Configured ones override in-code ones

        Returns:
            list: [readPerms, writePerms, writePriority]. Priority determines the priority of web API claims.
        """
        d2 = [
            self.configuredPermissions[0] or self.permissions[0],
            self.configuredPermissions[1] or self.permissions[1],
            self.configuredPermissions[2] or self.permissions[2]
        ]

        # Block exposure at all if the permission is never
        if '__never__' in d2[0]:
            d2[0] = ''
            d2[1] = ''

        return d2

    def _apiPush(self):
        "If the expose function was used, push this to the dataSourceWidget"
        if not self.dataSourceWidget:
            return

        # Immediate write, don't push yet, do that in a thread because TCP can block
        def pushFunction():
            # Set value immediately, for later page loads
            assert self.dataSourceWidget
            self.dataSourceWidget.value = self.value
            if self.guiLock.acquire(timeout=1):
                try:
                    # Use the new literal computed value, not what we were passed,
                    # Because it could have changed by the time we actually get to push
                    self.dataSourceWidget.send(self.value)
                finally:
                    self.guiLock.release()

        # Should there already be a function queued for this exact reason, we just let
        # That one do it's job
        if self.guiLock.acquire(timeout=0.001):
            try:
                workers.do(pushFunction)
            finally:
                self.guiLock.release()

    def testForDeadlock(self):
        "Run a check in the background to make sure this lock isn't clogged up"

        def f():
            # Approx check, more than one isn't the worst thing
            if self.testingForDeadlock:
                return

            self.testingForDeadlock = True

            if self.lock.acquire(timeout=30):
                self.lock.release()
            else:
                if not self.alreadyPostedDeadlock:
                    messagebus.post_message(
                        "/system/notifications/errors",
                        "Tag point: " + self.name +
                        " has been unavailable for 30s and may be involved in a deadlock. see threads view."
                    )
                    self.alreadyPostedDeadlock = True

            self.testingForDeadlock = False

        workers.do(f)

    def _recordConfigAttr(self, k: str, v: Any):
        "Make sure a config attr setting gets saved"

        # If it looks like a number, it is.  That makes the code simpler for dealing
        # With web inputs and assorted things like that in a uniform way without needing to
        # special case based on the attribute name
        try:
            v = float(v)
        except ValueError:
            pass
        except TypeError:
            pass

        # Reject various kinds of empty, like None, empty strings, all whitespace.
        # Treat them as meaning to get rid of the attr
        if v not in (None, '') and (v.strip() if isinstance(v, str) else True):
            self.configOverrides[k] = v
            if self.name not in configTagData:
                configTagData[self.name] = persist.getStateFile(
                    getFilenameForTagConfig(self.name))
                configTagData[self.name][k] = v
                configTagData[self.name].noFileForEmpty = True
            configTagData[self.name][k] = v
        else:
            # Setting at attr to none or an empty string
            # Deletes it.
            self.configOverrides.pop(k, 0)
            if self.name in configTagData:
                configTagData[self.name].pop(k, 0)

    def recalc(self, *a):
        "Just re-get the value as needed"
        # It's a getter, ignore the mypy unused thing.
        self.poll()

    def contextGetNumericTagValue(self, n: str) -> float:
        "Get the tag value, adding it to the list of source tags. Creates tag if it isn't there"
        try:
            return self.sourceTags[n].value
        except KeyError:
            self.sourceTags[n] = Tag(n)
            # When any source tag updates, we want to recalculate.
            self.sourceTags[n].subscribe(self.recalc)
            return self.sourceTags[n].value
        return 0

    def contextGetStringTagValue(self, n: str) -> str:
        "Get the tag value, adding it to the list of source tags. Creates tag if it isn't there"
        try:
            return self.sourceTags[n].value
        except KeyError:
            self.sourceTags[n] = StringTag(n)
            # When any source tag updates, we want to recalculate.
            self.sourceTags[n].subscribe(self.recalc)
            return self.sourceTags[n].value
        return 0

    def setConfigAttr(self, k: str, v: Any):
        "Sets the configured attribute by name, and also sets the corresponding dynamic attribute."

        if k not in configAttrs:
            raise ValueError(k +
                             " does not support overriding by configuration")

        with lock:
            self._recordConfigAttr(k, v)
            if isinstance(v, str):
                if v.strip() == '':
                    v = None
                else:
                    try:
                        v = float(v)
                    except Exception:
                        # Can't use pass or it will trigger the linter
                        v = v
            # Attempt to go back to the values set by code
            if v is None:
                v = self._dynConfigValues.get(k, v)

            # For all the config attrs, setting the property sets the dynamic attr.
            # But WE also want to invoke all the side effects of setting the prop when we reconfigure.
            # As a hack, we save and restore that value, so that we preserve the original un-configured val.

            x = self._dynConfigValues.get(k, None)

            setattr(self, k, v)

            # Restore TODO race condition here!!!!!!
            # We get the old dyn val if it is set by another thread in between
            self._dynConfigValues[k] = x

            hasUnsavedData[0] = True

    # Note the black default condition, that lets us override a normal alarm while using the default condition.
    @typechecked
    def setAlarm(self,
                 name: str,
                 condition: Optional[str] = '',
                 priority: str = "info",
                 releaseCondition: Union[str, None] = '',
                 auto_ack: Union[bool, str] = 'no',
                 trip_delay: Union[float, str] = '0',
                 isConfigured: bool = False,
                 _refresh: bool = True):
        with lock:
            if not name:
                raise RuntimeError("Empty string name")

            if auto_ack is True:
                auto_ack = 'yes'
            if auto_ack is False:
                auto_ack = 'no'

            trip_delay = str(trip_delay)

            d = {
                'condition': condition,
                'priority': priority,
                'auto_ack': auto_ack,
                'trip_delay': trip_delay,
                'releaseCondition': releaseCondition
            }

            # Remove empties to make way for defaults
            d = {i: d[i] for i in d if d[i]}

            if isConfigured:
                if not isinstance(condition, str) and condition is not None:
                    raise ValueError(
                        "Configurable alarms only allow str or none condition")
                hasUnsavedData[0] = True

                storage = self.configuredAlarmData
            else:
                storage = self.dynamicAlarmData
                # Dynamics are weak reffed
                if not _refresh:
                    # This is because we need somewhere to return the strong ref
                    raise RuntimeError(
                        "Cannot create dynamic alarm without the refresh option"
                    )

            if condition is None:
                try:
                    storage.pop(name, 0)
                except Exception:
                    logger.exception("I don't think this matters")
            else:
                storage[name] = d

            # If we have configured alarms, there should be a configTagData entry.
            # If not, delete, because when that is empty it's how we know
            # to delete the actual file
            if isConfigured:
                if self.configuredAlarmData:
                    if self.name not in configTagData:
                        configTagData[self.name] = persist.getStateFile(
                            getFilenameForTagConfig(self.name))
                        configTagData[self.name].noFileForEmpty = True

                configTagData[self.name]['alarms'] = self.configuredAlarmData

            if _refresh:
                x = self.createAlarm(name)
                if x and not isConfigured:
                    # Alarms have to have a reference to the config data
                    x.tagpoint_config_data = d
                    x.tagpoint_name = self.name
                    return x

    def clearDynamicAlarms(self):
        with lock:
            if self.dynamicAlarmData:
                self.dynamicAlarmData.clear()
                self.createAlarms()

    # TODO when there's time, refactor so createAlarms calls createAlarm
    def createAlarm(self, name: str) -> alerts.Alert:
        x = self.createAlarms(name)
        assert isinstance(x, alerts.Alert)
        return x

    def createAlarms(self, limitTo: Optional[str] = None):
        merged: Dict[str, Dict[str, Dict[str, Any]]] = {}
        with lock:
            # Combine the merged and configured alarms
            # at a granular per-attribute level

            for i in self.dynamicAlarmData:
                d = self.dynamicAlarmData[i]
                if d:
                    merged[i] = merged.get(i, {})
                    for j in d:
                        merged[i][j] = d[j]

            for i in self.configuredAlarmData:
                merged[i] = merged.get(i, {})
                for j in self.configuredAlarmData[i]:
                    merged[i][j] = self.configuredAlarmData[i][j]

            self.effectiveAlarmData = merged.copy()

            # Cancel all existing alarms
            for i in self.alarms:
                a = self.alarms[i]
                if a:
                    if not limitTo or i == limitTo:

                        # This is the polling function, the poller, and the subscriber
                        pollStuff = self._alarmGCRefs.pop(i, None)

                        if pollStuff:
                            try:
                                self.unsubscribe(pollStuff[2])
                            except Exception:
                                logger.exception("Maybe already unsubbed?")

                            # This is the poller for polling even when there is no change, at a very low rate,
                            # To catch any edge cases not caught by watching tag changes
                            try:
                                pollStuff[1].unregister()
                            except Exception:
                                logger.exception("Maybe already unsubbed?")

                        a.release()

            if not limitTo:
                self.alarms = {}
                self._configuredAlarms = {}
            else:
                self.alarms.pop(limitTo, 0)
                self._configuredAlarms.pop(limitTo, 0)

            for i in merged:
                if not limitTo or i == limitTo:
                    d = merged[i]
                    self._alarmFromData(i, d)

            if limitTo and limitTo in self.alarms:
                return self.alarms[limitTo]

    @staticmethod
    def _makeTagAlarmHTMLFunc(selfwr):
        def notificationHTML():
            try:
                if hasattr(selfwr(), "meterWidget"):
                    return selfwr().meterWidget.render()
                elif hasattr(selfwr(), "spanWidget"):
                    return selfwr().spanWidget.render()
                else:
                    return "Binary Tagpoint"
            except Exception as e:
                return str(e)

        return notificationHTML

    @staticmethod
    def _getAlarmContextGetters(obj, context: dict, recalc: Callable):
        # Note that it these go to an alarm which is held if active, or another tag that could be held elsewhere
        # It cannot reference any tag directly or preserve any references, we would not want that.

        # that could keep this tag alive long after it should be gone

        # Functions used for getting other tag values

        # You must keep a reference to recalc2 locally!!!!!!!!!

        #

        def recalc2(*a, **k):
            recalc()()

        def contextGetNumericTagValue(n):
            """Since an alarm can use values from other tags, we must track those values, and from there
                recalc the alarm whenever they should change.
            """
            if n in obj.sourceTags:
                t = obj.sourceTags[n]()
                if t:
                    return t.value

            t = Tag(n)
            obj.sourceTags[n] = weakref.ref(t)
            # When any source tag updates, we want to recalculate.
            obj.sourceTags[n]().subscribe(obj.recalcFunction)
            return t.value

        def contextGetStringTagValue(n):
            """Since an alarm can use values from other tags, we must track those values, and from there
                recalc the alarm whenever they should change.
            """
            if n in obj.sourceTags:
                t = obj.sourceTags[n]()
                if t:
                    return t.value

            t = StringTag(n)
            obj.sourceTags[n] = weakref.ref(t)
            # When any source tag updates, we want to recalculate.
            obj.sourceTags[n].subscribe(obj.recalcFunction)
            return t.value

        context['tv'] = contextGetNumericTagValue
        context['stv'] = contextGetStringTagValue

        return recalc2

    @typechecked
    def _alarmFromData(self, name: str, d: dict):
        if not d.get("condition", ''):
            return

        if d.get("condition", '').strip() in ("False", "None", "0"):
            return
        tripCondition = d['condition']

        releaseCondition = d.get('releaseCondition', None)

        priority = d.get("priority", "warning") or 'warning'
        auto_ack = d.get("auto_ack", '').lower() in ('yes', 'true', 'y', 'auto')
        trip_delay = float(d.get("trip_delay", 0) or 0)

        # Shallow copy, because we are going to override the tag getter
        context = copy.copy(self.evalContext)

        tripCondition = compile(tripCondition,
                                self.name + ".alarms." + name + "_trip",
                                "eval")
        if releaseCondition:
            releaseCondition = compile(
                releaseCondition, self.name + ".alarms." + name + "_release",
                "eval")

        n = self.name.replace("=", 'expr_')
        for i in ILLEGAL_NAME_CHARS:
            n = n.replace(i, "_")

        # This is technically unnecessary, the weakref/GC based cleanup could handle it eventually,
        # But we want a real complete guarantee that it happens *right now*
        oldAlert = self.alarms.get(name, None)
        try:
            if oldAlert:
                for i in oldAlert.sourceTags:
                    try:
                        oldAlert.sourceTags[i]().unsubscribe(
                            oldAlert.recalcFunction)
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

        obj = alerts.Alert(
            n + ".alarms." + name,
            priority=priority,
            auto_ack=auto_ack,
            trip_delay=trip_delay,
        )
        # For debugging reasons
        obj.tagEvalContext = context

        obj.sourceTags = {}

        # We don't need to weakref-ify this directly, as it just goes to the poller and the poller doesn't
        # keep strong references.

        def alarmRecalcFunction(*a):
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
                    obj.trip("Tag value:" + str(context['value'])[:128])
                elif releaseCondition:
                    if eval(releaseCondition, context, context):
                        obj.release()
                else:
                    obj.release()
            except Exception as e:
                obj.error(str(e))
                raise

        def alarmPollFunction(value, timestamp, annotation):
            "Given a new tag value, recalc the alarm expression"
            context['value'] = value
            context['timestamp'] = timestamp
            context['annotation'] = annotation

            alarmRecalcFunction()

        obj.notificationHTML = self._makeTagAlarmHTMLFunc(weakref.ref(self))

        generatedRecalcFuncWeMustKeepARefTo = self._getAlarmContextGetters(
            obj, context, weakref.ref(alarmRecalcFunction))

        self._alarmGCRefs[name] = (alarmRecalcFunction,
                                   scheduling.scheduler.scheduleRepeating(
                                       alarmRecalcFunction, 60,
                                       sync=False), alarmPollFunction,
                                   generatedRecalcFuncWeMustKeepARefTo)

        # Do it with this indirection so that it doesn't do anything
        # bad with some kind of race when we delete things, and so that it doesn't hold references
        def recalcPoll(*a):
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
            logger.exception("Error in test run of alarm function for :" +
                             name)
            messagebus.post_message(
                "/system/notifications/errors",
                "Error with tag point alarm\n" + traceback.format_exc())

        return alarmPollFunction

    def setConfigData(self, data: Dict[str, Any]):
        with lock:
            hasUnsavedData[0] = True
            # New config, new chance to see if there's a problem.
            self.alreadyPostedDeadlock = False
            self._runtimeConfigData.update(data)

            if data and self.name not in configTagData:
                configTagData[self.name] = persist.getStateFile(
                    getFilenameForTagConfig(self.name))
                configTagData[self.name].noFileForEmpty = True

            if 'type' in data:
                if data['type'] == 'number' and not isinstance(
                        self, NumericTagPointClass):
                    raise RuntimeError(
                        "Tag already exists and is not a numeric tag")
                if data['type'] == 'string' and not isinstance(
                        self, StringTagPointClass):
                    raise RuntimeError(
                        "Tag already exists and is not a string tag")
                if data['type'] == 'object' and not isinstance(
                        self, ObjectTagPointClass):
                    raise RuntimeError(
                        "Tag already exists and is not an object tag")

            # Only modify tags if the current data matches the existing
            # Configured value and has not beed overwritten by code
            for i in configAttrs:
                if i in data:
                    self.setConfigAttr(i, data[i])
                else:
                    self.setConfigAttr(i, None)

            for i in softConfigAttrs:
                if i in data:
                    self._recordConfigAttr(i, data[i])
                else:
                    self._recordConfigAttr(i, None)

            # The type field is what determines a tag that can be
            # created purely through config
            if data.get("type", None):
                configTags[self.name] = self
            else:
                # Pop from that storage, this shouldn't exist if there is no
                # external reference
                configTags.pop(self.name, 0)

            loggers = data.get('loggers', [])

            if loggers:
                self._recordConfigAttr("loggers", loggers)
            else:
                self._recordConfigAttr("loggers", None)

            self.configLoggers = []
            for i in loggers:
                interval = float(i.get("interval", 60) or 60)
                target = i.get("target", "disk")

                length = float(
                    i.get("historyLength", 3 * 30 * 24 * 3600)
                    or 3 * 30 * 24 * 3600)

                accum = i['accumulate']
                try:
                    if target not in ("disk", "ram"):
                        raise ValueError("Bad logging target :" + target)

                    c = taghistorian.accumTypes[accum](self, interval, length,
                                                       target)
                    self.configLoggers.append(c)
                except Exception:
                    messagebus.post_message(
                        "/system/notifications/errors",
                        "Error creating logger for: " + self.name + "\n" +
                        traceback.format_exc())

            # this is apparently just for the configured part, the dynamic part happens behind the scenes in
            # setAlarm via createAlarma
            alarms = data.get('alarms', {})
            self.configuredAlarmData = {}
            for i in alarms:
                if alarms[i]:
                    # Avoid duplicate param
                    alarms[i].pop('name', '')
                    self.setAlarm(i,
                                  **alarms[i],
                                  isConfigured=True,
                                  _refresh=False)
                else:
                    self.setAlarm(i, None, isConfigured=True, _refresh=False)

            # This one is a little different. If the timestamp is 0,
            # We know it has never been set.
            if 'value' in data:
                if not str(data['value']).strip() == '':
                    configTagData[self.name]['value'] = str(data['value'])

                    if self.timestamp == 0:
                        # Set timestamp to 0, this marks the tag as still using a default
                        # Which can be further changed
                        self.setClaimVal("default", str(data['value']), 0,
                                         "Configured default")
                else:
                    if self.timestamp == 0:
                        # Set timestamp to 0, this marks the tag as still using a default
                        # Which can be further changed
                        self.setClaimVal("default", str(self.default), 0,
                                         "Configured default")
            else:
                if self.name in configTagData:
                    configTagData[self.name].pop("value", 0)

            # Todo there's a duplication here, we refresh allthe alarms, not sure we need to
            self.createAlarms()

            # Delete any existing configured value override claim
            if hasattr(self, 'kweb_manualOverrideClaim'):
                toRelease = self.kweb_manualOverrideClaim
            else:
                toRelease = None

            # Val override last, in case it triggers an alarm
            # Convert to string for consistent handling, the config engine things anything that looks like a number, is.
            overrideValue = str(data.get('overrideValue', '')).strip()
            tempOverrideValue = str(data.get('tempOverrideValue', '')).strip()

            if self.type == "binary":
                try:
                    overrideValue = bytes.fromhex(overrideValue)
                except Exception:
                    logging.exception("Bad hex in tag override")
                    overrideValue = b''

                try:
                    tempOverrideValue = bytes.fromhex(tempOverrideValue)
                except Exception:
                    logging.exception("Bad hex in tag override")
                    overrideValue = b''

            if overrideValue:
                if overrideValue.startswith("="):
                    self.kweb_manualOverrideClaim = self.createGetterFromExpression(
                        overrideValue, self,
                        int(data.get('overridePriority', '') or 90))
                else:
                    self.kweb_manualOverrideClaim = self.claim(
                        overrideValue, data.get('overrideName', 'config'),
                        int(data.get('overridePriority', '') or 90))
            else:
                self.kweb_manualOverrideClaim = None

            # We already replaced it because we use the same name, don't release the one we just made.
            # Only need to release if going to no override.
            if toRelease and self.kweb_manualOverrideClaim is not toRelease:
                toRelease.release()
                toRelease = None

            # #################### Temp stuff ##############################

            # Delete any existing configured temporary value override claim
            # I think two should really be enough, a temp and a permanent.
            if hasattr(self, 'kweb_tempManualOverrideClaim'):
                toRelease = self.kweb_tempManualOverrideClaim
            else:
                toRelease = None

            if tempOverrideValue:
                self.kweb_tempManualOverrideClaim = self.claim(
                    tempOverrideValue,
                    "kwebtempmanualoverride",
                    int(data.get('tempOverridePriority', '') or 90),
                    expiration=int(data.get('tempOverrideLength', '') or 90))
            else:
                self.kweb_tempManualOverrideClaim = None

            # We already replaced it because we use the same name, don't release the one we just made.
            # Only need to release if going to no override.
            if toRelease and not self.kweb_tempManualOverrideClaim is toRelease:
                toRelease.release()
                toRelease = None

            ##############################################################

            p = data.get('permissions', ('', '', ''))
            # Set configured permissions, overriding runtime
            self.expose(*p, configured=True)

    @property
    def interval(self):
        return self._interval

    @interval.setter
    def interval(self, val):

        self._dynConfigValues['interval'] = val

        # Config tages priority over code
        if not val == self.configOverrides.get('interval', val):
            return
        if val is not None:
            self._interval = val
        else:
            self._interval = 0

        messagebus.post_message("/system/tags/interval" + self.name,
                               self._interval,
                               synchronous=True)
        with self.lock:
            self._managePolling()

    @property
    def subtype(self):
        return self._subtype

    @subtype.setter
    def subtype(self, val):
        self._subtype = val
        if val == 'bool':
            self.min = 0
            self.max = 1

    @property
    def default(self):
        return self._default

    @default.setter
    def default(self, val):
        self._dynConfigValues['default'] = val
        if not val == self.configOverrides.get('value', val):
            return
        if val is not None:
            self._default = val
        else:
            self._default = 0

        with self.lock:
            if self.timestamp == 0:
                # Set timestamp to 0, this marks the tag as still using a default
                # Which can be further changed
                self.setClaimVal("default", float(self._default), 0,
                                 "Code default")

    @classmethod
    def Tag(cls, name: str, defaults: Dict[str, Any] = {}):
        name: str = normalizeTagName(name)
        rval = None
        with lock:
            if name in allTags:
                x = allTags[name]()
                if x:
                    if x.__class__ is not cls:
                        raise TypeError(
                            "A tag of that name exists, but it is the wrong type. Existing: "
                            + str(x.__class__) + " New: " + str(cls))
                    rval = x

            if not rval:
                rval = cls(name)

            assert isinstance(rval, cls)
            return rval

    @property
    def currentSource(self) -> str:

        # Avoid the lock by using retru in case claim disappears
        for i in range(0, 1000):
            try:
                return self.activeClaim().name
            except Exception:
                time.sleep(0.001)
        return self.activeClaim().name

    def filterValue(self, v):
        "Pure function that returns a cleaned up or normalized version of the value"
        return v

    def __del__(self):
        global allTagsAtomic
        with lock:
            try:
                del allTags[self.name]
                allTagsAtomic = allTags.copy()
            except Exception:
                logger.exception("Tag may have already been deleted")
            messagebus.post_message("/system/tags/deleted",
                                   self.name,
                                   synchronous=True)

    def __call__(self, *args, **kwargs):
        if not args:
            return self.value
        else:
            return self.setClaimVal('default', *args, **kwargs)

    def interface(self):
        "Override the VResource thing"
        # With no replacement or master objs, we just return self
        return self

    def _managePolling(self):
        interval = self._interval or 0
        if (self.subscribers or self.handler) and interval > 0:
            if not self.poller or not (interval == self.poller.interval):
                if self.poller:
                    self.poller.unregister()
                    self.poller = None

                self.poller = scheduling.scheduler.scheduleRepeating(
                    self.poll, interval, sync=False)
        else:
            if self.poller:
                self.poller.unregister()
                self.poller = None

    def fastPush(self, value, timestamp=None, annotation=None):
        """
            Push a value to all subscribers. Does not set the tag's value.
            Bypasses all claims. Does not guarantee to get any locks, multiples of this call can happen at once.
            Does not perform any checks on the value.

            Meant for streaming video analysis.
        """

        timestamp = timestamp or time.monotonic()

        for i in self.subscribers_atomic:
            f = i()
            if f:
                f(value, timestamp, annotation)

        if not self.dataSourceWidget:
            return

        # Set value immediately, for later page loads
        if self.guiLock.acquire(timeout=0.3):
            try:
                # Use the new literal computed value, not what we were passed,
                # Because it could have changed by the time we actually get to push
                self.dataSourceWidget.send(value)

            except Exception:
                raise
            finally:
                self.guiLock.release()
        else:
            print("Timed out in the push function")

    @typechecked
    def subscribe(self, f: Callable, immediate=False):

        if isinstance(f, GenericTagPointClass) and (f.unreliable or self.unreliable):
            f = f.fastPush

        timestamp = time.monotonic()

        try:
            desc = str(f.__name__ + ' of ' + f.__module__)
        except Exception:
            desc = str(f)

        timestamp = time.monotonic()

        def errcheck(*a):
            if time.monotonic() < timestamp - 0.5:
                logging.warning(
                    "Function: " + desc +
                    " was deleted 0.5s after being subscribed.  This is probably not what you wanted."
                )

        if self.lock.acquire(timeout=20):
            try:

                ref: Union[weakref.WeakMethod, weakref.ref, None] = None

                if isinstance(f, types.MethodType):
                    ref = weakref.WeakMethod(f, errcheck)
                else:
                    ref = weakref.ref(f, errcheck)

                for i in self.subscribers:
                    if f == i():
                        syslogger.warning(
                            "Double subscribe detected, same function subscribed to "
                            + self.name +
                            " more than once.  Only the first takes effect.")
                        self._managePolling()
                        return

                self.subscribers.append(ref)

                torm = []
                for i in self.subscribers:
                    if not i():
                        torm.append(i)
                for i in torm:
                    self.subscribers.remove(i)
                messagebus.post_message("/system/tags/subscribers" + self.name,
                                       len(self.subscribers),
                                       synchronous=True)

                if immediate and self.timestamp:
                    f(self.value, self.timestamp, self.annotation)
                self._managePolling()

                self.subscribers_atomic = copy.copy(self.subscribers)
            finally:
                self.lock.release()
        else:
            self.testForDeadlock()
            raise RuntimeError(
                "Cannot get lock to subscribe to this tag. Is there a long running subscriber?"
            )

    @typechecked
    def unsubscribe(self, f: Callable):
        if self.lock.acquire(timeout=20):
            try:
                x = None
                for i in self.subscribers:
                    if i() == f:
                        x = i
                if x:
                    self.subscribers.remove(x)
                messagebus.post_message("/system/tags/subscribers" + self.name,
                                       len(self.subscribers),
                                       synchronous=True)
                self._managePolling()
                self.subscribers_atomic = copy.copy(self.subscribers)
            finally:
                self.lock.release()
        else:
            self.testForDeadlock()
            raise RuntimeError(
                "Cannot get lock to subscribe to this tag. Is there a long running subscriber?"
            )

    @typechecked
    def setHandler(self, f: Callable):
        self.handler = weakref.ref(f)

    def _debugAdminPush(self, value, t, a):
        pass

    def poll(self):
        if self.lock.acquire(timeout=5):
            try:
                self._getValue()
                self._push()
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
        if self.lastValue == self.lastPushedValue:
            if self.timestamp:
                return

        # Note the difference with the handler.
        # It is called synchronously, right then and there
        if self.handler:
            f = self.handler()
            if f:
                f(self.lastValue, self.timestamp, self.annotation)
            else:
                self.handler = None

        self._apiPush()

        self.lastPushedValue = self.lastValue

        for i in self.subscribers:
            f = i()
            if f:
                try:
                    f(self.lastValue, self.timestamp, self.annotation)
                except Exception:
                    try:
                        extraData = str(
                            (str(self.lastValue)[:48], self.timestamp,
                             str(self.annotation)[:48]))
                    except Exception as e:
                        extraData = str(e)
                    logger.exception(
                        "Tag subscriber error, val,time,annotation was: " +
                        extraData)
                    # Return the error from whence it came to display in the proper place
                    for i in subscriberErrorHandlers:
                        try:
                            i(self, f, self.lastValue)
                        except Exception:
                            print("Failed to handle error: " +
                                  traceback.format_exc(6) + "\nData: " +
                                  extraData)
            del f

    def processValue(self, value):
        """Represents the transform from the claim input to the output.
            Must be a pure-ish function
        """
        return value

    @property
    def age(self):
        return time.monotonic() - self.vta[1]

    @property
    def value(self) -> T:
        return self._getValue()

    @value.setter
    def value(self, v: T):
        self.setClaimVal("default", v, time.monotonic(),
                         "Set via value property")

    def pull(self) -> T:
        if not self.lock.acquire(timeout=15):
            raise RuntimeError("Could not get lock")
        try:
            return self._getValue(True)
        finally:
            self.lock.release()

    def _getValue(self, force=False) -> T:
        "Get the processed value of the tag, and update lastValue, It is meant to be called under lock."

        # Overrides not guaranteed to be instant
        if (self.lastGotValue >
                time.monotonic() - self.interval) and not force:
            return self.lastValue

        activeClaim = self.activeClaim()
        if activeClaim is None:
            activeClaim = self.getTopClaim()

        activeClaimValue = activeClaim.value

        if not callable(activeClaimValue):
            # We no longer are aiming to support using the processor for impure functions

            self.lastGotValue = time.monotonic()
            self.lastValue = self.processValue(activeClaimValue)

        else:
            # Rate limited tag getter logic. We ignore the possibility for
            # Race conditions and assume that calling a little too often is fine, since
            # It shouldn't affect correctness

            # Note that this is on a per-claim basis.  Every claim has it's own cache.
            if (time.monotonic() - activeClaim.lastGotValue >
                    self._interval) or force:
                # Set this flag immediately, or else a function with an error could defeat the cacheing
                # And just flood everything with errors
                activeClaim.lastGotValue = time.monotonic()

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
                            logging.error(
                                "tag point:" + self.name +
                                " took too long getting lock to get value, falling back to cache"
                            )
                            return self.lastValue
                    try:
                        # None means no new data
                        x = activeClaimValue()
                        t = time.monotonic()

                        if x is not None:
                            # Race here. Data might not always match timestamp an annotation, if we weren't under lock
                            self.vta = (activeClaimValue, t, None)

                            # Set the timestamp on the claim, so that it will not become expired
                            self.activeClaim().vta = self.vta

                            activeClaim.cachedValue = (x, t)

                            # This is just used to calculate the overall age of the tags data
                            self.lastGotValue = time.monotonic()
                            self.lastValue = self.processValue(x)

                    finally:
                        self.lock.release()

                except Exception:
                    # We treat errors as no new data.
                    logger.exception("Error getting tag value")

                    # The system logger is the one kaithem actually logs to file.
                    if self.lastError < (time.monotonic() - (60 * 10)):
                        self.lastError = time.monotonic()
                        syslogger.exception(
                            "Error getting tag value. This message will only be logged every ten minutes."
                        )
                    # If we can, try to send the exception back whence it came
                    try:
                        from . import newevt
                        if hasattr(activeClaimValue, "__module__"):
                            if activeClaimValue.__module__ in newevt.eventsByModuleName:
                                newevt.eventsByModuleName[
                                    activeClaimValue.__module__]._handle_exception()
                    except Exception:
                        print(traceback.format_exc())

        return self.lastValue

    @property
    def pushOnRepeats(self):
        return False

    @pushOnRepeats.setter
    def pushOnRepeats(self, v):
        raise AttributeError(
            "Push on repeats was causing too much trouble and too much confusion and has been removed"
        )

    def handleSourceChanged(self, name):
        try:
            self._debugAdminPush(*self.vta)
        except Exception:
            pass
        if self.onSourceChanged:
            try:
                self.onSourceChanged(name)
            except Exception:
                logging.exception("Error handling changed source")

    def claim(self,
              value: Any,
              name: Optional[str] = None,
              priority: Optional[float] = None,
              timestamp: Optional[float] = None,
              annotation: Any = None,
              expiration: float = 0) -> Claim:
        """Adds a 'claim', a request to set the tag's value either to a literal
            number or to a getter function.

            A tag's value is the highest priority claim that is currently
            active, or the value returned from the getter if the active claim is
            a function.
        """

        name = name or 'claim' + str(time.time())
        if timestamp is None:
            timestamp = time.monotonic()

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
                claim = self.claims[name]()

            # If the weakref obj disappeared it will be None
            if claim is None:
                priority = priority or 50
                claim = self.claimFactory(value, name, priority, timestamp,
                                          annotation, expiration)

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

            self.claims[name] = weakref.ref(claim)

            if self.activeClaim:
                ac = self.activeClaim()
            else:
                ac = None

            oldAcPriority = 0
            oldAcTimestamp = 0

            if ac:
                oldAcPriority = ac.priority
                oldAcTimestamp = ac.timestamp

            claim.priority = priority
            claim.vta = value, timestamp, annotation

            # If we have priortity on them, or if we have the same priority but are newer
            if (ac is None) or (priority > oldAcPriority) or (
                    (priority == oldAcPriority) and (timestamp > oldAcTimestamp)):
                self.activeClaim = self.claims[name]
                self.handleSourceChanged(name)

                if callable(self.vta[0]) or callable(value):
                    needsManagePolling = True
                else:
                    needsManagePolling = False

                self.vta = (value, timestamp, annotation)

                if needsManagePolling:
                    self._managePolling()

            # If priority has been changed on the existing active claim
            # We need to handle it
            elif name == ac.name:
                # Defensive programming against weakrefs dissapearing
                # in some kind of race condition that leaves them in the list.
                # Basically we find the highest priority valid claim

                # Deref all weak refs
                c = [i() for i in self.claims.values()]
                # Eliminate dead references
                c = [i for i in c if i]
                # Get the top one
                c = sorted(c, reverse=True)

                for i in c:
                    x = i
                    if x:
                        self.vta = (x.value, x.timestamp, x.annotation)

                        if not i == self.activeClaim():
                            self.activeClaim = weakref.ref(i)
                            self.handleSourceChanged(i.name)
                        else:
                            self.activeClaim = weakref.ref(i)
                        break

            self._getValue(force=True)
            self._push()
            return claim
        finally:
            self.lock.release()

    def setClaimVal(self, claim, val, timestamp, annotation):
        "Set the value of an existing claim"

        if timestamp is None:
            timestamp = time.monotonic()

        valCallable = True
        if not callable(val):
            valCallable = False
            val = self.filterValue(val)

        if not self.lock.acquire(timeout=10):
            raise RuntimeError("Could not get lock!")

        try:
            c = self.claims[claim]

            # If we're setting the active claim
            if c == self.activeClaim:
                upd = True
            else:
                co = c()
                ac = self.activeClaim()

                upd = False
                # We can "steal" control if we have the same priority
                # and are more recent, byt to do that we have to use
                #  the slower claim function that handles creating
                # and switching claims
                if (ac is None) or (co.priority >= ac.priority
                                    and timestamp >= ac.timestamp):
                    self.claim(val, claim, co.priority, timestamp, annotation)
                    return

            # Grab the claim obj and set it's val
            x = c()
            if self.poller or valCallable:
                self._managePolling()

            x.vta = val, timestamp, annotation

            if upd:
                self.vta = (val, timestamp, annotation)
                if valCallable:
                    # Mark that we have not yet ever gotten this getter
                    # so the change becomes immediate.
                    # Note that we have both a tag and a claim level cache time
                    self.lastGotValue = 0
                    # No need to call the function right away, that can happen when a getter calls it
                    pass  # self._getValue()
                else:
                    self.lastGotValue = time.monotonic()
                    self.lastValue = self.processValue(val)
                # No need to push is listening
                if (self.subscribers or self.handler):
                    if timestamp:
                        self._push()
        finally:
            self.lock.release()

    # Get the specific claim object for this class
    def claimFactory(self,
                     value: Any,
                     name: str,
                     priority: int,
                     timestamp,
                     annotation,
                     expiration: float = 0):
        return Claim(self, value, name, priority, timestamp, annotation,
                     expiration)

    def getTopClaim(self) -> Claim:
        # Deref all weak refs
        x = [i() for i in self.claims.values()]
        # Eliminate dead references
        x = [i for i in x if i and not i.released]
        if not x:
            raise RuntimeError(f"Program state is corrupt, tag{self.name} has no claims")
        # Get the top one
        x = sorted(x, reverse=True)[0]
        return x

    def release(self, name):
        if not self.lock.acquire(timeout=10):
            raise RuntimeError("Could not get lock!")

        try:
            # Ifid lets us filter by ID, so that a claim object that has
            # Long since been overriden can't delete one with the same name
            # When it gets GCed
            if name not in self.claims:
                return

            if name == "default":
                raise ValueError("Cannot delete the default claim")

            self.claims[name]().released = True
            o = self.getTopClaim()
            # All claims gone means this is probably in a __del__ function as it is disappearing
            if not o:
                return

            doChange = self.activeClaim() is not o

            self.vta = (o.value, o.timestamp, o.annotation)
            self.activeClaim = weakref.ref(o)

            self._getValue()
            self._push()
            self._managePolling()
            if doChange:
                self.handleSourceChanged(self.activeClaim().name)
        finally:
            self.lock.release()


default_bool_enum = {-1: None, 0: False, 1: True}


class NumericTagPointClass(GenericTagPointClass[float]):
    defaultData = 0
    type = 'number'

    @typechecked
    def __init__(self,
                 name: str,
                 min: Optional[float] = None,
                 max: Optional[float] = None):

        self.vta: Tuple[float, float, Any]

        # Real active compouted vals after the dynamic/configured override logic
        self._hi: Optional[float] = None
        self._lo: Optional[float] = None
        self._min: Optional[float] = min
        self._max: Optional[float] = max
        # Pipe separated list of how to display value
        self._displayUnits: Union[str, None] = None
        self._unit: str = ""
        self.guiLock = threading.Lock()
        self._meterWidget = None
        self.enum = {}

        self._setupMeter()
        super().__init__(name)

    def processValue(self, value: Union[float, int]):

        if self._min is not None:
            value = max(self._min, value)

        if self._max is not None:
            value = min(self._max, value)

        return float(value)

    @property
    def meterWidget(self):
        if not self.lock.acquire(timeout=5):
            raise RuntimeError("Error getting lock")
        try:
            if self._meterWidget:
                x = self._meterWidget
                if x:
                    self._debugAdminPush(self.value, None, None)
                    # Put if back if the function tried to GC it.
                    self._meterWidget = x
                    return self._meterWidget

            self._meterWidget = widgets.Meter(
                extraInfo=makeTagInfoHelper(self))

            def f(v, t, a):
                self._debugAdminPush(v, t, a)

            self.subscribe(f)
            self._meterWidget.updateSubscriber = f

            self._meterWidget.defaultLabel = self.name.split(".")[-1][:24]

            self._meterWidget.set_permissions(['/users/tagpoints.view'],
                                             ['/users/tagpoints.edit'])
            self._setupMeter()
            # Try to immediately put the correct data in the gui
            if self.guiLock.acquire():
                try:
                    # Note: this in-thread write could be slow
                    self._meterWidget.write(self.lastValue)
                finally:
                    self.guiLock.release()
            return self._meterWidget
        finally:
            self.lock.release()

    def _debugAdminPush(self, value, t, a):

        if not self._meterWidget:
            return

        if not self._meterWidget.stillActive():
            if not self.lock.acquire(timeout=5):
                raise RuntimeError("Error getting lock")
            self._meterWidget = None
            self.lock.release()
            return

        # Immediate write, don't push yet, do that in a thread because TCP can block

        def pushFunction():
            self._meterWidget.write(value, push=False)
            if self.guiLock.acquire(timeout=1):
                try:
                    # Use the cached literal computed value, not what we were passed,
                    # Because it could have changed by the time we actually get to push
                    self._meterWidget.write(self.lastValue)
                finally:
                    self.guiLock.release()

        # Should there already be a function queued for this exact reason, we just let
        # That one do it's job
        if self.guiLock.acquire(timeout=0.001):
            try:
                workers.do(pushFunction)
            finally:
                self.guiLock.release()

    def filterValue(self, v: float) -> float:
        return float(v)

    def claimFactory(self,
                     value: float | Callable[..., Optional[float]],
                     name: str,
                     priority: float,
                     timestamp: float,
                     annotation: Any,
                     expiration: float = 0):
        return NumericClaim(self, value, name, priority, timestamp, annotation,
                            expiration)

    @property
    def min(self) -> Union[float, int]:
        return self._min if self._min is not None else -10**18

    @min.setter
    def min(self, v: Optional[float]):
        self._dynConfigValues['min'] = v

        if not v == self.configOverrides.get('min', v):
            return
        self._min = v
        self.pull()
        self._setupMeter()

    @property
    def max(self) -> Union[float, int]:
        return self._max if self._max is not None else 10**18

    @max.setter
    def max(self, v: Optional[float]):
        self._dynConfigValues['max'] = v
        if not v == self.configOverrides.get('max', v):
            return
        self._max = v
        self.pull()
        self._setupMeter()

    @property
    def hi(self) -> Union[float, int]:
        x = self._hi
        if x is None:
            return 10**18
        else:
            return x

    @hi.setter
    def hi(self, v: Optional[float]):
        self._dynConfigValues['hi'] = v
        if not v == self.configOverrides.get('hi', v):
            return
        if v is None:
            v = 10**16
        self._hi = v
        self._setupMeter()

    @property
    def lo(self) -> Union[float, int]:
        if self._lo is None:
            return 10**18
        return self._lo

    @lo.setter
    def lo(self, v: Optional[float]):
        self._dynConfigValues['lo'] = v
        if not v == self.configOverrides.get('lo', v):
            return
        if v is None:
            v = -(10**16)
        self._lo = v
        self._setupMeter()

    def _setupMeter(self):
        if not self._meterWidget:
            return
        self._meterWidget.setup(
            self._min if (not (self._min is None)) else -100,
            self._max if (not (self._max is None)) else 100,
            self._hi if not (self._hi is None) else 10**16,
            self._lo if not (self._lo is None) else -(10**16),
            unit=self.unit,
            displayUnits=self.displayUnits)

    def convertTo(self, unit: str):
        "Return the tag's current vakue converted to the given unit"
        return convert(self.value, self.unit, unit)

    def convertValue(self, value: Union[float, int],
                     unit: str) -> Union[float, int]:
        "Convert a value in the tag's native unit to the given unit"
        return convert(value, self.unit, unit)

    @property
    def unit(self):
        return self._unit

    @typechecked
    @unit.setter
    def unit(self, value: str):
        if self._unit:
            if not self._unit == value:
                if value:
                    raise ValueError(
                        "Cannot change unit of tagpoint. To override this, set to None or '' first"
                    )
        # TODO race condition in between check, but nobody will be setting this from different threads
        # I don't think
        if not self._displayUnits:
            # Rarely does anyone want alternate views of dB values
            if "dB" not in value:
                try:
                    self._displayUnits = default_display_units[unit_types[value]]
                    # Always show the native unit
                    if not value in self._displayUnits:
                        self._displayUnits = value + '|' + self._displayUnits
                except Exception:
                    self._displayUnits = value
            else:
                self._displayUnits = value

        self._unit = value
        self._setupMeter()
        if self._meterWidget:
            self._meterWidget.write(self.value)

    @property
    def displayUnits(self):
        return self._displayUnits

    @displayUnits.setter
    def displayUnits(self, value):
        if value and not isinstance(value, str):
            raise RuntimeError("units must be str")
        self._dynConfigValues['displayUnits'] = value
        if not value == self.configOverrides.get('displayUnits', value):
            return

        self._displayUnits = value
        self._setupMeter()
        if self._meterWidget:
            self._meterWidget.write(self.value)


class StringTagPointClass(GenericTagPointClass[str]):
    defaultData = ''
    unit = "string"
    type = 'string'
    mqttEncoding = 'utf8'

    @typechecked
    def __init__(self, name: str):
        self.vta: Tuple[str, float, Any]
        self.guiLock = threading.Lock()
        self._spanWidget = None
        super().__init__(name)

    def processValue(self, value):

        return str(value)

    def filterValue(self, v):
        return str(v)

    def _debugAdminPush(self, value, timestamp, annotation):
        # Immediate write, don't push yet, do that in a thread because TCP can block

        if not self._spanWidget:
            if not self.lock.acquire(timeout=5):
                raise RuntimeError("Error getting lock")
            self._spanWidget = None
            self.lock.release()
            return

        if not self._spanWidget.stillActive():
            if not self.lock.acquire(timeout=5):
                raise RuntimeError("Error getting lock")
            self._spanWidget = None
            self.lock.release()
            return

        # Limit the length
        value = value[:256]
        self._spanWidget.write(value, push=False)

        def pushFunction():
            self._spanWidget.value = value
            if self.guiLock.acquire(timeout=1):
                try:
                    # Use the cached literal computed value, not what we were passed,
                    # Because it could have changed by the time we actually get to push
                    self._spanWidget.write(self.lastValue)
                finally:
                    self.guiLock.release()

        # Should there already be a function queued for this exact reason, we just let
        # That one do it's job
        if self.guiLock.acquire(timeout=0.001):
            try:
                workers.do(pushFunction)
            finally:
                self.guiLock.release()

    @property
    def spanWidget(self):
        if not self.lock.acquire(timeout=5):
            raise RuntimeError("Error getting lock")
        try:
            if self._spanWidget:
                x = self._spanWidget
                if x:
                    self._debugAdminPush(self.value, None, None)
                    # Put if back if the function tried to GC it.
                    self._spanWidget = x
                    return self._spanWidget

            self._spanWidget = widgets.DynamicSpan(
                extraInfo=makeTagInfoHelper(self))

            def f(v, t, a):
                self._debugAdminPush(v, t, a)

            self.subscribe(f)
            self._spanWidget.updateSubscriber = f

            self._spanWidget.defaultLabel = self.name.split(".")[-1][:24]

            self._spanWidget.set_permissions(['/users/tagpoints.view'],
                                            ['/users/tagpoints.edit'])
            # Try to immediately put the correct data in the gui
            if self.guiLock.acquire():
                try:
                    # Note: this in-thread write could be slow
                    self._spanWidget.write(self.lastValue)
                finally:
                    self.guiLock.release()
            return self._spanWidget
        finally:
            self.lock.release()


class ObjectTagPointClass(GenericTagPointClass[Dict[str, Any]]):
    defaultData: object = {}
    type = 'object'

    @typechecked
    def __init__(self, name: str):
        self.vta: Tuple[Dict[str, Any], float, Any]
        self.guiLock = threading.Lock()

        self.validate = None
        self._spanWidget = None
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

    def _debugAdminPush(self, value, timestamp, annotation):
        # Immediate write, don't push yet, do that in a thread because TCP can block

        if not self._spanWidget:
            if not self.lock.acquire(timeout=5):
                raise RuntimeError("Error getting lock")
            self._spanWidget = None
            self.lock.release()
            return

        if not self._spanWidget.stillActive():
            if not self.lock.acquire(timeout=5):
                raise RuntimeError("Error getting lock")
            self._spanWidget = None
            self.lock.release()
            return

        value = json.dumps(value)
        # Limit the length
        value = value[:256]
        self._spanWidget.write(value, push=False)

        def pushFunction():
            self._spanWidget.value = value
            if self.guiLock.acquire(timeout=1):
                try:
                    # Use the cached literal computed value, not what we were passed,
                    # Because it could have changed by the time we actually get to push
                    self._spanWidget.write(json.dumps(self.lastValue))
                finally:
                    self.guiLock.release()

        # Should there already be a function queued for this exact reason, we just let
        # That one do it's job
        if self.guiLock.acquire(timeout=0.001):
            try:
                workers.do(pushFunction)
            finally:
                self.guiLock.release()

    @property
    def spanWidget(self):
        if not self.lock.acquire(timeout=5):
            raise RuntimeError("Error getting lock")
        try:
            if self._spanWidget:
                x = self._spanWidget

                def f(v, t, a):
                    self._debugAdminPush(v, t, a)

                self.subscribe(f)
                x.updateSubscriber = f
                if x:
                    self._debugAdminPush(self.value, None, None)
                    # Put if back if the function tried to GC it.
                    self._spanWidget = x
                    return self._spanWidget

            self._spanWidget = widgets.DynamicSpan()

            self._spanWidget.set_permissions(['/users/tagpoints.view'],
                                            ['/users/tagpoints.edit'])
            # Try to immediately put the correct data in the gui
            if self.guiLock.acquire():
                try:
                    # Note: this in-thread write could be slow
                    self._spanWidget.write(self.lastValue)
                finally:
                    self.guiLock.release()
            return self._spanWidget
        finally:
            self.lock.release()


class BinaryTagPointClass(GenericTagPointClass[bytes]):
    defaultData: bytes = b''
    type = 'binary'

    @typechecked
    def __init__(self, name: str):
        self.vta: Tuple[bytes, float, Any]
        self.guiLock = threading.Lock()

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


class Claim():
    "Represents a claim on a tag point's value"

    @typechecked
    def __init__(self,
                 tag: GenericTagPointClass[Any],
                 value: Any,
                 name: str = 'default',
                 priority: Union[int, float] = 50,
                 timestamp: Union[int, float, None] = None,
                 annotation=None,
                 expiration=0):

        self.name = name
        self.tag = tag
        self.vta: Tuple[Any, float, Any] = value, timestamp, annotation

        # If the value is a callable, this is the cached result plus the timestamp for the cache, separate
        # From the vta timestamp of when that callable actually got set.
        self.cachedValue = (None, timestamp)

        # Track the last *attempt* at reading the value if it is a callable, regardless of whether
        # it had new data or not.

        # It is in monotonic time.
        self.lastGotValue = 0

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
        if self.name != 'default':
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
        if (self.priority, self.timestamp) <= (other.priority,
                                               other.timestamp):
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
        if (self.priority, self.timestamp) >= (other.priority,
                                               other.timestamp):
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

            if ts < (time.monotonic() - self.expiration):
                # First we must try to refresh the callable.
                self.refreshCallable()
                if self.tag.lock.acquire(timeout=90):
                    try:
                        if callable(self.value):
                            ts = self.cachedValue[1]
                        else:
                            ts = self.timestamp

                        if ts < (time.monotonic() - self.expiration):
                            self.setPriority(self.expiredPriority, False)
                            self.expired = True
                    finally:
                        self.tag.lock.release()
                else:
                    raise RuntimeError(
                        "Cannot get lock to set priority, waited 90s")
        else:
            # If we are already expired just refresh now.
            self.refreshCallable()

    def refreshCallable(self):
        # Only call the getter under lock in case it happens to not be threadsafe
        if callable(self.value):
            if self.tag.lock.acquire(timeout=90):
                self.lastGotValue = time.monotonic()
                try:
                    x = self.value()
                    if x is not None:
                        self.cachedValue = (x, time.monotonic())
                        self.unexpire()
                finally:
                    self.tag.lock.release()

            else:
                raise RuntimeError(
                    "Cannot get lock to set priority, waited 90s")

    def setExpiration(self, expiration: float, expiredPriority: float = 1):
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
                self.poller = scheduling.scheduler.scheduleRepeating(
                    self.expirePoll, interval, sync=False)
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
                    "Cannot get lock to set priority, waited 90s")

    @property
    def value(self):
        return self.vta[0]

    @property
    def timestamp(self):
        return self.vta[1]

    @property
    def annotation(self):
        return self.vta[2]

    def set(self, value, timestamp: Optional[float] = None, annotation: Any = None):

        # Not threadsafe here if multiple threads use the same claim, value, timestamp, and annotation can
        self.vta = (value, self.timestamp, self.annotation)

        # If we are expired, un-expi
        if self.expired:
            self.unexpire()

        # In the released state we must do it all over again
        elif self.released:
            if self.tag.lock.acquire(timeout=60):
                try:
                    self.tag.claim(value=self.value,
                                   timestamp=self.timestamp,
                                   annotation=self.annotation,
                                   priority=self.priority,
                                   name=self.name)
                finally:
                    self.tag.lock.release()

            else:
                raise RuntimeError(
                    "Cannot get lock to re-claim after release, waited 60s")
        else:
            self.tag.setClaimVal(self.name, value, timestamp, annotation)

    def release(self):
        try:
            # Stop any weirdness with an old claim double releasing and thus releasing a new claim
            if not self.tag.claims[self.name]() is self:

                # If the old replaced claim is somehow the active omne we acrtuallty should handle that
                if not self.tag.activeClaim() is self:
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
                self.tag.claim(value=self.value,
                               timestamp=self.timestamp,
                               annotation=self.annotation,
                               priority=self.priority,
                               name=self.name)
            finally:
                self.tag.lock.release()

        else:
            raise RuntimeError("Cannot get lock to set priority, waited 60s")

    def __call__(self, *args, **kwargs):
        if not args:
            raise ValueError("No arguments")
        else:
            return self.set(*args, **kwargs)


class NumericClaim(Claim):
    "Represents a claim on a tag point's value"

    @typechecked
    def __init__(self,
                 tag: GenericTagPointClass[float],
                 value: float | Callable[..., Optional[float]],
                 name: str = 'default',
                 priority: Union[int, float] = 50,
                 timestamp: Union[int, float, None] = None,
                 annotation=None,
                 expiration: float = 0):

        self.vta: Tuple[float, float, Any]
        Claim.__init__(self, tag, value, name, priority, timestamp, annotation,
                       expiration)

    def setAs(self, value: float, unit: str, timestamp: Optional[float] = None, annotation: Any = None):
        "Convert a value in the given unit to the tag's native unit"
        self.set(convert(value, unit, self.tag.unit), timestamp, annotation)


# Math for the first order filter
# v is our state, k is a constant, and i is input.

# At each timestep of one, we do:
# v = v*(1-k) + i*k

# moving towards the input with sped determined by k.
# We can reformulate that as explicitly taking the difference, and moving along portion of it
# v = (v+((i-v)*k))

# We can show this reformulation is correct with XCas:
# solve((v*(1-k) + i*k) - (v+((i-v)*k)) =x,x)

# x is 0, because the two equations are always the same.

# Now we use 1-k instead, such that k now represents the amount of difference allowed to remain.
# Higher k is slower.
# (v+((i-v)*(1-k)))

# Twice the time means half the remaining difference, so we are going to raise k to the power of the number of timesteps
# at each round to account for the uneven timesteps we are using:
# v = (v+((i-v)*(1-(k**t))))

# Now we need k such that v= 1/e when starting at 1 going to 0, with whatever our value of t is.
# So we substitute 1 for v and 0 for i, and solve for k:
# solve(1/e = (1+((0-1)*(1-(k**t)))),k)

# Which gives us k=exp(-(1/t))


class Filter():
    pass


class LowpassFilter(Filter):
    def __init__(self, name, inputTag, timeConstant, priority=60, interval=-1):
        self.state = inputTag.value
        self.filtered = self.state
        self.lastRanFilter = time.monotonic()
        self.lastState = self.state

        # All math derived with XCas
        self.k = math.exp(-(1 / timeConstant))
        self.lock = threading.Lock()

        self.inputTag = inputTag
        inputTag.subscribe(self.doInput)

        self.tag = Tag(name)
        self.claim = self.tag.claim(self.getter,
                                    name=inputTag.name + ".lowpass",
                                    priority=priority)

        if interval is None:
            self.tag.interval = timeConstant / 2
        else:
            self.tag.interval = interval

    def doInput(self, val, ts, annotation):
        "On new data, we poll the output tag which also loads the input tag data."
        self.tag.poll()

    def getter(self):
        self.state = self.inputTag.value

        # Get the average state over the last period
        state = (self.state + self.lastState) / 2
        t = time.monotonic() - self.lastRanFilter
        self.filtered = (self.filtered + ((state - self.filtered) *
                                          (1 - (self.k**t))))
        self.lastRanFilter += t

        self.lastState = self.state

        # Suppress extremely small changes that lead to ugly decimals and network traffic
        if abs(self.filtered - self.state) < (self.filtered / 1000000.0):
            return self.state
        else:
            return self.filtered


class HighpassFilter(LowpassFilter):
    def getter(self):
        self.state = self.inputTag.value

        # Get the average state over the last period
        state = (self.state + self.lastState) / 2
        t = time.monotonic() - self.lastRanFilter
        self.filtered = (self.filtered + ((state - self.filtered) *
                                          (1 - (self.k**t))))
        self.lastRanFilter += t

        self.lastState = self.state

        s = self.state - self.filtered

        # Suppress extremely small changes that lead to ugly decimals and network traffic
        if abs(s) < (0.0000000000000001):
            return 0
        else:
            return s


# class HysteresisFilter(Filter):
#     def __init__(self, name, inputTag, hysteresis=0, priority=60):
#         self.state = inputTag.value

#         # Start at midpoint with the window centered
#         self.hysteresisUpper = self.state + hysteresis / 2
#         self.hysteresisLower = self.state + hysteresis / 2
#         self.lock = threading.Lock()

#         self.inputTag = inputTag
#         inputTag.subscribe(self.doInput)

#         self.tag = _NumericTagPoint(name)
#         self.claim = self.tag.claim(
#             self.getter, name=inputTag.name + ".hysteresis", priority=priority)

#     def doInput(self, val, ts, annotation):
#         "On new data, we poll the output tag which also loads the input tag data."
#         self.tag.poll()

#     def getter(self):
#         with self.lock:
#             self.lastState = self.state

#             if val >= self.hysteresisUpper:
#                 self.state = val
#                 self.hysteresisUpper = val
#                 self.hysteresisLower = val - self.hysteresis
#             elif val <= self.hysteresisLower:
#                 self.state = val
#                 self.hysteresisUpper = val + self.hysteresis
#                 self.hysteresisLower = val
#             return self.state


def createGetterFromExpression(e: str, t: TagPointClass, priority=98) -> Claim:

    try:
        for i in t.sourceTags:
            t.sourceTags[i].unsubscribe(t.recalc)
    except Exception:
        logger.exception(
            "Unsubscribe fail to old tag.  A subscription mau be leaked, wasting CPU. This should not happen."
        )

    t.sourceTags = {}

    def recalc(*a):
        t()

    t.recalcHelper = recalc

    c = compile(e[1:], t.name + "_expr", "eval")

    def f():
        return (eval(c, t.evalContext, t.evalContext))

    # Overriding these tags would be extremely confusing because the
    # Expression is right in the name, so don't make it easy
    # with priority 98 by default
    c2 = t.claim(f, "ExpressionTag", priority)
    t.pull()
    return c2


def configTagFromData(name: str, data: dict):
    name = normalizeTagName(name)

    t = data.get("type", '')

    # Get rid of any unused existing tag
    try:
        if name in configTags:
            del configTags[name]
            gc.collect()
            time.sleep(0.01)
            gc.collect()
            time.sleep(0.01)
            gc.collect()
    except Exception:
        logger.exception("Deleting tag config")

    tag: Optional(TagPointClass) = None
    # Create or get the tag
    if t == "number":
        tag = Tag(name)

    elif t == "string":
        tag = StringTag(name)
    elif name in allTags:
        tag = allTags[name]()
    else:
        # Config later when the tag is actually created
        configTagData[name] = persist.getStateFile(
            getFilenameForTagConfig(name))
        for i in data:
            configTagData[name][i] = data[i]
        return

    if tag:
        configTags[name] = tag
    # Now set it's config.
    tag.setConfigData(data)


def loadAllConfiguredTags(f=os.path.join(directories.vardir, "tags")):
    with lock:
        global configTagData

        configTagData = persist.loadAllStateFiles(f)

        gcEmptyConfigTags()

        for i in list(configTagData.keys()):
            try:
                configTagFromData(i, configTagData[i].getAllData())
            except Exception:
                logging.exception("Failure with configured tag: " + i)
                messagebus.post_message(
                    "/system/notifications/errors",
                    "Failed to preconfigure tag " + i + "\n" +
                    traceback.format_exc())


Tag = NumericTagPointClass.Tag
ObjectTag = ObjectTagPointClass.Tag
StringTag = StringTagPointClass.Tag
BinaryTag = BinaryTagPointClass.Tag
