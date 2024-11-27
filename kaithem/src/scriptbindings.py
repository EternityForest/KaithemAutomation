# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only


"""This file implements ChandlerScript, a DSL for piplines of events triggered by
commands, called bindings.

One binding fits on one line:

event: action1 argument1 argument2 | action2 "A quoted argument" $variable

commands have a return value. Should one return None, the pipeline stops right there.

The pipeline also stops if an error is encountered.


Bindings live in a "Context Object". You can trigger an event in such an object with
ctx.event("event")

You can add an action by simply adding it as a function to the weak dict ctx.commands

Arguments are preprocessed before being supplied as positional args.
However, the dict based variant supplies args as keywords, so be aware.

Anything beginning with $ is considered a variable, it is expanded based on variables
in the context.

Anything that looks like it could be a number is automatically converted to a float or
int, unless it is quoted.

The return value of the previous function is always available as $chain

This means functions can potentially recieve any python data type.
All functions should be strongly typed for this reason, and should use
the typeguard library to ensure this.


commands can have a manifest property applied to the function.

It must look like:
{
    "description":"Foo",
    "args":[
        ["arg1Name","int",default,min,max],
        ["arg2Name",'str','Default'],
        ["arg3,"SomeOtherType", "SomeOtherData"]
    ]
}

This allows GUIs to auto-generate a UI for visually creating pipelines.

If there is an unrecognized type, it is treated as a string.
"""

from __future__ import annotations

import datetime
import inspect
import logging
import math
import random
import subprocess
import threading
import time
import traceback
import weakref
from collections.abc import Callable
from types import MethodType
from typing import Any

import pytz
import simpleeval
from beartype import beartype
from scullery import workers
from scullery.scheduling import scheduler

from kaithem.api import lifespan

from . import astrallibwrapper as sky
from . import geolocation, settings_overrides, tagpoints, util

simpleeval.MAX_POWER = 1024


class NamespaceGetter:
    "Takes a dict and a prefix. Responds to attr requests with dict[prefix+.+key]"

    def __init__(self, d, prefix):
        self.__attr_prefix = prefix
        self.__attr_dict = d

    def __getattr__(self, k):
        return self.__attr_dict[f"{self.__attr_prefix}.{k}"]


def DummyObject():
    "Operations with this succeed, but return other"

    def __add__(self, other):
        return other

    def __sub__(self, other):
        return other

    def __mul__(self, other):
        return other

    def __floordiv__(self, other):
        return other

    def __truediv__(self, other):
        return other

    def __mod__(self, other):
        return other

    def __pow__(self, other):
        return other

    def __and__(self, other):
        return other

    def __xor__(self, other):
        return other

    def __or__(self, other):
        return other

    def __int__(self):
        return 0

    def __neg__(self):
        return 0

    def __str__(self):
        return ""


def paramDefault(p):
    if isinstance(p, int):
        return f"={str(p)}"

    if isinstance(p, (int, float)):
        return f"={str(p)}"

    if isinstance(p, str):
        # Wrap strings that look like numbers in quotes
        if p and not p.strip().startswith("="):
            try:
                float(p)
                return f"='{repr(p)}'"
            except Exception:
                return f"={repr(p)}"

        # Presever things starting with = unchanged
        else:
            return str(p)

    if isinstance(p, bool):
        return 1 if p else 0

    if p is None:
        return ""
    return ""


def get_function_info(f: Callable[..., Any]):
    p = inspect.signature(f).parameters

    d = {
        "doc": inspect.getdoc(f),
        "args": [[i, paramDefault(p[i].default)] for i in p],
    }

    if hasattr(f, "completionTags"):
        d["completionTags"] = f.completionTags

    return d


def getContextFunctionInfo(f):
    p = inspect.signature(f).parameters
    d = {
        "doc": inspect.getdoc(f),
        "args": [[i, paramDefault(p[i].default)] for i in p][1:],
    }

    return d


def safesqrt(x):
    if x > 10**30:
        raise RuntimeError("Too High of number for sqrt")
    return math.sqrt(x)


def millis():
    return time.monotonic() * 1000


# TODO separate the standard library stuff from this file?


def is_day(lat=None, lon=None):
    if lat is None:
        if lon is None:
            lat, lon = geolocation.getCoords()

        if lat is None or lon is None:
            raise RuntimeError(
                "No server location set, fix this in system settings"
            )
    return sky.is_day(lat, lon)


def is_night(lat=None, lon=None):
    if lat is None:
        if lon is None:
            lat, lon = geolocation.getCoords()

        if lat is None or lon is None:
            raise RuntimeError(
                "No server location set, fix this in system settings"
            )
    return sky.is_night(lat, lon)


def is_light(lat=None, lon=None):
    if lat is None:
        if lon is None:
            lat, lon = geolocation.getCoords()

        if lat is None or lon is None:
            raise RuntimeError(
                "No server location set, fix this in system settings"
            )
    return sky.is_light(lat, lon)


def is_dark(lat=None, lon=None):
    if lon is None:
        lat, lon = geolocation.getCoords()

    else:
        raise ValueError("You set lon, but not lst?")
    if lat is None or lon is None:
        raise RuntimeError(
            "No server location set, fix this in system settings"
        )

    return sky.is_dark(lat, lon)


def cfg(key: str):
    return settings_overrides.get_val(key)


globalUsrFunctions = {
    "unixtime": time.time,
    "millis": millis,
    "random": random.random,
    "randint": random.randint,
    "max": max,
    "min": min,
    "log": math.log,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "sqrt": safesqrt,
    "is_dark": is_dark,
    "is_night": is_night,
    "is_light": is_light,
    "is_day": is_day,
    "cfg": cfg,
}


globalConstants = {"e": math.e, "pi": math.pi}


def rval(x):
    "Returns the parameter x, and continues the action(Unless the value is None)"
    return x


def passAction():
    "Does nothing and returns True, continuing the action"
    return True


def maybe(chance=50):
    "Return a True with some percent chance, else stop the action"
    return True if random.random() * 100 > chance else None


def continue_if(v):
    "Continue if the first parameter is True. Remember that the param can be an expression like '= event.value=50'"
    return True if v else None


# Use context_info.event from inside any function, the value will be a (name,value) tuple for the event
context_info = threading.local()

predefinedcommands = {
    "return": rval,
    "pass": passAction,
    "maybe": maybe,
    "continue_if": continue_if,
}


lock = threading.RLock()


class ScheduleTimer:
    def __init__(self, selector, context):
        self.eventName = selector
        self.context = weakref.ref(context)

        selector = selector.strip()
        if not selector:
            return
        if not selector[0] == "@":
            raise ValueError("Invalid")

        ref = datetime.datetime.now()

        self.selector = util.get_rrule_selector(selector[1:], ref)

        nextruntime = self.selector.after(datetime.datetime.now(), False)
        self.nextruntime = dt_to_ts(nextruntime)
        self.next = scheduler.schedule(self.handler, self.nextruntime, False)

    def handler(self, *a, **k):
        nextruntime = self.selector.after(datetime.datetime.now(), False)
        ctx = self.context()

        # We don't want to reschedule if the context no longer exists
        if not ctx:
            return
        try:
            ctx.event(self.eventName)

            self.nextruntime = dt_to_ts(nextruntime)
            self.next = scheduler.schedule(
                self.handler, self.nextruntime, False
            )
            ctx.onTimerChange(self.eventName, self.nextruntime)

        finally:
            del ctx

    def stop(self):
        try:
            self.next.unregister()
        except Exception:
            pass


def dt_to_ts(dt, tz=None):
    "Given a datetime in tz, return unix timestamp"
    if tz:
        utc = pytz.timezone("UTC")
        return (
            tz.localize(dt.replace(tzinfo=None))
            - datetime.datetime(1970, 1, 1, tzinfo=utc)
        ) / datetime.timedelta(seconds=1)

    else:
        # Local Time
        ts = time.time()
        offset = (
            datetime.datetime.fromtimestamp(ts)
            - datetime.datetime.utcfromtimestamp(ts)
        ).total_seconds()
        return (
            (dt - datetime.datetime(1970, 1, 1)) / datetime.timedelta(seconds=1)
        ) - offset


class ScriptActionKeeper:
    """This typecheck wrapper is courtesy
    of two hours spent debugging at 2am, and my desire to avoid repeating that"""

    def __init__(self):
        self.scriptcommands = weakref.WeakValueDictionary()
        self.debug_refs = {}

    def __setitem__(self, key, value):
        if not isinstance(key, str):
            raise TypeError("Keys must be string function names")
        if not callable(value):
            raise TypeError("Script commands must be callable")

        if isinstance(value, MethodType):
            raise TypeError("Bound method type not supported")

        p = inspect.signature(value).parameters
        for i in p:
            if (
                (not p[i].default == p[i].empty)
                and p[i].default
                and not isinstance(p[i].default, (str, int, bool))
            ):
                raise ValueError(
                    "All default values must be int, string, or bool, not "
                    + str(p[i].default)
                )

        self.scriptcommands[key] = value

        def warn_chandler_gc(x):
            # Lifespan will be None during system exit
            if lifespan and not lifespan.shutdown:
                print(f"Chandler action {x} is no longer valid")

        self.debug_refs[key] = weakref.ref(value, warn_chandler_gc)

    def __getitem__(self, key):
        return self.scriptcommands[key]

    def __contains__(self, key):
        return key in self.scriptcommands

    def get(self, k, d):
        return self.scriptcommands.get(k, d)


class Event:
    def __init__(self, name, val, timestamp=None):
        self.name = name
        self.value = val
        self.time = timestamp or time.time()
        self.millis = millis()


class BaseChandlerScriptContext:
    def __init__(
        self,
        parentContext: BaseChandlerScriptContext | None = None,
        gil: threading.RLock | None = None,
        functions: dict[str, Callable[..., Any]] = {},
        variables: dict[str, Any] | None = None,
        constants: dict[str, Any] | None = None,
        contextFunctions: dict[str, Callable[..., Any]] = {},
        contextName: str = "script",
        wait_for_all_async_commands_callback: Callable[[], Any] | None = None,
    ):
        # Used so external code can give us a way to wait for any custom events to be done.
        self.wait_for_all_async_commands_callback = (
            wait_for_all_async_commands_callback
        )

        # Used as a backup plan to be able to do things in a background thread
        # when doing so directly would cause a deadlock
        self.event_queue: list[Callable[[], Any]] = []

        # Map event names to a list of pipelines, where each pipeline
        # is a list of commands, a command being a list of strings.
        self.event_listeners: dict[str, list[list[list[str]]]] = {}
        self.variables: dict[str, Any] = (
            variables if variables is not None else {}
        )
        self.commands = ScriptActionKeeper()
        self.context_commands = ScriptActionKeeper()

        self.children: dict[int, weakref.ref[BaseChandlerScriptContext]] = {}
        self.children_iterable: dict[
            int, weakref.ref[BaseChandlerScriptContext]
        ] = {}
        self.constants: dict[str, Any] = (
            constants if (constants is not None) else {}
        )
        self.contextName = contextName

        # Cache whether or not any binding is watching a variable
        # or variable. False positives are acceptable, it's just a slight
        # Performance hit
        self.need_refresh_for_variable: dict[str, bool] = {}
        self.need_refresh_for_tag: dict[str, bool] = {}

        # Used to track stuff like tag values that have timestamps
        # Tag value getters set it to the highest of the tag time and its current val.
        # Set it to 0, run an eval, the value gives you a time to use as event timestamp
        self.eval_times = 0

        # Used for detecting loops.  .d Must be 0 whenever we are not CURRENTLY,
        # as in right now, in this thread, executing an event. Not a pure stack
        # or semaphore, when you queue up an event, that event will run at one
        # higher than the event that created it, And always return to 0 when it
        # is not actively executing event code, to ensure that things not caused
        # directly by an event Don't have a nonzero depth.

        # It'ts not even tracking recursion really, more like async causation,
        # or parenthood back to an event not caused my another event.

        # The whole point is not to let an event create another event, which
        # runs the first event, etc.
        self.eventRecursionDepth = threading.local()

        # Should we propagate events to children
        self.propagateEvents = False

        # Used to allow objects named foo.bar to be accessed as actual
        # attributes of a foo obj,

        # Even though we use a flat list of vars.
        self.namespaces: dict[str, NamespaceGetter] = {}
        self.contextName = "ScriptContext"

        self.time_events: dict[str, ScheduleTimer] = {}
        self.poller = None
        self.slowpoller = None
        selfid = id(self)

        # Stack to keep track of the $event variable for the current event we
        # are running, For nested events
        self.eventValueStack: list[Event] = []

        # Look for rising edge detects that already fired
        self.risingEdgeDetects = {}

        # State tracking for change detection
        self.changeDetects = {}

        if parentContext:

            def delf(*a, **K):
                with lock:
                    del parentContext.children[selfid]
                    parentContext.children_iterable = (
                        parentContext.children.copy()
                    )

            with lock:
                parentContext.children[id(self)] = weakref.ref(self, delf)
                parentContext.children_iterable = parentContext.children.copy()

        self.parentContext = parentContext

        # Vars that have changed since last time we
        # Cleared the list. Used for telling the GUI
        # client about the current set of variables
        self.changedVariables: dict[str, Any] = {}

        def setter(Variable, Value):
            if not isinstance(Variable, str):
                raise RuntimeError("Var name must be string")
            if Variable in globalConstants or Variable in self.constants:
                raise NameError(f"Key {Variable} is a constant")
            self.setVar(Variable, Value)

        self.setter = setter
        self.commands["set"] = setter

        for i in predefinedcommands:
            self.commands[i] = predefinedcommands[i]

        def defaultVar(name, default):
            try:
                return self._nameLookup(name)
            except NameError:
                return default

        functions = functions.copy()
        functions.update(globalUsrFunctions)
        functions["defaultVar"] = defaultVar
        functions["var"] = defaultVar

        c = {}
        # Wrap them, so the first param becomes this context object.

        def wrap(self, f):
            def wrapped(*a, **k):
                f(self, *a, **k)

            return wrapped

        for i in contextFunctions:
            c[i] = wrap(self, contextFunctions[i])

        self.functions = functions

        self.evaluator = simpleeval.SimpleEval(
            functions=functions, names=self._nameLookup
        )

        if not gil:
            self.gil = threading.RLock()
        else:
            self.gil = gil

    def waitForEvents(self, timeout=None):
        st = time.time()
        while self.event_queue:
            if timeout and time.time() - st > timeout:
                raise TimeoutError("Timed out waiting for events")
            time.sleep(0.001)

    def checkPollEvents(self):
        """Check every event that is actually an expression, to see if it should
        be triggered
        """
        with self.gil:
            for i in self.event_listeners:
                try:
                    # Edge trigger
                    if i.startswith("=/"):
                        # Change =/ to just =
                        self.eval_times = 0
                        r = self.preprocessArgument(f"={i[2:]}")
                        if r:
                            if (i in self.risingEdgeDetects) and (
                                not self.risingEdgeDetects[i]
                            ):
                                self.risingEdgeDetects[i] = True
                                self.event(
                                    i,
                                    r,
                                    timestamp=self.eval_times or time.time(),
                                )
                        else:
                            self.risingEdgeDetects[i] = False

                    elif i.startswith("=~"):
                        self.eval_times = 0
                        r = self.preprocessArgument(f"={i[2:]}")
                        if (i in self.changeDetects) and (
                            self.changeDetects[i] != r
                        ):
                            self.event(
                                i, r, timestamp=self.eval_times or time.time()
                            )

                        self.changeDetects[i] = r

                    # Counter trigger
                    elif i.startswith("=+"):
                        self.eval_times = 0
                        r = self.preprocessArgument(f"={i[2:]}")
                        if r:
                            if (i in self.changeDetects) and (
                                self.changeDetects[i] != r
                            ):
                                self.event(
                                    i,
                                    r,
                                    timestamp=self.eval_times or time.time(),
                                )

                        self.changeDetects[i] = r

                    elif i.startswith("="):
                        self.eval_times = 0
                        r = self.preprocessArgument(i)
                        if r:
                            self.event(i, r, self.eval_times or time.time())
                except Exception:
                    self.event(
                        "script.error",
                        f"{self.contextName}\n{traceback.format_exc(chain=True)}",
                    )
                    raise

    def getCommandDataForEditor(self):
        """Get the data, as python dict which can be JSONed,
        which must be bound to the commands prop of the editor,
        so that the editor can know what commands we have"""
        with self.gil:
            c = self.commands.scriptcommands
            info = {}
            for i in c:
                f = c[i]
                info[i] = get_function_info(f)

            return info

    def do_async(self, f):
        self.event_queue.append(f)
        workers.do(self.doEventQueue)

    def doEventQueue(self, allowAsync=True):
        # Run all events in the queue, under the gil.
        while self.event_queue:
            if self.gil.acquire(timeout=20):
                # Run them all as one block
                try:
                    while self.event_queue:
                        try:
                            if self.event_queue:
                                self.event_queue.pop(False)()
                        except Exception:
                            logging.exception("Error in script context")
                finally:
                    self.gil.release()
            else:
                raise RuntimeError(
                    "Event queue stalled, Queued events are still buffered and may run later"
                )

    def onTimerChange(self, timer, nextRunTime):
        pass

    def _runCommand(self, c):
        # ContextCommands take precedence
        a = self.commands.get(c[0], None)
        a = self.context_commands.get(c[0], a)

        seen = {}

        p = self

        while not a:
            if id(p) in seen:
                break
            seen[id(p)] = True

            p = p.parentContext
            if p:
                a = p.commands.get(c[0], None)
                a = p.context_commands.get(c[0], a)
            else:
                break

        if a:
            try:
                return a(*[self.preprocessArgument(i) for i in c[1:]])
            except Exception:
                raise RuntimeError(
                    f"Error running chandler command: {str(c)[:1024]}"
                )
        else:
            raise ValueError(f"No such command: {c}")

    def syncEvent(self, evt, val=None, timeout=20):
        "Handle an event synchronously, in the current thread."
        if self.gil.acquire(timeout=20):
            try:
                depth = self.eventRecursionDepth.d
            except Exception:
                # Hasn't been set in this thread
                depth = 0

            try:
                return self._event(evt, val, depth)
            finally:
                self.gil.release()
        else:
            raise RuntimeError("Could not get GIL to run this event")

    def stopAfterThisHandler(self):
        "Don't handle any more bindings for this event, but continue the current binding"
        self.stopScriptFlag = True

    def event(self, evt, val=None, timestamp=None):
        "Queue an event to run in the background. Queued events run in FIFO"

        # Capture the depth we are at, so we can make sure that _event knows if
        # it was caused by another event.
        #
        try:
            depth = self.eventRecursionDepth.d
        except AttributeError:
            # Hasn't been set in this thread
            depth = 0

        def f():
            self._event(evt, val, depth)

        if len(self.event_queue) > 128:
            raise RuntimeError("Too Many queued events!!!")

        self.do_async(f)

    def _event(self, evt, val, depth, timestamp=None):
        handled = False

        # Tell any functions we call that they are running at elevated depth.
        self.eventRecursionDepth.d = depth + 1

        try:
            if self.eventRecursionDepth.d > 8:
                raise RecursionError(
                    "Cannot nest more than 8 events directly causing each other"
                )

            if not isinstance(val, Event):
                self.eventValueStack.append(Event(evt, val, timestamp))
            else:
                val.name = evt
                self.eventValueStack.append(val)

            context_info.event = (evt, val)
            self.variables["_"] = True if val is None else val

            self.stopScriptFlag = False
            try:
                if evt in self.event_listeners:
                    handled = True
                    for pipeline in self.event_listeners[evt]:
                        if self.stopScriptFlag:
                            break
                        for command in pipeline:
                            x = self._runCommand(command)
                            if x is None:
                                break
                            self.variables["_"] = x
            except Exception:
                logging.exception("Error running script command")
                self.event(
                    "script.error",
                    f"{self.contextName}\n{traceback.format_exc(chain=True)}",
                )
                raise

        finally:
            if self.eventValueStack:
                self.eventValueStack.pop()

            # We are done running the event, now we can set to 0 The depth must
            # be 0, because there is no event currently running till the queued
            # ones happen. This is not a stack or semaphore!
            self.eventRecursionDepth.d = 0
            context_info.event = None

        # #Propagate events to all children
        # if self.propagateEvents:
        #     for i in self.children_iterable:
        #         x = i()
        #         if x:
        #             x.event(i)
        #     del x

        return handled

    def preprocessArgument(self, a: Any):
        if isinstance(a, str):
            if a.startswith("="):
                return self.eval(a[1:])
            # Looks like a number, it is a number
            try:
                a = float(a)
            except Exception:
                pass

        return a

    def eval(self, a: Any):
        return self.evaluator.eval(a)

    def addNamespace(self, name):
        """If name is foo, Makes variables named 'foo.bar'
        accessible via an actual foo obj. Kind of a hack to allow a flat list of vars"""

        self.namespaces[name] = NamespaceGetter(self.variables, name)

    def _nameLookup(self, n):
        if not isinstance(n, str):
            n = n.id

        if n == "event":
            return self.eventValueStack[-1]

        if n in self.variables:
            return self.variables[n]
        if n in globalConstants:
            return globalConstants[n]
        if n in self.constants:
            return self.constants[n]

        if n in self.namespaces:
            return self.namespaces[n]

        raise NameError(f"No such name: {n}")

    def setVar(self, k: str, v: Any, force=False):
        if not self.gil.acquire(timeout=10):
            raise RuntimeError("Could not get lock")
        try:
            self.variables[k] = v
            self.changedVariables[k] = v
            self.onVarSet(k, v)
            if k not in self.need_refresh_for_variable:
                self.need_refresh_for_variable[k] = False
                for i in self.event_listeners:
                    if k in i:
                        self.need_refresh_for_variable[k] = True
            if self.need_refresh_for_variable[k]:
                self.checkPollEvents()
        finally:
            self.gil.release()

    def onVarSet(self, k: str, v: Any):
        pass

    def addContextCommand(self, name, callable):
        def wrap(self, f):
            def wrapped(*a, **k):
                f(self, *a, **k)

        self.commands[name] = wrap(self, callable)

    @beartype
    def addBindings(self, b: list[list[str | list[list[str]]]]):
        """
        Take a list of bindings and add them to the context.
        A binding looks like:
        ['eventname',[['command','arg1'],['command2']]

        When events happen commands run till one returns None.

        Also immediately runs any now events
        """
        with self.gil:
            # Cache is invalidated, bindings have changed
            self.need_refresh_for_variable = {}
            self.need_refresh_for_tag = {}
            for i in b:
                if not isinstance(i[0], str):
                    raise ValueError(
                        f"First item in binding must be str, got {i[0]}"
                    )

                if not isinstance(i[1], list):
                    raise ValueError(
                        f"Second item in binding must be command list, got {i[1]}"
                    )

                evt_name: str = i[0]
                cmds: list[list[str]] = i[1]

                if evt_name not in self.event_listeners:
                    self.event_listeners[evt_name] = []

                self.event_listeners[evt_name].append(cmds)
                self.onBindingAdded(i)

            if "now" in self.event_listeners:
                self.event("now")
                del self.event_listeners["now"]

    def onBindingAdded(self, evt):
        "Called when a binding is added that listens to evt"

    def startTimers(self):
        needCheck = 0
        with self.gil:
            for i in self.event_listeners:
                if i and i.strip()[0] == "@":
                    if i not in self.time_events:
                        self.time_events[i] = ScheduleTimer(i, self)
                        self.onTimerChange(i, self.time_events[i].nextruntime)
                if i == "script.poll":
                    if not self.poller:
                        self.poller = scheduler.schedule_repeating(
                            self.poll, 1 / 24.0
                        )
                # Really just a fallback for various insta-check triggers like tag changes
                if i.strip().startswith("="):
                    if not self.slowpoller:
                        needCheck = True
                        self.slowpoller = scheduler.schedule_repeating(
                            self.checkPollEvents, 3
                        )

            # Run right away for faster response
            if needCheck:
                self.checkPollEvents()

    def poll(self):
        self.event("script.poll")

    def on_clearBindingsHook(self):
        pass

    def clearBindings(self):
        """Clear event bindings and associated data like timers.
        Don't clear any binding for an event listed in preserve.
        """
        with self.gil:
            self.event_listeners = {}
            for i in self.time_events:
                self.time_events[i].stop()
            self.time_events = {}

            if self.poller:
                self.poller.unregister()
                self.poller = None

            if self.slowpoller:
                self.slowpoller.unregister()
                self.slowpoller = None

            self.on_clearBindingsHook()

            # Odd behavior note: Clearing a binding resets the edge detect behavior
            self.risingEdgeDetects = {}

    def clearState(self):
        with self.gil:
            self.variables = {}
            self.changedVariables = {}
            for i in self.tagClaims:
                self.tagClaims[i].release()
            self.tagClaims = {}


class ChandlerScriptContext(BaseChandlerScriptContext):
    tagDefaultPrefix = "/sandbox/"

    def onTagChange(self, tagname, val, timestamp):
        """We make a best effort to run this synchronously. If we cannot,
        We let the background thread handle it.
        """

        def f():
            if isinstance(val, str) and len(val) > 16000:
                raise RuntimeError(f"{tagname} val too long for chandlerscript")
            self.setVar(f"$tag:{tagname}", val, True)
            if tagname not in self.need_refresh_for_tag:
                self.need_refresh_for_tag[tagname] = False
                for i in self.event_listeners:
                    if tagname in i:
                        self.need_refresh_for_tag[tagname] = True
            if self.need_refresh_for_tag[tagname]:
                self.checkPollEvents()

        if len(self.event_queue) > 128:
            raise RuntimeError("Too Many queued events!!!")

        # All tag point changes happen async
        self.do_async(f)

    def setupTag(self, tag):
        if tag in self.tagpoints:
            return

        def onchange(v, ts, an):
            self.onTagChange(tag.name, v, ts)

        tag.subscribe(onchange)
        self.need_refresh_for_tag[tag.name] = True
        self.tagHandlers[tag.name] = (tag, onchange)

    def canGetTagpoint(self, t):
        if t not in self.tagpoints and len(self.tagpoints) > 128:
            raise RuntimeError("Too many tagpoints")
        if t.startswith(self.tagDefaultPrefix):
            return t

    def specialVariableHook(self, k, v):
        if k.startswith("$tag:"):
            raise NameError(
                "Tagpoint variables are not writable. Use setTag(name, value, claimPriority)"
            )

    def on_clearBindingsHook(self):
        for i in self.tagHandlers:
            self.tagHandlers[i][0].unsubscribe(self.tagHandlers[i][1])

            try:
                self.setVar(f"$tag:{i}", "Unsubscribed", force=True)
            except Exception:
                pass

        # Clear all the tagpoints that we may have been watching for changes
        self.tagHandlers = {}
        self.tagpoints: dict[str, tagpoints.GenericTagPointClass[Any]] = {}
        self.need_refresh_for_variable = {}
        self.need_refresh_for_tag = {}

    def __init__(self, *a, **k):
        BaseChandlerScriptContext.__init__(self, *a, **k)

        def setTag(
            tagName=f"{self.tagDefaultPrefix}foo", value="=0", priority=75
        ):
            """Set a Tagpoint with the given claim priority.
            Use a value of None to unset existing tags. If the tag does not
            exist, the type is auto-guessed based on the type of the value.
            None will silently return and do nothing if the tag does not exist.
            """

            if not tagName[0] == "/":
                tagName = f"/{tagName}"

            self.need_refresh_for_tag = {}

            tagType = None
            priority = float(priority)
            if not tagType:
                if isinstance(value, str):
                    tagType = tagpoints.StringTag
                elif value is not None:
                    tagType = tagpoints.Tag
                elif value is None:
                    # Semi idempotence, no need to set if it is not already there.
                    if tagName not in self.tagClaims:
                        return True

            if tagType is None:
                raise ValueError("Could not guess proper tag type")

            if self.canGetTagpoint(tagName):
                if tagName in self.tagClaims:
                    tc = self.tagClaims[tagName]
                    if value is None:
                        tc.release()
                        del self.tagClaims[tagName]
                        return True
                else:
                    self.setupTag(tagType(tagName))
                    tc = tagType(tagName).claim(
                        value=value,
                        priority=priority,
                        name=f"{self.contextName}at{str(id(self))}",
                    )
                    self.tagClaims[tagName] = tc
                tc.set(value)
                self.setVar(f"$tag:{tagName}", value, True)
            else:
                raise RuntimeError("This script context cannot access that tag")
            return True

        self.setTag = setTag
        self.commands["set_tag"] = setTag
        setTag.completionTags = {"tagName": "tagPointsCompleter"}  # type: ignore

        def shell(cmd: str):
            """Run a system shell command line and return the output as the next command's _"""
            return (
                subprocess.check_output(cmd, shell=True, timeout=10)
                .decode("utf-8")
                .strip()
            )

        self.shell = shell
        self.commands["shell"] = shell
        self.tagpoints = {}
        self.tagHandlers = {}
        self.tagClaims = {}

        def tagpoint(t):
            tagName = self.canGetTagpoint(t)
            if not tagName:
                raise RuntimeError(f"It seems you do not have access to:{t}")
            t = tagpoints.Tag(tagName)
            self.setupTag(t)
            self.setVar(f"$tag:{t.name}", t.value, True)
            self.eval_times = max(t.timestamp, self.eval_times)
            return t.value

        def stringtagpoint(t):
            tagName = self.canGetTagpoint(t)
            if not tagName:
                raise RuntimeError(f"It seems you do not have access to:{t}")
            t = tagpoints.StringTag(tagName)
            self.setupTag(t)
            self.setVar(f"$tag:{t.name}", t.value, True)
            self.eval_times = max(t.timestamp, self.eval_times)
            return t.value

        c = {}

        c["tagValue"] = tagpoint
        c["tv"] = tagpoint

        c["stringTagValue"] = stringtagpoint
        c["stv"] = stringtagpoint

        self.functions.update(c)


##### SELFTEST ##########


# c = ChandlerScriptContext()

# x = []
# desired = ["Playing Baseball", "A bat goes with a glove"]


# def baseball():
#     x.append("Playing Baseball")
#     return True


# def bat(a):
#     x.append(f"A bat goes with a {a}")
#     return None


# def no(*a, **k):
#     raise RuntimeError("This shouldn't run, the prev command returning None stops the pipe")


# c.commands["baseball"] = baseball
# c.commands["bat"] = bat
# c.commands["no"] = no
# c.commands

# b: list[list[str | list[list[str]]]] = [
#     ["window", [["baseball"], ["bat", "='glove'"], ["no", "this", "shouldn't", "run"]]],
#     ["test", [["set", "foo", "bar"]]],
# ]

# c.addBindings(b)

# # Bind event window to an action with three commands

# # Top level list of b is a list of event name,commands pairs.
# #
# # commands is a list of commands. Every action is a list where the first
# # Is th name of the command, and the rest are arguments.

# # Note that the first arg of bat stats with an equals sign
# # so it gets evaluated, just like a LibreOffice Calc cell.

# c.event("window")
# c.event("test")

# c.waitForEvents()

# if not x == desired:
#     raise RuntimeError("The ChandlerScript module isn't working as planned")
# if not c.variables["foo"] == "bar":
#     raise RuntimeError("The ChandlerScript module isn't working as planned")
