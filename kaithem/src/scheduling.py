# Copyright Daniel Dunn 2015,2016
# This file is part of Kaithem Automation.

# Kaithem Automation is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.

# Kaithem Automation is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Kaithem Automation.  If not, see <http://www.gnu.org/licenses/>.

from dataclasses import replace
import threading
import sys
import time
import traceback
import logging
import types
from . import workers, util

from scullery import messagebus

logger = logging.getLogger("system.scheduling")

localLogger = logging.getLogger("scheduling")


def handleFirstError(f):
    "Callback to deal with the first error from any given event"
    m = f.__module__
    messagebus.postMessage(
        "/system/notifications/errors",
        "Problem in scheduled event function: "
        + repr(f)
        + " in module: "
        + m
        + ", check logs for more info.",
    )


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

    def __init__(self, function, time):
        BaseEvent.__init__(self)
        self.f = util.universal_weakref(function)
        self.time = time
        self.errored = False
        self.stopped = False

    def schedule(self):
        scheduler.insert(self)

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
            # If we can, try to send the exception back whence it came
            try:
                from . import newevt

                newevt.eventsByModuleName(f.__module__)._handle_exception()
            except Exception:
                print(traceback.format_exc())

            try:
                if hasattr(f, "__name__") and hasattr(f, "__module__"):
                    logger.exception(
                        "Exception in scheduled function "
                        + f.__name__
                        + " of module "
                        + f.__module__
                    )
            except Exception:
                logger.exception("Exception in scheduled function " + repr(f))

        finally:
            del f

    def _unregister(self):
        scheduler.remove(self)

    # We want to use the worker pool to unregister so that we know which thread the scheduler.unregister call is
    # going to be in to prevent deadlocks. Also, we take a dummy var so we can use this as a weakref callback
    def unregister(self, dummy=None):
        self.stopped = True
        workers.do(self._unregister)


def shouldSkip(priority, interval, lateby, lastran):
    t = {
        "realtime": 200,
        "interactive": 0.8,
        "high": 0.5,
        "medium": 0.3,
        "low": 0.2,
        "verylow": 0.1,
    }
    maxlatency = {
        "realtime": 0,
        "interactive": 0.2,
        "high": 2,
        "medium": 3,
        "low": 10,
        "verylow": 60,
    }
    if lateby > t[priority]:
        if ((time.time() - lastran) + interval) < maxlatency[priority]:
            return True


class BaseRepeatingEvent(BaseEvent):
    """Does function every interval seconds in real time,
    and stops if you don't keep a reference to function"""

    def __init__(
        self,
        function,
        interval,
    ):
        BaseEvent.__init__(self)
        self.f = util.universal_weakref(function)
        self.fstr = str(function)
        self.interval = float(interval)

        # True if the event is in the scheduler queue or the worker queue,
        # And should only be set under lock
        self.scheduled = False

        self.errored = False
        self.lock = threading.Lock()
        self.lastrun = None
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
                f = self.fstr + "(dead)"
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
        """Insert self into the scheduler.
        Note for subclassing: The responsibility of this function to check if it is already scheduled, return if so,
        if not, if must reschedule itself by setting self.time to some time in the future.
        It must then call scheduler.insert(self)

        This must happen in a threadsafe and atomic way because the scheduler thread will call this every once in a while,
        just to be sure, in case an error occurred in the reschedule process

        We implement this at the moment by having a separate _schedule functinon for when we are already under self.lock
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
                "Tried to schedule something that is still running: " + str(self.f())
            )

    def _schedule(self):
        raise NotImplementedError()

    def register(self):
        self.stop = False
        scheduler.register_repeating(self)

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
                # If we can, try to send the exception back whence it came
                try:
                    from . import newevt

                    if f.__module__.startswith("Event_"):
                        newevt.eventsByModuleName[f.__module__]._handle_exception()
                except:
                    print(traceback.format_exc())

                try:
                    if hasattr(f, "__name__") and hasattr(f, "__module__"):
                        localLogger.exception(
                            "Exception in scheduled function "
                            + f.__name__
                            + " of module "
                            + f.__module__
                        )

                except:
                    localLogger.exception("Exception in scheduled function")

                if not self.errored:
                    try:
                        try:
                            logger.exception(
                                "Exception in scheduled function "
                                + f.__name__
                                + " of module "
                                + f.__module__
                            )
                        except:
                            logger.exception("Exception in scheduled function")
                        handleFirstError(f)
                    except:
                        logging.exception(
                            "Error handling first error in repeating event"
                        )
                self.errored = True
            finally:
                # We have to reschedule no matter what.
                try:
                    self._schedule()
                except:
                    # Don't even trust logging here. I'm being extremely paranoid about a deadlock.
                    try:
                        logging.exception("Error scheduling")
                    except:
                        print(traceback.format_exc(6))
                self.lock.release()
                del f
                sys.last_traceback = None
        else:
            print(self.lock)


class UnsynchronizedRepeatingEvent(BaseRepeatingEvent):
    """Represents a repeating event that is not synced to the real time exactly"""

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
        scheduler.insert(self)


class RepeatWhileEvent(UnsynchronizedRepeatingEvent):
    "Does function every interval seconds, and stops if you don't keep a reference to function"

    def __init__(self, function, interval):
        self.ended = False
        UnsynchronizedRepeatingEvent.__init__(self, function, interval)

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


# class ComplexRecurringEvent():
# def schedule(self):
# if self.scheduled:
# return
# else:
# t = self.schedulefunc(self.last)
# if t<time.time():
# if self.makeup:
# n = self.schedulefunc(t)
# x = (t+n)/2
# self.scheduled = t
# s


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
        import sched

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

    def everySecond(self, f):
        e = UnsynchronizedRepeatingEvent(f, 1)
        e.register()
        e.schedule()
        return f

    def everyMinute(self, f):
        e = UnsynchronizedRepeatingEvent(f, 60)
        e.register()
        e.schedule()
        return f

    def everyHour(self, f):
        e = UnsynchronizedRepeatingEvent(f, 3600)
        e.register()
        e.schedule()
        return f

    def every(self, f, interval):
        interval = float(interval)
        e = UnsynchronizedRepeatingEvent(f, interval)
        e.register()
        e.schedule()
        if isinstance(f, types.MethodType):

            def f2():
                f()

        else:
            f2 = f
        f2.unregister = lambda: e.unregister()
        return f2

    def schedule(self, f, t, exact=False):
        t = float(t)
        e = Event(f, t)
        e.schedule()
        return e

    def scheduleRepeating(self, f, t, sync=True):
        e = UnsynchronizedRepeatingEvent(f, float(t))

        e.register()
        e.schedule()
        return e

    def insert(self, event, replaces=None):
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
            except:
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
                except:
                    logger.exception(
                        "failed to remove event, perhaps it was not actually scheduled"
                    )

            except:
                logger.exception("failed to unregister event")

    def manager(self):
        while 1:
            time.sleep(30)
            with self.lock:
                self._dorErrorRecovery()

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

    def _dorErrorRecovery(self):
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
            except:
                logger.exception("Exception while scheduling event")


scheduler = NewScheduler()
scheduler.start()


# If either of these doesn't run at the right time, raise a message
selftest = [time.monotonic(), time.monotonic()]

lastpost = [0]


def a():
    selftest[0] = time.monotonic()
    if selftest[1] < time.monotonic() - 40:
        if lastpost[0] < time.monotonic() - 600:
            lastpost[0] = time.monotonic()
            messagebus.postMessage(
                "/system/notifications/errors",
                "Something caused a scheduler continual selftest function not to run.",
            )


def b():
    selftest[1] = time.monotonic()
    if selftest[0] < time.monotonic() - 40:
        if lastpost[0] < time.monotonic() - 600:
            lastpost[0] = time.monotonic()
            messagebus.postMessage(
                "/system/notifications/errors",
                "Something caused a scheduler continual selftest function not to run.",
            )


scheduler.every(a, 20)
scheduler.every(b, 20)
