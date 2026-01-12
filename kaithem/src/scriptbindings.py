from __future__ import annotations

# SPDX-FileCopyrightText: Copyright 2013 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-or-later
import copy
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
from types import FunctionType, MethodType
from typing import Any, TypedDict

import pydantic
import simpleeval
from scullery import workers
from scullery.scheduling import scheduler

from kaithem.api import lifespan

from . import settings_overrides, tagpoints, util

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
        {"name":"foo","type":"str","default":"bar"},
        {"name":"bar","type":"int","default":"1"}
    ]
}

This allows GUIs to auto-generate a UI for visually creating pipelines.

If there is an unrecognized type, it is treated as a string.
"""


simpleeval.MAX_POWER = 1024


# Command metadata type definitions
class CommandArgManifest(TypedDict):
    """Metadata for a single command argument."""

    name: str  # Parameter name
    type: str  # Type hint string (str, float, int, bool, etc)
    default: str  # UI display default (must be explicit string)


class CommandManifest(TypedDict):
    """Metadata for a complete command function."""

    doc: str  # Docstring/description
    args: list[CommandArgManifest]  # List of arguments


class EventBindingCommandConfig(TypedDict):
    command: str


class LoadedEventBindingCommand(TypedDict):
    command: FunctionBlock


class EventBindingPipelineConfig(TypedDict):
    event: str
    commands: list[EventBindingCommandConfig]


class LoadedEventBindingPipeline(TypedDict):
    event: str
    commands: list[LoadedEventBindingCommand]


class NamespaceGetter:
    "Takes a dict and a prefix. Responds to attr requests with dict[prefix+.+key]"

    def __init__(self, d, prefix):
        self.__attr_prefix = prefix
        self.__attr_dict = d

    def __getattr__(self, k):
        return self.__attr_dict[f"{self.__attr_prefix}.{k}"]


def paramDefault(p):
    if p.name == "self":
        return None
    if (
        p.kind == p.POSITIONAL_ONLY
        or p.kind == p.VAR_POSITIONAL
        or p.kind == p.VAR_KEYWORD
    ):
        return None

    p = p.default
    if isinstance(p, int | float):
        return f"{str(p)}"

    if isinstance(p, str):
        return str(p)

    if isinstance(p, bool):
        return 1 if p else 0

    if p is None:
        return ""
    return ""


def _extract_type_hint(annotation) -> str:
    """Extract simple type string from annotation.

    Args:
        annotation: Parameter annotation from inspect.Parameter

    Returns:
        Simple type string (e.g., 'str', 'float', 'int')
    """
    if annotation is inspect.Parameter.empty:
        return "str"  # Default to string

    type_str = str(annotation)
    # Handle common patterns: <class 'str'> -> 'str'
    if type_str.startswith("<class '"):
        return type_str.split("'")[1]
    # Handle typing module types like str | int
    if " | " in type_str:
        # Return first type in union
        return type_str.split(" | ")[0].strip().replace("'", "")
    return "str"


def get_function_info(
    f: Callable[..., Any] | type[FunctionBlock],
) -> CommandManifest:
    """Extract complete metadata from function signature.

    Returns metadata with enhanced arg information:
    {
        "doc": "...",
        "args": [
            {"name": "argname", "type": "str", "default": ""},
            ...
        ],
    }

    Note: defaults are returned as empty strings. Explicit manifests should
    provide proper UI defaults. This fallback is used only for functions
    without explicit manifest attributes.
    """
    if isinstance(f, type(FunctionBlock)):
        f = f.__call__
    sig = inspect.signature(f)
    p = sig.parameters

    # Build enhanced args list with name, type, and empty default
    args: list[CommandArgManifest] = []
    for param_name, param in p.items():
        # Skip 'self' parameter
        if param_name == "self":
            continue
        # Skip *args and **kwargs
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        # Skip parameters with no defaults (required parameters)
        if param.default is param.empty:
            continue

        arg_info: CommandArgManifest = {
            "name": param_name,
            "type": "any",
            "default": "",  # Explicit manifests must provide UI defaults
        }
        args.append(arg_info)

    d: CommandManifest = {
        "doc": inspect.getdoc(f) or "",
        "args": args,
    }
    return d


def getContextFunctionInfo(f):
    p = inspect.signature(f).parameters
    d = {
        "doc": inspect.getdoc(f),
        "args": [[i, paramDefault(p[i])] for i in p][1:],
    }

    return d


def safesqrt(x):
    if x > 10**30:
        raise RuntimeError("Too High of number for sqrt")
    return math.sqrt(x)


def millis():
    return time.monotonic() * 1000


def cfg(key: str):
    return settings_overrides.get_val(key)


# API subject to change, user defined blocks not supported yets
class FunctionBlock:
    doc: str = ""
    args: list[CommandArgManifest] = []

    @classmethod
    def manifest(cls) -> CommandManifest:
        """Build manifest from class attributes."""
        m: CommandManifest = {"doc": cls.doc, "args": cls.args}
        return m

    def get_script_context(self) -> BaseChandlerScriptContext:
        return context_info.engine

    def get_underscore_val(self) -> Any:
        return context_info.engine.variables.get("_")

    def __init__(self, ctx: BaseChandlerScriptContext, *args, **kwargs):
        self.ctx = ctx

    def call(self, *args, **kwargs):
        raise NotImplementedError

    def close(self):
        pass


class StatelessFunction(FunctionBlock):
    """Base class for stateless command functions.

    Define command metadata as class attributes (doc, args).
    The manifest property auto-builds CommandManifest from these attributes.
    """


class OnChangeBlock(FunctionBlock):
    doc = "Trigger only when input value changes from previous input"
    args = [{"name": "input", "type": "str", "default": "=_"}]

    def __init__(self, ctx: ChandlerScriptContext, *args, **kwargs):
        self.lastValue = None

    def call(self, input: Any = "=_", **kwds: Any) -> Any:
        """
        If the input is the same as the last input, or this is the first input, return None
        """
        if self.lastValue is None:
            self.lastValue = input
        elif self.lastValue == input:
            return None
        else:
            self.lastValue = input
            return self.lastValue


class OnRisingEdgeBlock(FunctionBlock):
    doc = "Trigger only when input value changes from falsy to truthy"
    args = [{"name": "input", "type": "str", "default": "=_"}]

    def __init__(self, ctx: ChandlerScriptContext, *args, **kwargs):
        self.lastValue = True

    def call(self, input: Any = "=_", **kwds: Any) -> Any:
        if self.lastValue:
            self.lastValue = input
            return None
        if not input:
            self.lastValue = input
            return None
        else:
            self.lastValue = input
            return self.lastValue


class OnCounterIncreaseBlock(FunctionBlock):
    doc = "Trigger when the counter increases, or when it wraps back around"
    args = [{"name": "input", "type": "str", "default": "=_"}]

    def __init__(self, ctx: ChandlerScriptContext, *args, **kwargs):
        self.lastValue = None

    def call(self, input=0, **kwds: Any) -> Any:
        if self.lastValue is None:
            self.lastValue = input
        elif self.lastValue == input:
            return None

        # When the counter wraps around
        # If the difference is less that 255, it's probably not wrapping,
        # It's probably just a race.
        elif (input < self.lastValue) and (self.lastValue - input) < 255:
            self.lastValue = input
            return None
        else:
            self.lastValue = input
            return self.lastValue


class LowPassFilterBlock(FunctionBlock):
    doc = "Low pass filter with the given time constant"
    args = [
        {"name": "input", "type": "number", "default": "=_"},
        {"name": "tc", "type": "number", "default": "1.0"},
    ]

    def __init__(self, ctx: ChandlerScriptContext, *args, **kwargs):
        self.state: float = 0.0
        self.t = 0

    def call(self, input="=_", tc="1.0", **kwds: Any) -> Any:
        if self.t == 0:
            self.t = time.time()
            self.state = input  # type: ignore
            return input

        sps = 1 / (time.time() - self.t)
        self.t = time.time()

        # Don't allow sudden jumps, even if the time constant says otherwise
        if sps < 1:
            sps = 1

        # Approximate the blend amount
        # This is an AI generated approximation
        x = tc * sps  # type: ignore
        # This line added by trial and error
        x = x * 2
        x = 1.0 - x / (1.0 + x + 0.5 * x * x)  # type: ignore

        self.state = x * self.state + (1 - x) * input  # type: ignore

        return self.state


class CooldownBlock(FunctionBlock):
    doc = "Continue executing rule only N times per T seconds"
    args = [
        {"name": "limit", "type": "number", "default": "1"},
        {"name": "window", "type": "number", "default": "1.0"},
    ]

    def __init__(self, ctx: ChandlerScriptContext, *args, **kwargs):
        self.credits = 0
        self.timestamp = 0

    def call(self, limit="1", window="1.0", **kwds: Any) -> Any:
        self.credits = min(
            float(limit),
            self.credits
            + ((time.monotonic() - self.timestamp) / float(window)),
        )
        self.timestamp = time.monotonic()

        if self.credits >= 1:
            self.credits -= 1
            return self.get_underscore_val()

        return None


class HysteresisBlock(FunctionBlock):
    doc = "Add hysteresis to the input.  Only continues when changes are bigger than the window. "
    args = [
        {"name": "input", "type": "number", "default": "=_"},
        {"name": "window", "type": "number", "default": "1.0"},
    ]

    def __init__(self, ctx: ChandlerScriptContext, *args, **kwargs):
        self.lastMark = None

    def call(self, input=0.0, window=1.0, **kwds: Any) -> Any:
        v: float = input  # type: ignore
        w: float = window / 2  # type: ignore

        if self.lastMark is None:
            self.lastMark = v
            return None

        elif v > self.lastMark + w:
            self.lastMark = v - w
            return v
        elif v < self.lastMark - w:
            self.lastMark = v + w
            return v

        return None


globalUsrFunctions = {
    "unixtime": time.time,
    "millis": millis,
    "random": random.random,
    "randint": random.randint,
    "floor": math.floor,
    "max": max,
    "min": min,
    "log": math.log,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "sqrt": safesqrt,
    "cfg": cfg,
}


globalConstants = {"e": math.e, "pi": math.pi}


class ReturnValue(StatelessFunction):
    doc = "Returns the parameter x, and continues the action (Unless the value is None)"
    args = [{"name": "x", "type": "any", "default": ""}]

    def call(self, x):
        return x


class PassAction(StatelessFunction):
    doc = "Does nothing and returns True, continuing the action"
    args = []

    def call(self):
        return True


class Maybe(StatelessFunction):
    doc = "Return True with some percent chance, else stop the action"
    args = [{"name": "chance", "type": "number", "default": "50"}]

    def call(self, chance=50):
        return True if random.random() * 100 > chance else None


class ContinueIf(StatelessFunction):
    doc = "Continue if the first parameter is True. The param can be an expression like '= event.value=50'"
    args = [{"name": "v", "type": "str", "default": ""}]

    def call(self, v):
        return True if v else None


class SetTag(FunctionBlock):
    doc = (
        "Set a Tagpoint. If a priority is given, set the given claim priority."
    )
    args = [
        {
            "name": "tag",
            "type": "TagpointName",
            "default": "foo",
        },
        {"name": "value", "type": "any", "default": "=0"},
        {"name": "priority", "type": "number", "default": "0"},
    ]

    def __init__(self, ctx: ChandlerScriptContext, *args, **kwargs):
        super().__init__(ctx, *args, **kwargs)
        self.tagpoints = {}
        self.tagHandlers = {}
        self.tagClaims = {}

    def close(self):
        for i in self.tagClaims:
            if not self.tagClaims[i].name == "default":
                self.tagClaims[i].release()
        self.tagClaims = {}

    def call(
        self,
        tag="chandlerscript_tag_foo",
        value: float | int | str = 0,
        priority=0,
    ):
        """Set a Tagpoint.

        If a priority is given, set the given claim priority, and the claim
        will persist until it is released or the group is stopped.

        If priority empty or zero, just set the default base value layer,
        and the value will stay until overwritten or the tag is deleted.

        Use a value of None to unset existing tags. If the tag does not

        exist, the type is auto-guessed based on the type of the value.
        None will silently return and do nothing if the tag does not exist.
        """

        if not tag[0] == "/":
            tag = f"/{tag}"

        tagType = None
        if str(priority).strip():
            priority = float(priority)
        else:
            priority = None

        if not tagType:
            if isinstance(value, str):
                tagType = tagpoints.StringTag
            elif value is not None:
                tagType = tagpoints.Tag
            elif value is None:
                # Semi idempotence, no need to set if it is not already there.
                if tag not in self.tagClaims:
                    return True

        if tagType is None:
            raise ValueError("Could not guess proper tag type")

        if tag in self.tagClaims:
            tc = self.tagClaims[tag]
            if value is None:
                tc.release()
                del self.tagClaims[tag]
                return True
            else:
                tc.set(value)
                self.get_script_context().setVar(f"$tag:{tag}", value, True)
        else:
            self.tagpoints[tag] = tagType(tag)

            if priority:
                tc = tagType(tag).claim(
                    value=value,  # type: ignore
                    priority=priority,
                    name="ChandlerFunctionBlock",
                )
            else:
                tc = tagType(tag).default_claim

            self.tagClaims[tag] = tc

            tc.set(value)
            self.get_script_context().setVar(f"$tag:{tag}", value, True)

        return True


class Shell(StatelessFunction):
    doc = "Run a system shell command line and return the output as the next command's _"
    args = [{"name": "cmd", "type": "str", "default": ""}]

    def call(self, cmd: str):
        """Run a system shell command line and return the output as the next command's _"""
        return (
            subprocess.check_output(cmd, shell=True, timeout=10)
            .decode("utf-8")
            .strip()
        )


# Use context_info.event from inside any function, the value will be a (name,value) tuple for the event
context_info = threading.local()

predefinedcommands: dict[str, type[FunctionBlock]] = {
    "return": ReturnValue,
    "pass": PassAction,
    "maybe": Maybe,
    "continue_if": ContinueIf,
    "on_change": OnChangeBlock,
    "lowpass": LowPassFilterBlock,
    "hysteresis": HysteresisBlock,
    "on_rising_edge": OnRisingEdgeBlock,
    "on_count": OnCounterIncreaseBlock,
    "cooldown": CooldownBlock,
    "set_tag": SetTag,
    "shell": Shell,
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
        self.nextruntime = nextruntime.timestamp()
        self.next = scheduler.schedule(self.handler, self.nextruntime, False)

    def handler(self, *a, **k):
        nextruntime = self.selector.after(datetime.datetime.now(), False)
        ctx = self.context()

        # We don't want to reschedule if the context no longer exists
        if not ctx:
            return
        try:
            ctx.event(self.eventName)

            self.nextruntime = nextruntime.timestamp()
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


class ScriptActionKeeper:
    """This typecheck wrapper is courtesy
    of two hours spent debugging at 2am, and my desire to avoid repeating that"""

    def __init__(self):
        self.scriptcommands: weakref.WeakValueDictionary[
            str, type[FunctionBlock]
        ] = weakref.WeakValueDictionary()
        self.debug_refs = {}

    def __setitem__(self, key, value: type[FunctionBlock] | FunctionType):
        if not isinstance(key, str):
            raise TypeError("Keys must be string function names")

        if isinstance(value, MethodType):
            raise TypeError("Bound method type not supported")

        if not (
            isinstance(value, FunctionType)
            or isinstance(value, type(FunctionBlock))
        ):
            raise TypeError(
                "Script commands must be functions, StatelessFunction instances, or subclasses of FunctionBlock"
            )

        if isinstance(value, FunctionType):

            class LegacyFunctionWrapper(StatelessFunction):
                doc = get_function_info(value)["doc"]
                args = get_function_info(value)["args"]

                def call(self, *args, **kwargs):
                    return value(*args, **kwargs)

            self.scriptcommands[key] = LegacyFunctionWrapper
        else:
            self.scriptcommands[key] = value

        # Cache metadata at registration time
        if hasattr(value, "manifest"):
            manifest: CommandManifest = value.manifest()  # type: ignore
            self._validate_manifest(key, value, manifest)

        def warn_chandler_gc(x):
            # Lifespan will be None during system exit
            if lifespan and not lifespan.is_shutting_down:
                print(f"Chandler action {key} is no longer valid")

        self.debug_refs[key] = weakref.ref(value, warn_chandler_gc)

    def __getitem__(self, key):
        return self.scriptcommands[key]

    def __contains__(self, key):
        return key in self.scriptcommands

    def get(self, k, d):
        return self.scriptcommands.get(k, d)

    def _validate_manifest(
        self,
        name: str,
        func: Callable[..., Any] | type[FunctionBlock] | StatelessFunction,
        manifest: CommandManifest,
    ) -> None:
        """Validate that manifest matches function signature."""
        if isinstance(func, type(FunctionBlock)):
            sig = inspect.signature(func.call)
        elif isinstance(func, StatelessFunction):
            sig = inspect.signature(func.call)
        else:
            sig = inspect.signature(func)

        params = [p for p in sig.parameters if p != "self"]
        manifest_args = [arg["name"] for arg in manifest["args"]]

        if params != manifest_args:
            raise ValueError(
                f"Command '{name}' manifest args {manifest_args} "
                f"don't match signature params {params}"
            )


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
        self.event_listeners: list[LoadedEventBindingPipeline] = []

        self.variables: dict[str, Any] = (
            variables if variables is not None else {}
        )
        self.commands = ScriptActionKeeper()

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
                    if i["event"].startswith("="):
                        self.eval_times = 0
                        r = self.preprocessArgument(i["event"])
                        self.event(
                            i["event"], r, self.eval_times or time.time()
                        )

                except Exception:
                    self.event(
                        "script.error",
                        f"{self.contextName}\n{traceback.format_exc(chain=True)}",
                    )
                    raise

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

    def lookup_command(self, c: str) -> type[FunctionBlock]:
        a = self.commands.get(c, None)
        if a:
            return a
        if self.parentContext:
            return self.parentContext.lookup_command(c)
        else:
            if c in predefinedcommands:
                return predefinedcommands[c]

        raise ValueError(f"No such command: {c}")

    def _runCommand(self, c: LoadedEventBindingCommand):
        # ContextCommands take precedence
        f: Callable = c["command"].call

        args = {}
        for i in c:
            if i != "command":
                args[i] = self.preprocessArgument(c[i])

        return f(**args)

    def stopAfterThisHandler(self):
        "Don't handle any more bindings for this event, but continue the current binding"
        self.stopScriptFlag = True

    def event(self, evt, val=None, timestamp=None, sync=False):
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

        if sync:
            f()
        else:
            self.do_async(f)

    def _event(self, evt, val, depth, timestamp=None):
        handled = False

        # Tell any functions we call that they are running at elevated depth.
        self.eventRecursionDepth.d = depth + 1
        context_info.engine = self

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
                for pipeline in self.event_listeners:
                    if evt == pipeline["event"]:
                        handled = True
                        if self.stopScriptFlag:
                            break
                        for command in pipeline["commands"]:
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
            self.need_refresh_for_variable[n] = True
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

    def addBindings(
        self,
        b: list[EventBindingPipelineConfig] | list[list[str | list[list[str]]]],
    ):
        """Add bindings, auto-converting old list format to dict format if needed."""
        if not b:
            return

        # Auto-detect format and convert old lists to dicts
        if isinstance(b[0], list):
            self.addBindingsFromDict(self.migrate_old_bindings(b))  # type: ignore
        else:
            self.addBindingsFromDict(b)  # type: ignore

    def migrate_old_bindings(
        self, old_bindings: list[list[str | list[list[str]]]]
    ) -> list[EventBindingPipelineConfig]:
        """Convert old list format to dict format.

        Old format: [["event", [["cmd", "arg1"], ["cmd2"]]]]
        New format: [{"event": "evt", "commands": [{"command": "cmd", ...}]}]
        """
        result = []

        for binding in old_bindings:
            if not isinstance(binding, list) or len(binding) < 2:
                continue

            event_name = binding[0]
            assert isinstance(event_name, str)

            commands = binding[1] if isinstance(binding[1], list) else []

            if event_name.startswith("=+"):
                event_name = "=" + event_name[2:]
                commands = [["on_count", "=_"]] + commands

            elif event_name.startswith("=~"):
                event_name = "=" + event_name[2:]
                commands = [["on_change", "=_"]] + commands

            elif event_name.startswith("=/"):
                event_name = "=" + event_name[2:]
                commands = [["on_rising_edge", "=_"]] + commands

            elif event_name.startswith("="):
                commands = [["continue_if", "=_ > 0"]] + commands

            actions = []
            for cmd in commands:
                if not isinstance(cmd, list) or not cmd:
                    raise ValueError(f"Invalid binding: {binding}")

                cmd_name = cmd[0]
                args = cmd[1:] if len(cmd) > 1 else []

                # Get expected arg names for this command
                arg_names = self._get_command_arg_names(cmd_name)

                # Build action dict with command and arguments
                action = {"command": cmd_name}
                for arg_name, arg_value in zip(arg_names, args):
                    action[arg_name] = arg_value

                actions.append(action)

            if event_name and actions:
                result.append({"event": event_name, "commands": actions})

        return result

    def _import_dict_bindings(self, rules: list[EventBindingPipelineConfig]):
        """Import dict-format bindings directly.

        Args:
            rules: Rules in dict format [{"event": "evt", "commands": [...]}]
        """
        rules = copy.deepcopy(rules)
        loaded_rules: list[LoadedEventBindingPipeline] = []
        has_now = False

        with self.gil:
            for rule in rules:
                event_name = rule.get("event", "")

                if event_name == "now":
                    has_now = True

                actions: list[EventBindingCommandConfig] = rule["commands"]

                loaded_actions: list[LoadedEventBindingCommand] = []

                for action in actions:
                    cmd_name = action.get("command", "")
                    if not cmd_name:
                        raise ValueError(
                            "Missing command in action: " + str(action)
                        )

                    # Handle FunctionBlock instantiation
                    x = self.lookup_command(cmd_name)
                    cmd = x(self)

                    a: LoadedEventBindingCommand = action  # type: ignore
                    a["command"] = cmd

                    loaded_actions.append(a)
                loaded_rules.append(
                    {"event": event_name, "commands": loaded_actions}
                )

            self.event_listeners.extend(loaded_rules)

        if has_now:
            self.event("now")
            self.event_listeners = [
                i for i in self.event_listeners if i["event"] != "now"
            ]

        # Need to do this at least once to make the bindings know what to
        # Listen to
        self.checkPollEvents()

    def addBindingsFromDict(self, rules: list[EventBindingPipelineConfig]):
        """Add bindings from dict format.

        Native execution format: [{"event": "evt", "commands": [...]}]

        Args:
            rules: Rules in dict format
        """
        self._import_dict_bindings(rules)

    def _get_command_arg_names(self, cmd_name: str) -> list[str]:
        """Get parameter names in order for a command using cached metadata.

        Args:
            cmd_name: Name of the command

        Returns:
            List of parameter names in order, from cached metadata
        """

        # Check parent context
        cmd = self.lookup_command(cmd_name)

        return [arg["name"] for arg in cmd.manifest()["args"]]

    def onBindingAdded(self, evt):
        "Called when a binding is added that listens to evt"

    def startTimers(self):
        needCheck = 0
        with self.gil:
            for i in self.event_listeners:
                event_name = i["event"]
                if event_name.strip()[0] == "@":
                    if event_name not in self.time_events:
                        self.time_events[event_name] = ScheduleTimer(
                            event_name, self
                        )
                        self.onTimerChange(
                            event_name, self.time_events[event_name].nextruntime
                        )
                if event_name == "script.poll":
                    if not self.poller:
                        self.poller = scheduler.schedule_repeating(
                            self.poll, 1 / 24.0
                        )
                # Really just a fallback for various insta-check triggers like tag changes
                if event_name.strip().startswith("="):
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
        """Clear event bindings and associated data like timers."""
        with self.gil:
            for i in self.event_listeners:
                for j in i["commands"]:
                    if not isinstance(j["command"], StatelessFunction):
                        j["command"].close()

            # Cache is invalidated, bindings have changed
            self.need_refresh_for_variable = {}
            self.need_refresh_for_tag = {}

            self.event_listeners = []
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
        """Only called manually at times like stopping a chandler group"""
        with self.gil:
            self.clearBindings()

            self.variables = {}
            self.changedVariables = {}


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

    def setupTag(self, tag: tagpoints.GenericTagPointClass[Any]):
        if tag.name in self.tagpoints:
            return

        def onchange(v, ts, an):
            self.onTagChange(tag.name, v, ts)

        tag.subscribe(onchange)
        self.need_refresh_for_tag[tag.name] = True
        self.tagHandlers[tag.name] = (tag, onchange)
        self.tagpoints[tag.name] = tag

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

    def __init__(self, *a, **k):
        BaseChandlerScriptContext.__init__(self, *a, **k)

        self.tagHandlers = {}
        self.tagpoints: dict[str, tagpoints.GenericTagPointClass[Any]] = {}

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


@pydantic.validate_call(
    config=pydantic.ConfigDict(arbitrary_types_allowed=True)
)
def migrate_rules(
    context: BaseChandlerScriptContext,
    rules: list[list[str | list[list[str]]]] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if len(rules) == 0:
        return []
    if isinstance(rules[0], list):
        return context.migrate_old_bindings(rules)  # type: ignore
    return rules  # type: ignore


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
