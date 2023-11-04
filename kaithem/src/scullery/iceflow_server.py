
# Copyright Daniel Dunn 2019
# This file is part of Kaithem Automation.

# Kaithem Automation is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.

# Kaithem Automation is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License

import threading
import time
import logging
import weakref
import traceback
import os
import sys
import base64
import math

# import workers  # , ]messagebus


def doNow(f):
    f()


initialized = False
initlock = threading.Lock()

lock = threading.RLock()
Gst = None
jackChannels = {}

stopflag =[0]

# Overridden later
print = print

rpc = [None]


def tryToAvoidSegfaults(t, v):
    if v.clientName == "system":
        stop_allJackUsers()




# https://stackoverflow.com/questions/568271/how-to-check-if-there-exists-a-process-with-a-given-pid-in-python
def check_pid(pid):
    """ Check For the existence of a unix pid. """
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True


#messagebus.subscribe("/system/jack/delport", tryToAvoidSegfaults)
pipes = weakref.WeakValueDictionary()

log = logging.getLogger("IceFlow_gst")


# This is NixOS compatibility stuff, we could be running as an output from setup.py
# Or we could be running directly with python3 file.py
try:
    from . import jsonrpyc
except ImportError:
    import jsonrpyc

class PresenceDetectorRegion():
    def __init__(self):
        # This is a first order filter(Time domain blur) of the entire image

        self.state = None
        self.last = None

    def poll(self, val):

        #
        from PIL import ImageFilter
        from PIL import ImageChops

        try:
            import scipy.ndimage
            ndim = 1
        except Exception:
            ndim = 0

        import numpy as np
        x = val

        self.last = x if x else self.last

        rval = 0
        if self.state:
            diff = ImageChops.difference(self.state, self.last)
            # This is an erosion operation to prioritize multipixel stuff
            # over single pixel noise
            d = diff.convert('F')

            if ndim:
                # This is like 4 times faster.
                d = scipy.ndimage.grey_erosion(d, (3, 3))
            else:
                d = d.filter(ImageFilter.MinFilter(3))
            d = np.array(d)

            # Ignore everythong below the threshold, that gets rid of a lot of our noise
            m = np.mean(d) * 1.5 + 4
            d = np.fmax(d - m, 0)

            x = np.mean(d * d)
            if x == 0:
                rval = 0

            rval = math.sqrt(x) / 2.5

        self.state = self.last
        return rval


class PresenceDetector():
    def __init__(self, capture, regions=None):
        self.masks = regions
        self.regions = {}
        self.entireImage = PresenceDetectorRegion()
        self.capture = capture

        if regions is not None:
            for i in regions:
                self.regions[i] = PresenceDetectorRegion()

    def poll(self):
        r = {}

        x = self.capture.pull()
        if x is None:
            print("Capture returned none")
            return None

        w = x.width
        h = x.height

        if self.masks is None:
            return self.entireImage.poll(x)
        else:
            r[''] = self.entireImage.poll(x)

        for i in self.masks:
            m = self.masks[i]
            # Crop region is specified as a fraction, convert to pixels and points instead of fraction y,x,w,h
            i2 = x.crop((int(m[0] * w),
                         int(m[1] * h),
                        int(m[0] * w) + int(m[2] * w), 
                        int(m[1] * h) + int(m[3] * h))
                        )
            r[i] = self.regions[i].poll(i2)
        return r


class PILCapture():
    def __init__(self, appsink):
        from PIL import Image

        self.img = Image
        self.appsink = appsink

    def pullToFile(self, f, timeout=0.1):
        x = self.pull(timeout, True)
        if not x:
            return None
        x.save(f)
        return 1

    def pull(self, timeout=0.1, forceLatest=False):
        sample = self.appsink.emit('try-pull-sample', timeout * 10**9)

        if forceLatest:
            # Try another pull but only wait 1ms.
            # This is in case there is another queued up frame, such as if we have buffer elements or something
            # before this
            sample2 = self.appsink.emit('try-pull-sample', 1000000)
            c = 10
            while sample2:
                if c < 1:
                    break
                c -= 1
                sample2 = self.appsink.emit('try-pull-sample', 1000000)

            sample = sample2 or sample

        if not sample:
            return None

        buf = sample.get_buffer()
        caps = sample.get_caps()
        h = caps.get_structure(0).get_value('height')
        w = caps.get_structure(0).get_value('width')

        return self.img.frombytes("RGB", (w, h), buf.extract_dup(0, buf.get_size()))

    def pull_raw(self):
        "Pull a tuple consisting of raw RGB bytes, then the height and width with which to decode them."
        sample = self.appsink.emit('try-pull-sample', 0.1 * 10**9)
        if not sample:
            return None

        buf = sample.get_buffer()
        caps = sample.get_caps()
        h = caps.get_structure(0).get_value('height')
        w = caps.get_structure(0).get_value('width')

        return (buf.extract_dup(0, buf.get_size()), w, h)


class PILSource():
    def __init__(self, appsrc, greyscale=False):
        self.appsrc = appsrc
        self.greyscale = greyscale

    def push(self, img):
        img = img.tobytes("raw", "L" if self.greyscale else "rgb")
        img = Gst.Buffer.new_wrapped(img)
        self.appsrc.emit("push-buffer", img)


class AppSource():
    def __init__(self, appsrc):
        self.appsrc = appsrc

    def push(self, b):
        b = Gst.Buffer.new_wrapped(b)
        self.appsrc.emit("push-buffer", b)


class AppSink():
    # Used to pull the raw bytes buffer data.
    def __init__(self, appsink):
        self.appsink = appsink

    def pull(self, timeout=0.1):
        sample = self.appsink.emit('try-pull-sample', timeout * 10**9)
        if not sample:
            return None

        buf = sample.get_buffer()
        caps = sample.get_caps()

        return buf.extract_dup(0, buf.get_size())


def link(a, b):
    unref = False
    try:
        if not a or not b:
            raise ValueError("Cannot link None")
        if isinstance(a, Gst.Pad):
            if not isinstance(b, Gst.Pad):
                b = b.get_static_pad("sink")
                unref = True
                if not b:
                    raise RuntimeError(
                        "B has no pad named sink and A is a pad")
            if not a.link(b) == Gst.PadLinkReturn.OK:
                raise RuntimeError("Could not link: " + str(a) + str(b))

        else:
            x = a.link(b)

            if not x:
                raise RuntimeError("Could not link" + str(a) +
                                   str(b) + " reason " + str(x))
    finally:
        if unref:
            pass  # b.unref()


def stop_allJackUsers():
    # It seems best to stop everything using jack before stopping and starting the daemon.
    with lock:
        c = list(jackChannels.items())
        for i in c:
            # Sync stop, we gotta wait
            try:
                i[1]().syncStop = True
                i[1]().stop()
            except Exception:
                log.exception("Err stopping JACK user")
        del c
        # Defensive programming against a double stop, which might be something that
        # No longer is in a state that can be touched without a segfault
        try:
            for i in jackChannels:
                del jackChannels[i]
        except Exception:
            pass


def elementInfo(e):
    r = Gst.Registry.get()


elementsByShortId = weakref.WeakValueDictionary()


def Element(n, name=None):
    e = Gst.ElementFactory.make(n, None)
    elementsByShortId[id(e)] = e
    if e:
        return e
    else:
        raise ValueError("No such element exists: " + n)


loop = None

autorunMainloop = True

mainContext = None


def init():
    "On demand loading, for startup speed but also for compatibility if Gstreamer isn't there"
    global initialized, Gst, loop, mainContext
    # Quick check outside the lock
    if initialized:
        return
    with initlock:
        if not initialized:
            import gi
            gi.require_version('Gst', '1.0')
            gi.require_version('GstBase', '1.0')
            gi.require_version('Gtk', '3.0')
            from gi.repository import Gst as gst
            from gi.repository import GObject, GstBase, Gtk, GObject, GLib
            Gst = gst
            Gst.init(None)

            #mainContext = GLib.MainContext()

            #glibloop = GLib.MainLoop()

            # loop=threading.Thread(target=glibloop.run,daemon=True)
            # loop.start()
            initialized = True


def doesElementExist(n):
    n = Gst.ElementFactory.make(n)
    if n:
        pass  # n.unref()
    return True


def wrfunc(f, fail_return=None):
    def f2(*a, **k):
        try:
            return f()(*a, **k)
        except Exception:
            print(traceback.format_exc())
            return fail_return
    return f2


def makeWeakrefPoller(selfref, exitSignal):

    def pollerf():
        alreadyStarted = False
        t = 0
        seqNum = -1
        while selfref():
            self = selfref()

            self.threadStarted = True
            if not self.shouldRunThread:
                exitSignal.append(True)

                # We can't allow returns to happen till the pipeline is null.  That could cause a segfault
                # on garbage collection.  So we choose a memory leak instead.
                try:
                    with self.seeklock:
                        self.pipeline.set_state(Gst.State.NULL)
                except Exception:
                    pass
                self._waitForState(Gst.State.NULL, 3600000)
                return

            if self.shouldRunThread:
                if t < time.monotonic() - 3:
                    t = time.monotonic()
                    try:
                        # If we can't get the lock, don't block the message thread
                        if self.lock.acquire(timeout=1):
                            try:
                                self.loopCallback()
                            finally:
                                self.lock.release()

                        state = self.pipeline.get_state(1000000000)[1]
                        if not state == Gst.State.NULL:
                            self.wasEverRunning = True

                        # Set the flag if anything ever drives us into the null state
                        if self.wasEverRunning and state == Gst.State.NULL:
                            self.shouldRunThread = False
                            exitSignal.append(True)
                            return
                    except Exception:
                        # Todo actually handle some errors?
                        exitSignal.append(True)
                        # After pipeline deleted, we clean up
                        if hasattr(self, 'pipeline') and hasattr(self, 'bus'):
                            try:
                                with self.seeklock:
                                    self.pipeline.set_state(Gst.State.NULL)
                            except Exception:
                                pass
                            self._waitForState(Gst.State.NULL, 3600000)

                            raise
                        else:
                            return

            # with self.lock:
            msg = self.bus.timed_pop(500 * 1000 * 1000)
            if msg:
                try:
                    if msg.type == Gst.MessageType.ERROR:
                        self.on_error(self.bus, msg, None)

                    elif msg.type == Gst.MessageType.EOS:
                        if msg.seqnum != seqNum:
                            self.on_eos(self.bus, msg, None)

                    elif msg.type == Gst.MessageType.SEGMENT_DONE:
                        if msg.seqnum != seqNum:
                            self.on_segment_done()

                    self.on_message(self.bus, msg, None)

                    seqNum = msg.seqnum
                except Exception:
                    logging.exception("Err in pipeline:" + self.name)
                finally:
                    pass
            else:
                # Too quiet in here and the seeklock is taken, assume the seek was jammed
                # by a move to the pause state
                if self.seeklock.acquire(timeout=0.25):
                    self.seeklock.release()
                else:
                    self.pipeline.set_state(Gst.State.PLAYING)

            del self

            # time.sleep(1)
    return pollerf


def getCaps(e):
    try:
        return e.caps
    except Exception:
        return "UNKNOWN"
    e.getSinks()[0].getNegotiatedCaps()


def linkClosureMaker(self, src, dest, connectWhenAvailable, eid, deleteAfterUse=False):
    "This has t be outside, it can't leak a ref to self's strong reference into the closure or it may leak memory"
    def linkFunction(element, pad, dummy):
        s = pad.query_caps(None).to_string()
        if isinstance(connectWhenAvailable, str):
            if not connectWhenAvailable in s:
                return

        if eid in self().waitingCallbacks:
            link(element, dest)
        if deleteAfterUse:
            del self().waitingCallbacks[eid]
    return linkFunction


class GStreamerPipeline():
    """Semi-immutable pipeline that presents a nice subclassable GST pipeline You can only add stuff to it.
    """

    def __init__(self, name=None, realtime=None, systemTime=False):
        init()
        self.lock = threading.RLock()

        self.seeklock = self.lock

        self.pilcaptures = []

        # We use this for detecting motion.
        # We have to use this hack because gstreamer's detection is... not great.
        self._pilmotiondetectorcapture = None
        self._pilmotiondetector = None

        self.exiting = False

        self.uuid = time.time()
        name = name or "Pipeline" + str(time.monotonic())
        self.realtime = realtime
        self._stopped = True
        self.syncStop = False
        self.pipeline = Gst.Pipeline()
        self.threadStarted = False
        self.weakrefs = weakref.WeakValueDictionary()

        self.proxyToElement = weakref.WeakValueDictionary()

        # This WeakValueDictionary is mostly for testing purposes
        pipes[id(self)] = self

        # Thread puts something in this so we know we exited
        self.exitSignal = []

        self.weakrefs[str(self.pipeline)] = self.pipeline
        if not self.pipeline:
            raise RuntimeError("Could not create pipeline")
        if not initialized:
            raise RuntimeError("Gstreamer not set up")
        self.bus = self.pipeline.get_bus()
        self._stopped = False

        self.weakrefs[str(self.bus)] = self.bus

        self.hasSignalWatch = 0

        # Run in our own mainContext
        # mainContext.push_thread_default()
        try:
            self.bus.add_signal_watch()
        finally:
            pass  # mainContext.pop_thread_default()

        self.hasSignalWatch = 1
        # 1 is dummy user data, because some have reported segfaults if it is missing
        # Note that we keep strong refs to the functions, so they don't go away when we unregister,
        # Leading to a segfault in libffi because of a race condition
        self._onmessage = wrfunc(weakref.WeakMethod(self.on_message))
        self.pgbcobj = self.bus.connect('message', self._onmessage, 1)

        self._oneos = wrfunc(weakref.WeakMethod(self.on_eos))
        self.pgbcobj2 = self.bus.connect("message::eos", self._oneos, 1)

        self._onerror = wrfunc(weakref.WeakMethod(self.on_error))
        self.pgbcobj3 = self.bus.connect("message::error", self._onerror, 1)

        self.name = name

        self.elements = []
        self.sidechainElements = []
        self.namedElements = {}

        self.elementTypesById = {}

        # Just a place to store refs
        self.waitingCallbacks = {}

        self.running = False
        self.shouldRunThread = True
        self.wasEverRunning = True

        self.knownThreads = {}
        self.startTime = 0

        def dummy(*a, **k):
            pass

        if realtime:
            self._syncmessage = wrfunc(weakref.WeakMethod(
                self.syncMessage), fail_return=Gst.BusSyncReply.PASS)
            self.bus.set_sync_handler(self._syncmessage, 0, dummy)
        self.pollthread = None

        self.lastElementType = None

        # If true, keep the pipeline running at the same rate as system time
        self.systemTime = systemTime
        self.targetRate = 1.0
        self.pipelineRate = 1.0

    def sendEOS(self):
        self.pipeline.send_event(Gst.Event.new_eos())

    def loopCallback(self):
        if self._pilmotiondetector:
            x = self._pilmotiondetector.poll()
            if x is None:
                return
            rpc[0]("onPresenceValue", [x])

    def addPresenceDetector(self, resolution, connectToOutput=None, regions=None):
        if self._pilmotiondetector:
            raise RuntimeError("Already have one of these")

        self._pilmotiondetectorcapture = self.addPILCapture(
            resolution, connectToOutput, method=0)
        self._pilmotiondetector = PresenceDetector(
            self._pilmotiondetectorcapture, regions)

    def seek(self, t=None, rate=None, _raw=False, _offset=0.008, flush=True, segment=False, sync=False, skip=False):
        "Seek the pipeline to a position in seconds, set the playback rate, or both"
        with self.lock:
            if self.exiting:
                return
            if not self.running:
                return

            if rate is None:
                rate = self.targetRate

            if not _raw:
                # Set "effective start time" so that the system clock sync keeps working.
                if not t is None:
                    t = max(t, 0)
                    self.startTime = time.monotonic() - t
                self.targetRate = rate
                self.pipelineRate = rate

            flags = Gst.SeekFlags.NONE

            if flush:
                flags |= Gst.SeekFlags.FLUSH

            if segment:
                flags |= Gst.SeekFlags.SEGMENT

            if skip:
                # Use skip to speed up, but segment mode
                flags |= Gst.SeekFlags.SKIP

            if (not flush) and self.pipeline.get_state(1000_000_000)[1] == Gst.State.PAUSED:
                raise RuntimeError(
                    "Cannot do non-flushing seek in paused state as this may deadlock")

            # Big issue here.  Sometimes, i think when you stop playback during seek,
            # It blocks forever.  We have to do this in a background thread so we don't block everything
            # Else.   We just have to trust gstreamer to be thread safe, and to eventually unblock when the pipeline is null.
            e = threading.Event()

            def f():
                # Seek is especiallly problematic, we must isolate it from state changes
                with self.seeklock:
                    if (not flush) and self.pipeline.get_state(1000_000_000)[1] == Gst.State.PAUSED:
                        raise RuntimeError(
                            "Cannot do non-flushing seek in paused as this may deadlock.  State has changed while request inflight, request cancelled.")

                    self.pipeline.seek(rate, Gst.Format.TIME,
                                       flags, Gst.SeekType.NONE if t is None else Gst.SeekType.SET, max(
                                           ((t or 0) + _offset) * 10**9, 0),
                                       Gst.SeekType.NONE, 0)
                    e.set()
            if sync:
                f()
            else:
                doNow(f)
            # If it got blocked because a race condition that made it paused, try to unblock
            if not e.wait(0.5):
                if not flush:
                    self.pipeline.set_state(Gst.State.PLAYING)

    def getPosition(self):
        "Returns stream position in seconds"
        with self.lock:
            ret, current = self.pipeline.query_position(Gst.Format.TIME)
            if not ret:
                raise RuntimeError(ret)
            if current < 0:
                raise RuntimeError("Nonsense position: " + str(current))
            if current == Gst.CLOCK_TIME_NONE:
                raise RuntimeError("gst.CLOCK_TIME_NONE")
            return current / 10**9

    @staticmethod
    def setCurrentThreadPriority(x, y):
        raise RuntimeError("Must override this to use realtime priority")

    def syncMessage(self, *arguments):
        "Synchronous message, so we can enable realtime priority on individual threads."
        # Stop the poorly performing sync messages after a while.
        # Wait till we have at least one thread though.

        try:
            if self.knownThreads and time.monotonic() - self.startTime > 3:
                # This can't use the lock, we don't know what thread it might be called in.
                def noSyncHandler():
                    with self.lock:
                        if hasattr(self, 'bus'):
                            self.bus.set_sync_handler(None, 0, None)
                doNow(noSyncHandler)
            if not threading.currentThread().ident in self.knownThreads:
                self.knownThreads[threading.currentThread().ident] = True
                if self.realtime:
                    try:
                        self.setCurrentThreadPriority(1, self.realtime)
                    except Exception:
                        log.exception("Error setting realtime priority")
            return Gst.BusSyncReply.PASS
        except Exception:
            return Gst.BusSyncReply.PASS
            print(traceback.format_exc())

    def makeElement(self, n, name=None):
        with self.lock:
            e = Element(n, name)
            self.elementTypesById[id(e)] = n
            self.pipeline.add(e)
            return e

    # Low level wrapper just for filtering out args we don't care about
    def on_eos(self, *a, **k):
        with self.lock:
            self.onEOS()

    def onEOS(self):
        self.onStreamFinished()
        rpc[0]("onStreamFinished", [])

    def onStreamFinished(self):
        pass

    def __del__(self):
        self.running = False
        t = time.monotonic()

        # Give it some time, in case it really was started
        if not self.threadStarted:
            time.sleep(0.01)
            time.sleep(0.01)
            time.sleep(0.01)
            time.sleep(0.01)

        if self.threadStarted:
            while not self.exitSignal:
                time.sleep(0.1)
                if time.monotonic() - t > 10:
                    raise RuntimeError("Timeout")

        if not self._stopped:
            self.stop()

    def on_message(self, bus, message, userdata):
        s = message.get_structure()
        if s:
            self.onMessage(message.src, s.get_name(), s)

        return True

    # def appsinkhandler(self,appsink, user_data):
    #     sample = appsink.emit("pull-sample")
    #     gst_buffer = sample.get_buffer()
    #     (ret, buffer_map) = gst_buffer.map(Gst.MapFlags.READ)
    #     rpc[0]("_onAppsinkData", [str(user_data), base64.b64encode(buffer_map.data).decode()])
    #     return Gst.FlowReturn.OK

    def onMessage(self, src, name, s):
        if s.get_name() == 'level':
            rms = sum([i for i in s['rms']]) / len(s['rms'])
            decay = sum([i for i in s['decay']]) / len(s['decay'])
            rpc[0]("onLevelMessage", [str(src), rms, decay])

        elif s.get_name() == 'motion':
            if s.has_field("motion_begin"):
                rpc[0]("onMotionBegin", [])
            if s.has_field("motion_finished"):
                rpc[0]("onMotionEnd", [])

        elif s.get_name() == 'GstVideoAnalyse':
            rpc[0]("onVideoAnalyze", [{'luma-average': s.get_double('luma-average')[
                   1], 'luma-variance':s.get_double('luma-variance')[1]}])

        elif s.get_name() == 'barcode':
            rpc[0]("onBarcode", [s.get_string("type"),
                   s.get_string("symbol"), s.get_int("quality")[1]])

        elif s.get_name() == 'GstMultiFileSink':
            rpc[0]("onMultiFileSink", [''])

        elif s.get_name() == 'pocketsphynx':
            if s.get_value('hypothesis'):
                rpc[0]("onSTTMessage", [str(src), s.get_value('hypothesis')])
            if s.get_value('final'):
                rpc[0]("onSTTMessageFinal", [str(src), s.get_value('final')])

    def on_error(self, bus, msg, userdata):
        with self.lock:
            logging.debug('Error {}: {}, {}'.format(
                msg.src.name, *msg.parse_error()))

    def on_segment_done(self, *a):
        with self.lock:
            self.onSegmentDone()
            return True

    def onSegmentDone(self):
        # Called when a segment finishes playback, but NOT whem a segment ends because you did a seek to a new segment,
        # As that is usually not what you want when doing seamless loops.
        rpc[0]("onSegmentDone", [])
        pass

    def _waitForState(self, s, timeout=10):
        t = time.monotonic()
        i = 0.01
        while not self.pipeline.get_state(1000_000_000)[1] == s:
            if time.monotonic() - t > timeout:
                raise RuntimeError("Timeout, pipeline still in: ",
                                   self.pipeline.get_state(1000_000_000)[1])
            time.sleep(min(i, 0.1))
            i *= 2

    def exitSegmentMode(self):
        with self.lock:
            self.seek()

    def restart(self, segment=False):

        # Todo why do we even need the global lock here?
        def f():
            with self.lock:
                if not self.pipeline.get_state(1000_000_000)[1] == Gst.State.NULL:
                    with self.seeklock:
                        self.pipeline.set_state(Gst.State.NULL)
                    self._waitForState(Gst.State.NULL)
                self.start(segment=segment)
        doNow(f)

    def start(self, effectiveStartTime=None, timeout=10, segment=False):
        "effectiveStartTime is used to keep multiple players synced when used with systemTime"
        with self.lock:
            if self.exiting:
                return

            x = effectiveStartTime or time.time()
            timeAgo = time.time() - x
            # Convert to monotonic time that the nternal APIs use
            self.startTime = time.monotonic() - timeAgo

            # Go straight to playing, no need to locally do paused if we aren't using that feature
            if self.systemTime or effectiveStartTime or segment:
                if not self.pipeline.get_state(1000_000_000)[1] == (Gst.State.PAUSED, Gst.State.PLAYING):
                    with self.seeklock:
                        self.pipeline.set_state(Gst.State.PAUSED)
                    self._waitForState(Gst.State.PAUSED)

            # Seek to where we should be, if we had actually
            # Started when we should have. We want to get everything set up in the pause state
            # First so we have the right "effective" start time.

            # We accept cutting off a few 100 milliseconds if it means
            # staying synced.
            if self.systemTime:
                self.seek(time.monotonic() - self.startTime)

            elif segment:
                self.seek(0, segment=True, flush=True)

            with self.seeklock:
                self.pipeline.set_state(Gst.State.PLAYING)

            self._waitForState(Gst.State.PLAYING, timeout)

            self.running = True

            for i in range(0, 500):
                try:
                    # Test that we can actually read the clock
                    self.getPosition()
                    break
                except Exception:
                    if i > 150:
                        raise RuntimeError("Clock still not valid")
                    time.sleep(0.1)

            # Don't start the thread until we have a valid clock
            self.maybeStartPoller()

    def play(self, segment=False):
        with self.lock:
            if self.exiting:
                return
            if not self.running:
                raise RuntimeError(
                    "Pipeline is not paused, or running, call start()")
            if not self.pipeline.get_state(1000_000_000)[1] in (Gst.State.PLAYING, Gst.State.PAUSED, Gst.State.READY):
                raise RuntimeError(
                    "Pipeline is not paused, or running, call start()")

            # Hopefully this willl raise an error if the clock is invalid for some reason,
            # Instead of potentially causing a segfault, if that was the problem
            self.getPosition()
            with self.seeklock:
                self.pipeline.set_state(Gst.State.PLAYING)
            self._waitForState(Gst.State.PLAYING)

            if segment:
                self.seek(segment=True, flush=False)

    def pause(self):
        "Not that we can start directly into paused without playing first, to preload stuff"
        with self.lock:
            if self.exiting:
                return
            with self.seeklock:
                self.pipeline.set_state(Gst.State.PAUSED)
            self._waitForState(Gst.State.PAUSED)
            self.getPosition()
            self.running = True
            self.maybeStartPoller()

    def maybeStartPoller(self, join=False):
        if not self.pollthread:
            self.pollthread = threading.Thread(target=makeWeakrefPoller(weakref.ref(
                self), self.exitSignal), daemon=True, name="nostartstoplog.GSTPoller")
            self.pollthread.daemon = True
            self.pollthread.start()
            if join:
                self.pollthread.join()

    def isStoppedOrExiting(self):
        if self._stopped:
            return True
        if self.exiting:
            return True

    def stop(self):
        try:
            # Actually stop as soon as we can

            # Here again we must trust GST thread safety, or else we a blocked up pipeline
            # Could hold the lock and we could never stop it.
            self.shouldRunThread = False

            if not self.exiting:

                if hasattr(self, 'pipeline'):
                    with self.seeklock:
                        # This was causing segfaults for some reasons
                        if not (self.pipeline.get_state(1000_000_000)[1] == Gst.State.NULL):
                            # The set state line seemed to be a problem, better set the exiting
                            # flag early so we don't do it more than needed and hang?
                            self.exiting = True
                            self.pipeline.set_state(Gst.State.NULL)

            with self.lock:
                if self._stopped:
                    return

                self.exiting = True
                if hasattr(self, 'bus'):
                    self.bus.set_sync_handler(None, 0, None)
                    if self.hasSignalWatch:
                        self.bus.remove_signal_watch()
                        self.hasSignalWatch = False

            # Now we're going to do the cleanup stuff
            # In the background, because it involves a lot of waiting.
            # This might fail, if it never even started, but we just kinda ignore that.p
                self.running = False
                self.shouldRunThread = False
                t = time.monotonic()
                time.sleep(0.01)

                if not self.threadStarted:
                    time.sleep(0.01)
                    time.sleep(0.01)
                    time.sleep(0.01)
                    time.sleep(0.01)

                # On account of the race condition, it is possible that the thread actually never did start yet
                # So we have to ignore the exit flag stuff.

                # It shouldn't really be critical, most likely the thread can stop on it's own time anyway,
                # because it doesn't do anything without getting the lock.
                if self.threadStarted:
                    while not self.exitSignal:
                        time.sleep(0.1)
                        if time.monotonic() - t > 10:
                            break

                with self.lock:
                    if self._stopped:
                        return
                    try:
                        self._waitForState(Gst.State.NULL, 1)
                    except Exception:
                        with self.seeklock:
                            self.pipeline.set_state(Gst.State.NULL)
                        self._waitForState(Gst.State.NULL, 1)

                    # This stuff happens in the NULL state, because we prefer not to mess with stuff while it's
                    # Running
                    try:
                        self.bus.disconnect(self.pgbcobj)
                        del self.pgbcobj
                        self.bus.disconnect(self.pgbcobj2)
                        del self.pgbcobj2
                        self.bus.disconnect(self.pgbcobj3)
                        del self.pgbcobj3
                    except Exception:
                        print(traceback.format_exc())

                    def f():
                        with lock:
                            try:
                                del jackChannels[self.uuid]
                            except KeyError:
                                pass

                    doNow(f)

                    self._stopped = True
        finally:
           stopflag[0]=1

    def addPILCapture(self, resolution=None, connectToOutput=None, buffer=1, method=1):
        "Return a video capture object.  Now that we use BG threads this is just used to save snapshots to file"
        if resolution:
            scale = self.addElement("videoscale", method=method)
            caps = self.addElement("capsfilter", caps="video/x-raw,width=" +
                                   str(resolution[0]) + ",height=" + str(resolution[0]))
        conv = self.addElement("videoconvert", connectToOutput=connectToOutput)
        caps = self.addElement("capsfilter", caps="video/x-raw,format=RGB")

        appsink = self.addElement(
            "appsink", drop=True, sync=False, max_buffers=buffer)

        p = PILCapture(appsink)
        elementsByShortId[id(p)] = p
        self.pilcaptures.append(p)
        return p

    def addRemotePILCapture(self, *a, **k):
        return id(self.addPILCapture(*a, **k))

    def addPILSource(self, resolution, buffer=1, greyscale=False):
        "Return a video source object that we can use to put PIL buffers into the stream"

        appsrc = self.addElement("appsrc", caps="video/x-raw,width=" + str(resolution[0]) + ",height=" + str(
            resolution[0]) + ", format=" + "GREy8" if greyscale else "RGB", connectToOutput=False)
        conv = self.addElement("videoconvert")
        scale = self.addElement("videoscale")

        # Start with a blck image to make things prerooll
        if (greyscale):
            appsrc.emit(
                "push-buffer", Gst.Buffer.new_wrapped(bytes(resolution[0] * resolution[1])))
        else:
            appsrc.emit(
                "push-buffer", Gst.Buffer.new_wrapped(bytes(resolution[0] * resolution[1] * 3)))

        return PILSource(appsrc, greyscale)

    def addAppSink(self, connectToOutput=None, buffer=1):
        "Return a video capture object"

        appsink = self.addElement(
            "appsink", drop=True, sync=False, max_buffers=buffer)

        return AppSink(appsink)

    def addAppSrc(self, connectToOutput=None, buffer=1, caps=''):
        "Return a video capture object"

        appsrc = self.addElement("appsrc", caps=caps, connectToOutput=False)
        return AppSource(appsrc)

    def pullBuffer(self, element, timeout=0.1):
        if isinstance(element, int):
            element = elementsByShortId[element]

        sample = self.appsink.emit('try-pull-sample', timeout * 10**9)
        if not sample:
            return None

        buf = sample.get_buffer()
        caps = sample.get_caps()

        return base64.b64encode(buf.extract_dup(0, buf.get_size()))

    def pullToFile(self, element, fn):
        if isinstance(element, int):
            element = elementsByShortId[element]

        return element.pullToFile(fn)

    def addElement(self, t, name=None, connectWhenAvailable=False, connectToOutput=None, sidechain=False, **kwargs):

        with self.lock:
            if not isinstance(t, str):
                raise ValueError("Element type must be string")

            e = Gst.ElementFactory.make(t, name)

            # if t=='appsink':
            #     e.connect("new-sample", self.appsinkhandler, name)

            if e == None:
                raise ValueError("Nonexistant element type: " + t)
            self.weakrefs[str(e)] = e
            self.elementTypesById[id(e)] = t
            elementsByShortId[id(e)] = e

            for i in kwargs:
                v = kwargs[i]
                self.setProperty(e, i, v)

            self.pipeline.add(e)
            op = []
            # May need to use an ID if its a remore command
            if connectToOutput:
                if not isinstance(connectToOutput, (list, tuple)):
                    cto = [connectToOutput]
                else:
                    cto = connectToOutput

                for connectToOutput in cto:

                    if not connectToOutput is False:
                        if isinstance(connectToOutput, int):
                            connectToOutput = elementsByShortId[connectToOutput]

                        if not id(connectToOutput) in self.elementTypesById:
                            raise ValueError("Cannot connect to the output of: " +
                                             str(connectToOutput) + ", no such element in pipeline.")
                        op.append(connectToOutput)
            else:
                # One auto connect
                if connectToOutput is None:
                    op = [None]

            for connectToOutput in op:
                # Element doesn't have an input pad, we want this to be usable as a fake source to go after a real source if someone
                # wants to use it as a effect
                if t == "audiotestsrc":
                    connectToOutput = False

                # This could be the first element
                if self.elements and (not (connectToOutput is False)):
                    connectToOutput = connectToOutput or self.elements[-1]

                    # Fakesinks have no output, we automatically don't connect those
                    if self.elementTypesById[id(connectToOutput)] == 'fakesink':
                        connectToOutput = False

                    # Decodebin doesn't have a pad yet for some awful reason
                    elif (self.elementTypesById[id(connectToOutput)] == 'decodebin') or connectWhenAvailable:
                        eid = time.time()
                        f = linkClosureMaker(weakref.ref(
                            self), connectToOutput, e, connectWhenAvailable, eid)

                        self.waitingCallbacks[eid] = f
                        # Dummy 1 param because some have claimed to get segfaults without
                        connectToOutput.connect("pad-added", f, 1)
                    else:
                        link(connectToOutput, e)

            # Sidechain means don't set this element as the
            # automatic thing that the next entry links to
            if not sidechain:
                self.elements.append(e)
            else:
                self.sidechainElements.append(e)

            self.namedElements[name] = e

            self.lastElementType = t
            p = weakref.proxy(e)

            self.proxyToElement[id(p)] = e
            # List it under the proxy as well
            self.elementTypesById[id(p)] = t
            elementsByShortId[id(p)] = e

        # Mark as a JACK user so we can stop if needed for JACK
        # Stuff
        if t.startswith("jackaudio"):
            with lock:
                jackChannels[self.uuid] = weakref.ref(self)
        return p

    def addElementRemote(self, *a, **k):
        return id(self.addElement(*a, **k))

    def addJackMixerSendElements(self, target, idee, volume=-60):
        with self.lock:
            if not isinstance(target, str):
                raise ValueError("Target must be string")

            e = self.makeElement("tee")
            q = self.makeElement("queue")
            q2 = self.makeElement("queue")
            q2.max_size_buffers = 1
            q.max_size_buffers = 1
            q.leaky = 2
            q2.leaky = 2
            l = self.makeElement('volume')
            l.set_property('volume', 10**(volume / 20))

            e2 = self.makeElement(
                "jackaudiosink", "_send" + str(len(self.elements)))
            e2.set_property("buffer-time", 10)
            e2.set_property("port-pattern", "fdgjkndgmkndfmfgkjkf")
            e2.set_property("sync", False)
            e2.set_property("slave-method", 0)
            e2.set_property('provide-clock', False)
            e2.set_property('connect', False)

            e2.latency_time = 10

            tee_src_pad_template = e.get_pad_template("src_%u")
            tee_audio_pad = e.request_pad(tee_src_pad_template, None, None)
            tee_audio_pad2 = e.request_pad(tee_src_pad_template, None, None)

            if self.elements:
                link(self.elements[-1], e)
            link(tee_audio_pad, q)
            link(tee_audio_pad2, q2)
            self.elements.append(q2)

            link(q, l)
            link(l, e2)

            return id(l), id(e2)

    def setProperty(self, element, prop, value):
        with self.lock:

            if isinstance(element, int):
                element = elementsByShortId[element]

            if prop == "location" and self.elementTypesById[id(element)] == 'filesrc':
                if not os.path.isfile(value):
                    raise ValueError("No such file: " + value)

            if prop == 'caps':
                value = Gst.Caps(value)
                self.weakrefs[str(value)] = value

            if prop.startswith("_"):
                prop = prop[1:]
                
            prop = prop.replace("_", "-")

            prop = prop.split(":")
            if len(prop) > 1:
                childIndex = int(prop[0])
                target = element.get_child_by_index(childIndex)
                target.set_property(prop[1], value)
                self.weakrefs[str(target) + "fromgetter"] = target
            else:
                element.set_property(prop[0], value)

    def isActive(self):
        with self.lock:
            if self.pipeline.get_state(1000_000_000)[1] == Gst.State.PAUSED:
                return True
            if self.pipeline.get_state(1000_000_000)[1] == Gst.State.PLAYING:
                return True
            

gstp = None

ppid = os.getppid()


def main():
    global gstp

    gstp = GStreamerPipeline()
    rpc[0] = jsonrpyc.RPC(target=gstp)


    # def print(*a):
    #     rpc[0]("print", [str(a)])

    while not rpc[0].threadStopped:
        time.sleep(1)

        if (not check_pid(ppid)) or stopflag[0]:
            sys.exit()

        if not os.getppid() == ppid:
            return

if __name__ == '__main__':
    main()