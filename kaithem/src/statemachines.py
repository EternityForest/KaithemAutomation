# SPDX-FileCopyrightText: Copyright 2016 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import time
import threading
import weakref
from typeguard import typechecked
from typing import Callable, Any
from scullery import workers, util

# Lets keep dependancies on things within kaithem to a minimum, as eventually this might be spun off to a standalone thing
from . import scheduling

#
# StateMachine API
#
# sm= StateMachine()
#
# Create an object representing one nondeterministic finite automaton
#
# sm.add_state("stateName", [enter, exit])
#
# Add a state to the machine. Enter and exit may be functions to be called when the state enters or leaves. If the state
# already exists, it will be replaced
#
# sm.addRule("startState", "ExampleEvent", "destinationState")
#
# Add a rule to handle what should happen if event occurs while the machine is in state.
# The third parameter representing the destination state may also be a function. The function must take one parameter, the machine itself,
# and return either None for no Transiton or a string representing the new state. This lets you implement conditions and branchingself.
#
# sm.addTimer("state",60, "newstate")
#
# Add a timer to state that will cause it to Transiton to newstate after 60 seconds. You can set the time to None to delete any existing timers,
# and you can use a function for the destination state just like for a normal rule. States may only have one timerself.
#


illegal_name_chars = "~!@#$%^&*()-=+`<>?,./;':\"\\[]{}\n\r\t "


def unboundProxy(self, f):
    def f2(*args, **kwargs):
        f(*args, **kwargs)

    return f2


def makechecker(ref: weakref.ref[StateMachine]):
    def timer_check():
        m = ref()
        if m:
            m._check_timer()

    return timer_check


def runSubscriber(f, state):
    f(state)


class UpdateControl:
    pass


class StateMachine:
    def __init__(self, start="start"):
        """
        Represents an State Machine or FSA
        Args:
            start (str, optional): _description_. The initial state. Defaults to "start".
        """

        self.states = {}
        self.state = start
        self.prev_state = None
        self.entered_state = time.time()
        # Used to ensure that if one leaves and reenters a state just as a timer is firing it does not trigger anything.
        self._transiton_count = 0
        self.lock = threading.RLock()

        # Subscribers, as lists of function weakrefs indexed by what state entrance they are subscribed to to
        self._subscribers: dict[str, list[weakref.ref[Callable]]] = {}

        # Used for skipping ahead to quickly test timers and things like that.
        self._time_offset = 0

    def __call__(self, event):
        "Trigger an event, return the current state"
        self.event(event)
        return self.state

    def __repr__(self):
        return "<State machine at %d in state %s, entered %d ago>" % (
            id(self),
            self.state,
            time.time() - self.entered_state,
        )

    def subscribe(self, f: Callable[[str], Any], state="__all__"):
        """Cause function f to be called when the machine enters the given state.
        If the state is __all__, causes
        f to be called whenever the state changes at all.
        Uses weak refs, so you must maintain a reference to f

        Args:
            f (_type_): The function
            state (str, optional): The specific state to subscribe to. Defaults to "__all__".
        """
        with self.lock:
            # First clean up old subscribers. This is slow to do thi every time, but it should be infrequent.
            for i in self._subscribers:
                self._subscribers[i] = [i for i in self._subscribers[state] if i()]
            self._subscribers = {
                i: self._subscribers[i]
                for i in self._subscribers
                if self._subscribers[i]
            }

            if state not in self._subscribers:
                self._subscribers[state] = []
            self._subscribers[state].append(util.universal_weakref(f))

    def unsubscribe(self, f: Callable[[str], Any], state="__all__"):
        """

        Args:
            f (_type_): The function
            state (str, optional): The specific state to unsub to. Defaults to "__all__".
        """
        with self.lock:
            for i in self._subscribers:
                self._subscribers[i] = [i for i in self._subscribers[state] if i()]
            self._subscribers = {
                i: self._subscribers[i]
                for i in self._subscribers
                if self._subscribers[i]
            }

            torm = None
            for i in self._subscribers[state]:
                if i() == f:
                    torm = i
            if torm:
                self._subscribers[state].remove(torm)

    @property
    def age(self):
        return time.time() - self.entered_state

    @property
    def stateage(self) -> tuple[str, float]:
        """_Get the state, and how long it's been in that state

        Returns:
            tuple[str, float]: The state and age of the state in seconds
        """
        with self.lock:
            return (self.state, time.time() - self.entered_state)

    def _check_timer(self):
        "Poll function for any timers on the state."
        with self.lock:
            if self.states[self.state].get("timer"):
                if (
                    (time.time() + self._time_offset) - self.entered_state
                ) > self.states[self.state]["timer"][0]:
                    # Get the destination
                    x = self.states[self.state]["timer"][1]

                    # If it's a function, call it to get the actual destination.
                    if isinstance(x, str):
                        self._goto(x)
                    else:
                        x = x(self)
                        if x:
                            self._goto(x)
                else:
                    self._configure_timer()

    def _configure_timer(self):
        "Sets up the timer. Needs to be called under lock"

        if hasattr(self, "schedulerobj"):
            self.schedulerobj.unregister()
            del self.schedulerobj

        # If for any reason we get here too early, let's just keep rescheduling
        if self.states[self.state].get("timer"):
            # If we haven't already passed the time of the timer
            if ((time.time() + self._time_offset) - self.entered_state) < self.states[
                self.state
            ]["timer"][0]:
                f = makechecker(util.universal_weakref(self))
                self.schedulerobj = scheduling.scheduler.schedule(f, time.time() + 0.08)

                # Keep a ref so it doesn't get GCed
                self.schedulerobj.func_ref = f  # type: ignore

            # If we have already passed that time, just do it now.
            # This is here for faster response when skipping ahead.
            else:
                workers.do(self._check_timer)

    def seek(self, t, condition=None):
        """
        Seek ahead to a given position in the curren state's timeline, but only if the"""
        with self.lock:
            if condition and (not condition == self.state):
                return
            pos = time.time() - self.entered_state
            self._time_offset = t - pos
            self._configure_timer()

    @typechecked
    def add_state(
        self,
        name: str,
        rules: None | dict[str, str | Callable[[], str | None]] = None,
        enter: str | Callable | None = None,
        exit: str | Callable | None = None,
    ):
        """
        Create a new state.  Keys in rules must be event names,
        and values must be either state names or callables that return
        either a state name to go to, or None for no transition.

        Args:
            name (str): Name of the state. May not contain anything in illegal_name_chars
            rules (dict, optional): Dict of rules for the state
            enter (str | Callable | None, optional): Function to be called when entering
            exit (str | Callable | None, optional): Function to be called when exiting

        Raises:
            ValueError: _description_
        """
        for i in illegal_name_chars:
            if i in name:
                raise ValueError("Forbidden special character")
        with self.lock:
            self.states[name] = {
                "rules": rules or {},
                "enter": enter,
                "exit": exit,
                "conditions": [],
            }

    def set_timer(self, state: str, time: float | int, dest: str | Callable):
        """Add timer rule to a state.  When machine is in state continually
        for that many seconds, go to dest.

        Args:
            state (str): Starting state
            time (float | int): Timer duration
            dest (str | Callable): Dest state or callable returning name of dest
        """
        with self.lock:
            if dest:
                self.states[state]["timer"] = [time, dest]

    def remove_state(self, name):
        raise RuntimeError("Not supported now")

    @typechecked
    def add_rule(self, start: str, event: str | Callable, to: str | Callable):
        with self.lock:
            if isinstance(event, str):
                self.states[start]["rules"][event] = to
            elif callable(event):
                self.states[start]["conditions"].append((event, to))
                self._setupPolling()

    def del_rule(self, start, event):
        with self.lock:
            if event in self.states[start]["rules"]:
                del self.states[start]["rules"][event]
            elif event in self.states[start]["conditions"]:
                del self.states[start]["conditions"][event]
            else:
                raise KeyError("No such rule")

    def event(self, event):
        """Tell the machine that a specific event just occurred. If there is a matching Transiton rule for that event,
        then we do the current state's exit func, enter the new state, and do it's enter func"""
        with self.lock:
            if self.state not in self.states:
                return self.state

            s = self.states[self.state]

            if event in s["rules"]:
                x = s["rules"][event]
                # If the rule destination is a string, just use it. If it is not a string, then
                # It must be a function because those are the only two valid destination types.

                # If it's a function, call it to get the actual destination.
                if isinstance(x, str):
                    self._goto(x)
                else:
                    x = x(self)
                    if x:
                        self._goto(x)
            return self.event

    def check(self):
        "Check the function based condition rules"
        with self.lock:
            s = self.states.get(self.state, None)
            if s:
                # Check all the function rules, poll them all,
                # and should any happen to be true, we follow that rule
                # Like any other.
                for i in s["conditions"]:
                    if i[0]():
                        self._goto(i[1])

    def jump(self, state, condition=None):
        self.goto(state, condition)

    def goto(self, state, condition=None):
        "Jump to a specified state. If condition is not None, only jump if it matches the current state else do nothing."
        with self.lock:
            if condition and not self.state == condition:
                return
            self._goto(state)

    def _setupPolling(self):
        "Start polling the function based events, if there are any to poll for"
        if hasattr(self, "pollingscheduledfunction"):
            self.pollingscheduledfunction.unregister()
            del self.pollingscheduledfunction

        if self.states[self.state].get("conditions"):
            self.pollingscheduledfunction = scheduling.scheduler.every(
                self.check, 1 / 24
            )

    def _goto(self, state):
        "Must be called under the lock"

        s = self.states[self.state]
        s2 = self.states[state]

        # Do the old state's exit function
        if s["exit"]:
            s["exit"]()

        self.prev_state = self.state
        self.state = state
        # Record the time that we entered the new state
        self.entered_state = time.time()
        self._configure_timer()

        self._time_offset = 0

        if hasattr(self, "schedulerobj"):
            self.schedulerobj.unregister()
            del self.schedulerobj

        if self.states[self.state].get("timer"):
            f = makechecker(util.universal_weakref(self))
            self.schedulerobj = scheduling.scheduler.schedule(
                f, time.time() + self.states[self.state].get("timer")[0]
            )

            # Keep a strong reference
            self.schedulerobj.func_ref = f  # type: ignore

        self._setupPolling()

        # Do the entrance function of the new state
        if s2["enter"]:
            s2["enter"]()

        # Handle the subscribers
        if state in self._subscribers:
            for i in self._subscribers[state]:
                x = i()
                if x:
                    runSubscriber(x, self.state)

        if "__all__" in self._subscribers:
            for i in self._subscribers["__all__"]:
                x = i()
                if x:
                    runSubscriber(x, self.state)

        # Increment the trans count. wrap at 2**64
        self._transiton_count = (self._transiton_count + 1) % 2**64
