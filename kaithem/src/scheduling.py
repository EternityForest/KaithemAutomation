# SPDX-FileCopyrightText: Copyright 2015 Daniel Dunn
# SPDX-License-Identifier: GPL-3.0-only
"""
Wraps the very simple scheduling module in a way that supports
repeating events, error reporting, and weakref-based cleanup.

Note that weakref cleanup is never a good idea to
rely on for correctness, it's just a tool to manage resources.

"""

import threading
import sys
import time
import sched
import traceback
import logging
import types
from . import workers, util
from typing import Callable, Any


logger = logging.getLogger("system.scheduling")

localLogger = logging.getLogger("scheduling")


# These hooks are called on any exception in a function
# And passed the function
function_error_hooks: list[Callable[[Callable[..., Any]], Any]] = []


def handle_first_error(f: Callable):
    "Callback to deal with the first error from any given event"
    logger.exception(f"Error in {f}")


enumerate = enumerate


class BaseEvent:
    def __init__(self):
        self.exact = 0
        self.schedID = None


# Event API(not public):
# _schedule: if schedule is false calculate next runtime, insert self, set scheduled flag to true.
# only call under lock

# schedule: acquire lock, if so call _schedule

# _run: acquire lock(or do nothing if already running)
# do the actual action, and reschedule self if it's a repeating event

# run: use the worker pool to run an event, or run directly if fast enough(under 1ms)


class Event(BaseEvent):
    "Does function at time provided there is a strong referemce to f still by then"

    def __init__(self, function: Callable[[], Any], time: float):
        """_summary_

        Args:
            function (Callable[[],Any]): The function to call
            time (float): The time.time() at which to schedule.
        """
        BaseEvent.__init__(self)
        self.f = util.universal_weakref(function)
        self.time = time
        self.errored = False
        self.stopped = False

    def schedule(self):
        scheduler._insert(self)

    def run(self):
        workers.do(self._run)

    def _run(self):
        if self.stopped:
            return
        try:
            f = self.f()
            if not f:
                self.unregister()
            else:
                f()
        except Exception:
            if f:
                for i in function_error_hooks:
                    i(f)
        finally:
            del f

    def _unregister(self):
        scheduler.remove(self)

    # We want to use the worker pool to unregister so
    # that we know which thread the scheduler.unregister call is
    # going to be in to prevent deadlocks.
    # Also, we take a dummy var so we can use this as a weakref callback
    def unregister(self, dummy: Any = None):
        "Cancel running the event"
        self.stopped = True
        workers.do(self._unregister)


class BaseRepeatingEvent(BaseEvent):
    """Does function every interval seconds in real time,
    and stops if you don't keep a reference to function"""

    def __init__(
        self,
        function: Callable[[], Any],
        interval: float,
    ):
        """
        Args:
            function (Callable[[],Any]): Function to call
            interval (float): Interval
        """
        BaseEvent.__init__(self)
        self.f = util.universal_weakref(function)
        self.fstr = str(function)
        self.interval = float(interval)

        # True if the event is in the scheduler queue or the worker queue,
        # And should only be set under lock
        self.scheduled = False

        self.errored = False
        self.lock = threading.Lock()
        self.lastrun = 0.0
        # This flag is here to slove a really annoying problem.
        # If you unregister just before the reschedule function acquires the lock,
        # The object just gets rescheduled like nothing happened.
        # This stop function ensures they actually stop.
        self.stop = False
        del function

    def __repr__(self) -> str:
        try:
            f = self.f()
            if not f:
                f = f"{self.fstr}(dead)"
            f = str(f)
            return (
                "<BaseRepeatingEvent at "
                + str(id(self))
                + f
                + " every "
                + str(self.interval)
                + "s >"
            )
        except Exception:
            print(traceback.format_exc())
            return super().__repr__()

    def schedule(self):
        """Insert self into the scheduler. Not normally called
        by user code on repeating events, use register()

        Note for subclassing: The responsibility of this function
        to check if it is already scheduled, return if so,
        if not, if must reschedule itself by setting self.time
        to some time in the future.
        It must then call scheduler._insert(self)

        This must happen in a threadsafe and atomic way
        because the scheduler thread will call
        this every once in a while, just to be sure,
        in case an error occurred in the reschedule process

        We implement this at the moment by having a
        separate _schedule functinon for when we are already
        under self.lock
        """
        if self.lock.acquire(timeout=0.5):
            try:
                if self.scheduled:
                    return
                if not self.lastrun:
                    self.lastrun = time.time()
                self._schedule()
            finally:
                self.lock.release()
        else:
            logger.warning(
                f"Tried to schedule something that is still running: {str(self.f())}"
            )

    def _schedule(self):
        raise NotImplementedError()

    def register(self):
        """Register self in the list of
        repeating events to be automatically scheduled."""
        self.stop = False
        scheduler.register_repeating(self)
        self.schedule()

    def _unregister(self):
        scheduler.unregister(self)

    # We want to use the worker pool to unregister so that we know which thread the scheduler.unregister call is
    # going to be in to prevent deadlocks. Also, we take a dummy var so we can use this as a weakref callback
    def unregister(self, dummy=None):
        self.stop = True
        workers.do(self._unregister)

    def run(self):
        workers.do(self._run)

    def _run(self):
        # Safe to set outside lock I think. If there is
        # more than one scheduled copy there's a problem anyway.
        self.scheduled = False

        if self.stop:
            return

        # Don't run way too fast but do allow some tolerance in the speed.
        if time.time() - self.lastrun < (self.interval / 3):
            return

        self.lastrun = time.time()

        # We must have been pulled out of the event queue or we wouldn't be running.
        # If somehow there is another copy, exit and let recovery reschedule us later.

        if self.lock.acquire(timeout=1):
            try:
                f = self.f()
                if not f:
                    self.unregister()
                else:
                    f()
                # self._schedule()
            except Exception:
                if f:
                    for i in function_error_hooks:
                        i(f)

                if not self.errored:
                    try:
                        global handle_first_error
                        if f:
                            handle_first_error(f)
                    except Exception:
                        logging.exception(
                            "Error handling first error in repeating event"
                        )
                self.errored = True
            finally:
                # We have to reschedule no matter what.
                try:
                    self._schedule()
                except Exception:
                    # Don't even trust logging here. I'm being extremely paranoid about a deadlock.
                    try:
                        logging.exception("Error scheduling")
                    except Exception:
                        print(traceback.format_exc(6))
                self.lock.release()
                del f
                sys.last_traceback = None
        else:
            print(self.lock)


class RepeatingEvent(BaseRepeatingEvent):
    """Represents a repeating event that is not synced to
    multiples of wall clock time"""

    def __init__(self, *args, **kwargs):
        BaseRepeatingEvent.__init__(self, *args, **kwargs)

    def _schedule(self):
        """Calculate next runtime and put self into the queue.
        Should only ever be called under lock"""
        if self.scheduled:
            return

        # Don't alow unlimited amounts of winding up a big queue.
        t = max((self.lastrun + self.interval), ((time.time() + self.interval) - 5))
        self.time = t
        self.scheduled = True
        scheduler._insert(self)


class RepeatWhileEvent(RepeatingEvent):
    "Does function every interval seconds, and stops if you don't keep a reference to function"

    def __init__(self, function, interval):
        self.ended = False
        RepeatingEvent.__init__(self, function, interval)

    def _run(self):
        if self.ended:
            return
        if self.lock.acquire(False):
            try:
                f = self.f()
                if not f:
                    self.unregister()
                else:
                    r = f()
                    if not r:
                        self.unregister()
                        self.ended = True
            finally:
                self.lock.release()
                del f


class NewScheduler:
    """
    represents a thread that constantly runs tasks which are objects having a time property that determins when
    their run method gets called. Inserted tasks use a lockless double buffered scheme.
    """

    def __init__(self):
        self.lock = threading.RLock()
        self.repeatingtasks = []
        self.daemon = True
        self.name = "SchedulerThread"
        self.lastrecheckedschedules = time.time()
        self.lf = time.time()
        self.running = False

        self.wakeUp = threading.Event()
        self.sched = sched.scheduler(timefunc=time.time, delayfunc=self.delay)

    def start(self):
        with self.lock:
            if self.running:
                return
            self.running = True
            self.thread = threading.Thread(
                daemon=self.daemon, target=self.run, name="schedulerthread"
            )
            self.thread2 = threading.Thread(
                daemon=self.daemon,
                target=self.manager,
                name="schedulerthread_errorrecovery",
            )

            self.thread.start()
            self.thread2.start()

    def every_second(self, f: Callable[[], Any]):
        e = RepeatingEvent(f, 1)
        e.register()
        return f

    def every_minute(self, f: Callable[[], Any]):
        e = RepeatingEvent(f, 60)
        e.register()
        return f

    def every_hour(self, f: Callable[[], Any]):
        e = RepeatingEvent(f, 3600)
        e.register()
        return f

    def every(self, f: Callable[[], Any], interval: float):
        interval = float(interval)
        e = RepeatingEvent(f, interval)
        e.register()
        if isinstance(f, types.MethodType):

            def f2():
                f()

        else:
            f2 = f
        f2.unregister = lambda: e.unregister()
        return f2

    def schedule(self, f: Callable[[], Any], t: float, exact=False):
        t = float(t)
        e = Event(f, t)
        e.schedule()
        return e

    def schedule_repeating(self, f: Callable[..., Any], t: float, sync: bool = True):
        e = RepeatingEvent(f, float(t))
        e.register()
        return e

    def _insert(self, event, replaces=None):
        """Insert something that has a time  and a run
        property that wants its run called at time
        """

        if replaces:
            try:
                self.sched.cancel(replaces)
            except Exception:
                pass

        event.schedID = self.sched.enterabs(event.time, 1, event.run)
        # Only very fast events need to use this wake mechanism that burns CPU.
        # We have a min 0.15hz poll rate
        if event.time < (time.time() + 0.15):
            self.wakeUp.set()

    def remove(self, event):
        "Remove something that has a time and a run property that wants its run to be called at time"
        with self.lock:
            try:
                self.sched.cancel(event.schedID)
            except ValueError:
                pass
            except Exception:
                logger.exception("failed to remove event")

    def register_repeating(self, event):
        "Register a RepeatingEvent class"
        with self.lock:
            self.repeatingtasks.append(event)

    def unregister(self, event):
        "unregister a RepeatingEvent"
        with self.lock:
            try:
                try:
                    if event in self.repeatingtasks:
                        self.repeatingtasks.remove(event)
                except KeyError:
                    pass

                try:
                    self.sched.cancel(event.schedID)
                except ValueError:
                    pass
                except Exception:
                    logger.exception(
                        "failed to remove event, perhaps it was not actually scheduled"
                    )

            except Exception:
                logger.exception("failed to unregister event")

    def manager(self):
        while 1:
            time.sleep(30)
            with self.lock:
                self._do_error_recovery()

    # Custom delay func because we must be able to recieve new events while waiting
    def delay(self, t):
        self.wakeUp.clear()
        self.wakeUp.wait(min(t, 0.15))

    def run(self):
        while 1:
            try:
                self.sched.run()
            except Exception:
                logging.exception("Error in scheduler thread")

    def _do_error_recovery(self):
        for i in self.repeatingtasks:
            try:
                if not i.scheduled or time.time() - i.lastrun > (i.interval * 2):
                    # Give them 10 seconds to finish what they are doing and schedule themselves.
                    if i.lastrun < time.time() - 10:
                        # Let's maybe not block the entire scheduling thread
                        # If one event takes a long time to schedule or if it
                        # Is already running and can't schedule yet.

                        # On the off chance it actually IS scheduled, replace whatever was there last.
                        workers.do(i.schedule)
                        logger.debug(
                            "Rescheduled "
                            + str(i)
                            + "using error recovery, could indicate a bug somewhere, or just a long running event."
                        )
            except Exception:
                logger.exception("Exception while scheduling event")


scheduler = NewScheduler()
scheduler.start()
