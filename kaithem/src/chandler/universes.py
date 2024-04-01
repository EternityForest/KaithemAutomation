
from __future__ import annotations
import colorzero
import numpy
import time
import threading
import weakref
import socket
import logging
import traceback
import gc
import copy
import struct
import json
from typing import Optional, List, Dict, Any
from . import core
from .core import disallow_special

from ..kaithemobj import kaithem
from kaithem.src import alerts

logger = logging.getLogger("system.chandler")

# Locals for performance... Is this still a thing??
float = float
abs = abs
int = int
max = max
min = min

universesLock = core.lock
universes: Dict[str, weakref.ReferenceType[Universe]] = {}

# MUTABLE
_universes: Dict[str, weakref.ReferenceType[Universe]] = {}


fixtures: Dict[str, weakref.ref[Fixture]] = {}


class Fixture:
    def __init__(self, name: str, data: Optional[List[List[Any]] | Dict[str, Any]] = None):
        """Represents a contiguous range of channels each with a defined role in one universe.

        data is the definition of the type of fixture. It can be a list of channels, or
        a dict having a 'channels' property.

        Each channel must be described by a [name, type, [arguments]] list, where type is one of:

        red
        green
        blue
        value
        dim
        custom
        fine
        fog
        hue

        The name must be unique per-fixture.
        If a channel has the type "fine" it will be interpreted as the fine value of
        the immediately preceding coarse channel, and should automatically 
        get its value from the fractional part.
        If the coarse channel is not the immediate preceding channel,
        use the first argument to specify the number of the coarse channel,
        with 0 being the fixture's first channel.
        """
        self.channels: List[List[Any]]

        if data:
            # Normalize and raise errors on nonsense
            channels: List[List[Any]] | Dict[str, Any] = json.loads(json.dumps(data))

            if not isinstance(channels, list):
                channels = channels["channels"]

            assert isinstance(channels, list)
            self.channels = channels

        else:
            channels = []
            self.channels = channels

        self.universe: Optional[str] = None
        self.startAddress: Optional[int] = 0
        self.assignment = None
        disallow_special(name, ".")

        self.nameToOffset: Dict[str, int] = {}

        # Used for looking up channel by name
        for i in range(len(channels)):
            self.nameToOffset[channels[i][0]] = i

        with core.lock:
            if name in fixtures:
                raise ValueError("Name in Use")
            else:
                fixtures[name] = weakref.ref(self)
                self.name = name

    def getChannelByName(self, name: str):
        if self.startAddress:
            return self

    def __del__(self):
        with core.lock:
            try:
                del fixtures[self.name]
            except KeyError:
                pass

        ID = id(self)

        def f():
            with core.lock:
                try:
                    if id(fixtures[self.name]()) == id(ID):
                        self.assign(None, None)
                        self.rm()
                except KeyError:
                    pass
                except Exception:
                    print(traceback.format_exc())

        kaithem.misc.do(f)

    def rm(self):
        try:
            del fixtures[self.name]
        except Exception:
            print(traceback.format_exc())

    def assign(self, universe: Optional[str], channel: Optional[int]):
        with core.lock:
            # First just clear the old assignment, if any
            if self.universe and self.startAddress:
                oldUniverseObj = getUniverse(self.universe)

                if oldUniverseObj:
                    # Delete current assignments
                    for i in range(
                        self.startAddress, self.startAddress +
                            len(self.channels)
                    ):
                        if i in oldUniverseObj.channels:
                            if (
                                oldUniverseObj.channels[i]()
                                and oldUniverseObj.channels[i]() is self
                            ):
                                del oldUniverseObj.channels[i]
                                # We just unassigned it, so it's not a hue channel anymore
                                oldUniverseObj.hueBlendMask[i] = 0
                            else:
                                print(
                                    "Unexpected channel data corruption",
                                    universe,
                                    i,
                                    oldUniverseObj.channels[i](),
                                )

            self.assignment = universe, channel

            self.universe = universe
            self.startAddress = channel

            universeObj = getUniverse(universe)

            if not universeObj:
                return

            core.fixtureschanged = {}

            universeObj.channelsChanged()

            if not channel:
                return
            # 2 separate loops, first is just to check, so that we don't have half-completed stuff
            for i in range(channel, channel + len(self.channels)):
                if i in universeObj.channels:
                    if universeObj.channels[i]:
                        fixture = universeObj.channels[i]()
                        if fixture:
                            if not self.name == fixture.name:
                                raise ValueError(
                                    "channel "
                                    + str(i)
                                    + " of "
                                    + self.name
                                    + " would overlap with "
                                    + fixture.name
                                )

            cPointer = 0
            for i in range(channel, channel + len(self.channels)):
                universeObj.channels[i] = weakref.ref(self)
                if self.channels[cPointer][1] in ("hue", "sat", "custom"):
                    # Mark it as a hue channel that blends slightly differently
                    universeObj.hueBlendMask[i] = 1
                    cPointer += 1


class Universe():
    "Represents a lighting universe, similar to a DMX universe, but is not limited to DMX. "

    def __init__(self, name: str, count: int = 512, number: int = 0):
        global universes
        for i in ":/[]()*\\`~!@#$%^&*=+|{}'\";<>,":
            if i in name:
                raise ValueError(
                    "Name cannot contain special characters except _")
        self.name = name
        self.closed = False

        self.hidden = True

        # If local fading is disabled, the rendering tries to compress everything down to a set of fade commands.
        # This is the time at which the current fade is supposed to end.
        self.fadeEndTime = 0

        # If False, lighting values don't fade in, they just jump straight to the target,
        # For things like smart bulbs where we want to use the remote fade instead.
        self.localFading = True

        # Used by blend modes to request that the
        # remote device do onboard interpolation
        # The longest time requested by any layer is used
        # The final interpolation time is the greater of
        # This and the time determined by fadeEndTime
        self.interpolationTime = 0

        # Let subclasses set these
        if not hasattr(self, "status"):
            self.status = "normal"
        if not hasattr(self, "ok"):
            self.ok = True

        # name:weakref(fixture) for every ficture that is mapped to this universe
        self.fixtures = {}

        # Represents the telemetry data back from the physical device of this universe.
        self.telemetry = {}

        # Dict of all board ids that have already pushed a status update
        self.statusChanged = {}
        self.channels: Dict[int, weakref.ref[Fixture]] = {}

        # Maps names to numbers, mostly for tagpoint universes.
        if not hasattr(self, "channelNames"):
            self.channelNames = {}

        self.groups = {}
        self.values = numpy.array([0.0] * count, dtype="f4")
        self.alphas = numpy.array([0.0] * count, dtype="f4")

        # These channels should blend like Hue, which is normal blending but
        # There's no "background" of zeros. If there's nothing "behind" it, we consider it
        # 100% opaque
        # Type is bool
        self.hueBlendMask = numpy.array([0.0] * count, dtype="?")

        self.count = count
        # Maps fine channel numbers to coarse channel numbers
        self.fine_channels: Dict[int, int] = {}

        # Map fixed channel numbers to values.
        # We implemet that here so they are fixed no matter what the scenes and blend modes say
        self.fixed_channels: Dict[int, float] = {}

        # Used for the caching. It's the layer we want to save as the background state before we apply.
        # Calculated as either the last scene rendered in the stack or the first scene that requests a rerender that affects the universe
        self.save_before_layer = (0, 0)
        # Reset in pre_render, indicates if we've not rendered a layer that we think is going to change soon
        # so far in this frame
        self.all_static = True

        self.error_alert = alerts.Alert(f"{self.name}.errorState",
                                        priority="error", auto_ack=True)
        with core.lock:
            with universesLock:
                if name in _universes and _universes[name]():
                    gc.collect()
                    time.sleep(0.1)
                    gc.collect()
                    # We retry, because the universes are often temporarily cached as strong refs
                    if name in _universes and _universes[name]():
                        try:
                            u = _universes[name]()
                            if u:
                                u.close()
                        except Exception:
                            raise ValueError("Name " + name + " is taken")
                _universes[name] = weakref.ref(self)
                universes = {i: _universes[i]
                             for i in _universes if _universes[i]()}

        # flag to apply all scenes, even ones not marked as neding rerender
        self.full_rerender = False

        # The priority, started of the top layer layer that's been applied to this scene.
        self.top_layer = (0, 0)

        # This is the priority, started of the "saved" layer that's been cached so we don't
        # Have to rerender it or anything below it.
        self.prerendered_layer = (0, 0)

        # A copy of the state of the universe just after prerendered_layer was rendered, so we can go back
        # and start from there without rerendering lower layers.

        # The format is values,alphas
        self.prerendered_data = ([0.0] * count, [0.0] * count)

        # Maybe there might be an iteration error. But it's just a GUI convienence that
        # A simple refresh solves, so ignore it.
        try:
            for i in core.boards:
                x = i()
                if x:
                    x.pushUniverses()
        except Exception as e:
            print(e)

        kaithem.message.post("/chandler/command/refreshFixtures", self.name)
        self.refresh_scenes()

    def close(self):
        global universes
        with universesLock:
            # Don't delete the object that replaced this
            if self.name in _universes and (_universes[self.name]() is self):
                del _universes[self.name]

            universes = {i: _universes[i]
                         for i in _universes if _universes[i]()}

            def alreadyClosed(*a, **k):
                raise RuntimeError(
                    "This universe has been stopped, possibly because it was replaced wih a newer one")

            self.onFrame = alreadyClosed
            self.setStatus = alreadyClosed
            self.refresh_scenes = alreadyClosed
            self.reset_to_cache = alreadyClosed
            self.reset = alreadyClosed
            self.preFrame = alreadyClosed
            self.save_prerendered = alreadyClosed

        kaithem.message.post("/chandler/command/refreshScenes", None)
        self.closed = True

    def setStatus(self, s: str, ok: bool):
        "Set the status shown in the gui. ok is a bool value that indicates if the object is able to transmit data to the fixtures"
        if ok:
            self.error_alert.release()
        else:
            self.error_alert.trip(message=str(s))
        
        # avoid pushing unneded statuses
        if (self.status == s) and (self.ok == ok):
            return
        self.status = s
        self.ok = ok
        self.statusChanged = {}



    def refresh_scenes(self):
        """Stop and restart all active scenes, because some caches might need to be updated
            when a new universes is added
        """
        kaithem.message.post("/chandler/command/refreshScenes", None)

    def __del__(self):
        if not self.closed:
            # Do as little as possible in the undefined __del__ thread
            kaithem.message.post("/chandler/command/refreshScenes", None)

    def channelsChanged(self):
        "Call this when fixtures are added, moved, or modified."
        with core.lock:
            self.fine_channels = {}
            self.fixed_channels = {}

            for i in self.channels:
                fixture = self.channels[i]()
                if not fixture:
                    continue
                if not fixture.startAddress:
                    continue
                data = fixture.channels[i - fixture.startAddress]
                if (data[1] == "fine") and (i > 1):
                    if len(data) == 2:
                        self.fine_channels[i] = i - 1
                    else:
                        self.fine_channels[i] = fixture.startAddress + data[2]

                if (data[1] == "fixed"):
                    if len(data) == 2:
                        self.fixed_channels[i] = 0
                    else:
                        self.fixed_channels[i] = data[2]

    def reset_to_cache(self):
        "Remove all changes since the prerendered layer."
        values, alphas = self.prerendered_data
        self.values = copy.deepcopy(values)
        self.alphas = copy.deepcopy(alphas)

        self.top_layer = self.prerendered_layer

    def save_prerendered(self, p, s):
        "Save this layer as the cached layer. Called in the render functions"
        self.prerendered_layer = (p, s)
        self.prerendered_data = (copy.deepcopy(
            self.values), copy.deepcopy(self.alphas))

    def reset(self):
        "Reset all values to 0 including the prerendered data"
        self.prerendered_layer = (0, 0)
        self.values = numpy.array([0.0] * self.count, dtype="f4")
        self.alphas = numpy.array([0.0] * self.count, dtype="f4")

        self.top_layer = (0, 0)

    def preFrame(self):
        "Frame preprocessor, uses fixture-specific info, generally only called under lock"
        # Assign fine channels their value based on the coarse channel
        for i in self.fine_channels:
            self.values[i] = (self.values[self.fine_channels[i]] % 1) * 255

        for i in self.fixed_channels:
            self.values[i] = self.fixed_channels[i]

    def onFrame(self):
        pass


def message(data):
    "An enttec DMX message from a set of values"
    data = numpy.maximum(numpy.minimum(data, 255), 0)
    data = data.astype(numpy.uint8)
    data = data.tobytes()[1:513]
    return (b'\x7e\x06' + struct.pack('<H', len(data)) + data + b'\xe7')


def rawmessage(data):
    "An enttec open DMX message from a set of values"
    data = numpy.maximum(numpy.minimum(data, 255), 0)
    data = data.astype(numpy.uint8)
    data = data.tobytes()[1:513]
    # Remove the 0 position as DMX starts at 1
    return (b'\0' + data)


class EnttecUniverse(Universe):
    # Thanks to https://github.com/c0z3n/pySimpleDMX
    # I didn't actually use the code, but it was a very useful resouurce
    # For protocol documentation.
    def __init__(self, name:str, channels:int=128, portname:str="", framerate: float = 44.0, number:int=0):
        self.ok = False
        self.number = number
        self.status = "Disconnect"
        self.statusChanged = {}
        # Sender needs the values to be there for setup
        self.values = numpy.array([0.0] * channels, dtype="f4")
        self.sender = makeSender(
            DMXSender, weakref.ref(self), portname, framerate)

        Universe.__init__(self, name, channels)
        self.sender.connect()

        self.hidden = False

    def onFrame(self):
        data = message(self.values)
        self.sender.onFrame(data)

    def __del__(self):
        # Stop the thread when this gets deleted
        self.sender.onFrame(None)

    def close(self):
        try:
            self.sender.onFrame(None)
        except Exception:
            pass
        return super().close()



class DMXSender():
    """This object is used by the universe object to send data to the enttec adapter.
        It runs in it's own thread because the frame rate might have nothing to do with
        the rate at which the data actually gets rendered.
    """

    def __init__(self, universe, port, framerate: float):
        self.frame = threading.Event()
        self.universe = universe
        self.data = message(universe().values)
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.name = "DMXSenderThread_" + self.thread.name
        self.portname = port
        self.framerate = float(framerate)
        self.lock = threading.Lock()
        self.port = None
        self.started = None
        

    def setStatus(self, s, ok):
        try:
            self.universe().setStatus(s, ok)
        except Exception:
            pass

    def connect(self):
        if not self.started:
            self.started = True
            self.thread.start()
        # Different status message first time
        try:
            self.reconnect()
        except Exception as e:
            self.setStatus('Could not connect, ' + str(e)[:100] + '...', False)

    def reconnect(self, portlist=None):
        "Try to reconnect to the adapter"
        try:
            import serial
            import serial.tools
            if not self.portname:
                import serial.tools.list_ports

                p = portlist or serial.tools.list_ports.comports()
                if p:
                    if len(p) > 1:
                        self.setStatus(
                            'More than one device found, refusing to guess. Please specify a device.', False)
                        return
                    else:
                        p = p[0].device
                else:
                    self.port = None
                    self.setStatus('No device found', False)
                    return
            else:
                p = self.portname
            time.sleep(0.1)
            try:
                self.port.close()
            except Exception:
                pass
            self.port = serial.Serial(p, 57600, timeout=1.0, write_timeout=1.0)

            # This is a flush to try to re-sync recievers that don't have any kind of time out detection
            # We do this by sending a frame where each value is the packet end code,
            # Hoping that it lines up with the end of whatever unfinished data we don't know about.
            self.setStatus('Found port, writing sync data', True)

            for i in range(0, 8):
                self.port.write(message(numpy.array([231] * 120)))
                time.sleep(0.05)
            self.port.write(
                message(numpy.zeros(max(128, len(self.universe().values)))))
            time.sleep(0.1)
            self.port.read(self.port.inWaiting())
            time.sleep(0.05)
            self.port.write(self.data)
            self.setStatus('connected to ' + p, True)
        except Exception as e:
            try:
                self.port = None
                self.setStatus('dis_connected, ' + str(e)[:100] + '...', False)
            except Exception:
                pass

    def run(self):
        while 1:
            try:
                s = time.time()
                self.port.read(self.port.inWaiting())
                x = self.frame.wait(1)
                if not x:
                    continue
                with self.lock:
                    if self.data is None:
                        try:
                            self.port.close()
                        except Exception:
                            pass
                        return
                    self.port.write(self.data)
                    self.frame.clear()
                time.sleep(
                    max(((1.0 / self.framerate) - (time.time() - s)), 0))
            except Exception as e:
                try:
                    self.port.close()
                except Exception:
                    pass
                try:
                    if self.data is None:
                        return
                    if self.port:
                        self.setStatus('dis_connected, ' + str(e)
                                       [:100] + '...', False)
                    self.port = None
                    # I don't remember why we retry twice here. But reusing the port list should reduce CPU a lot.
                    time.sleep(3)
                    import serial
                    portlist = serial.tools.list_ports.comports()
                    # reconnect is designed not to raise Exceptions, so if there's0
                    # an error here it's probably because the whole scope is being cleaned
                    self.reconnect(portlist)
                    time.sleep(10)
                except Exception:
                    print("Sender thread exiting")
                    print(traceback.format_exc())
                    return

    def onFrame(self, data):
        with self.lock:
            self.data = data
            self.frame.set()


class ArtNetUniverse(Universe):
    def __init__(self, name, channels=128, address="255.255.255.255:6454", framerate=44.0, number=0):
        self.ok = True
        self.status = "OK"
        self.number = number
        self.statusChanged = {}

        x = address.split("://")
        if len(x) > 1:
            scheme = x[0]
        else:
            scheme = ''

        addr, port = x[-1].split(":")
        port = int(port)

        # Sender needs the values to be there for setup

        # Channel 0 is a dummy to make math easier.
        self.values = numpy.array([0.0] * (channels + 1), dtype="f4")
        self.sender = makeSender(ArtNetSender, weakref.ref(
            self), addr, port, framerate, scheme)

        Universe.__init__(self, name, channels)

        self.hidden = False

    def onFrame(self):
        data = (self.values)
        self.sender.onFrame(data, None, self.number)

    def __del__(self):
        # Stop the thread when this gets deleted
        self.sender.onFrame(None)

    def close(self):
        try:
            self.sender.onFrame(None)
        except Exception:
            pass
        return super().close()


class TagpointUniverse(Universe):
    "Used for outputting lighting to Kaithem's internal Tagpoint system"

    def __init__(self, name, channels=128, tagpoints={}, framerate=44.0, number=0):
        self.ok = True
        self.status = "OK"
        self.number = number
        self.statusChanged = {}
        self.tagpoints = tagpoints
        self.channelCount = channels
        self.tagObjsByNum = {}
        self.claims = {}
        self.hidden = False

        self.channelNames = {}
        # Put a claim on all the tags
        for i in self.tagpoints:
            # One higher than default
            try:
                if not i.strip():
                    continue

                x = i.split(':')

                chname = ''
                try:
                    num = int(x[0].strip())
                except Exception:
                    num = len(self.claims) + 1
                    chname = x[0].strip()

                if len(x) == 2:
                    chname = x[1].strip()
                else:
                    if not chname:
                        chname = 'tp' + str(num)

                tpn = self.tagpoints[i]
                if tpn:
                    self.tagObjsByNum[num] = kaithem.tags[tpn]
                    self.claims[num] = kaithem.tags[tpn].claim(
                        0, "Chandler_" + name, 50 if number < 2 else number)
                    self.channelNames[chname] = num

            except Exception as e:
                self.status = "error, " + i + " " + str(e)
                logger.exception("Error related to tag point " + i)
                print(traceback.format_exc())
                event("board.error", traceback.format_exc())

        # Sender needs the values to be there for setup
        self.values = numpy.array([0.0] * channels, dtype="f4")

        Universe.__init__(self, name, channels)

    def onFrame(self):
        for i in self.claims:
            try:
                x = float(self.values[i])
                if x > -1:
                    if self.tagObjsByNum[i].min is not None and self.tagObjsByNum[i].min >= -10**14:

                        # Should the tag point have a range set, and should that range be smaller than some very large possible default
                        # it could be, map the value from our 0-255 scale to whatever the tag point's scale is.
                        if self.tagObjsByNum[i].max is not None and self.tagObjsByNum[i].max <= 10**14:
                            x = x / 255
                            x *= self.tagObjsByNum[i].max - \
                                self.tagObjsByNum[i].min
                            x += self.tagObjsByNum[i].min
                    self.claims[i].set(x)
            except Exception:
                core.rl_log_exc("Error in tagpoint universe")
                print(traceback.format_exc())


def makeSender(c, uref, *a):
    return c(uref, *a)


class ArtNetSender():
    """This object is used by the universe object to send data to the enttec adapter.
        It runs in it's own thread because the frame rate might have nothing to do with
        the rate at which the data actually gets rendered.
    """

    def __init__(self, universe, addr, port, framerate, scheme):
        self.frame = threading.Event()
        self.scheme = scheme

        self.universe = universe
        self.data = False
        self.running = 1
        # The last telemetry we didn't ignore
        self.lastTelemetry = 0
        if self.scheme == "pavillion":
            def onBatteryStatus(v):
                self.universe().telemetry['battery'] = v
                if self.lastTelemetry < (time.time() - 10):
                    self.universe().statusChanged = {}

            def onConnectionStatus(v):
                self.universe().telemetry['rssi'] = v
                if self.lastTelemetry < (time.time() - 10):
                    self.universe().statusChanged = {}

            self.connectionTag = kaithem.tags["/devices/" + addr + ".rssi"]
            self._oncs = onConnectionStatus
            self.connectionTag.subscribe(onConnectionStatus)

            self.batteryTag = kaithem.tags["/devices/" + addr + ".battery"]
            self._onb = onBatteryStatus
            self.batteryTag.subscribe(onBatteryStatus)

        def run():
            import time
            import traceback
            interval = 1.1 / self.framerate

            while self.running:
                try:
                    s = time.time()
                    x = self.frame.wait(interval)
                    if not x:
                        interval = min(60, interval * 1.3)
                    else:
                        interval = 1.5 / self.framerate
                    if self.data is False:
                        continue
                    with self.lock:
                        if self.data is None:
                            print("Stopping ArtNet Sender for " + self.addr)
                            return
                        # Here we have the option to use a Pavillion device
                        if self.scheme == "pavillion":
                            try:
                                addr = kaithem.devices[self.addr].data['address']
                            except Exception:
                                time.sleep(3)
                                continue
                        else:
                            addr = self.addr

                        self.frame.clear()
                    try:
                        self.sock.sendto(self.data, (addr, self.port))
                    except Exception:
                        time.sleep(5)
                        raise

                    time.sleep(
                        max(((1.0 / self.framerate) - (time.time() - s)), 0))
                except Exception as e:
                    core.rl_log_exc("Error in artnet universe")
                    print(traceback.format_exc())
        self.thread = threading.Thread(target=run)
        self.thread.name = "ArtnetSenderThread_" + self.thread.name

        self.thread.daemon = True
        self.framerate = float(framerate)
        self.lock = threading.Lock()

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # Bind to the server address
        self.sock.bind(('', 0))
        self.sock.settimeout(1)

        self.addr = addr
        self.port = port
        self.thread.start()

    def __del__(self):
        self.running = 0



    def setStatus(self, s, ok):
        try:
            self.universe().setStatus(s, ok)
        except Exception:
            pass

    def onFrame(self, data, physical=None, universe=0):
        with self.lock:
            if not (data is None):
                # DMX starts at 1, don't send element 0 even though it exists.
                p = b'Art-Net\x00\x00\x50\x00\x0E\0' + struct.pack("<BH", physical if not physical is None else universe, universe) + struct.pack(
                    ">H", len(data)) + (data.astype(numpy.uint8).tobytes()[1:])
                self.data = p
            else:
                self.data = data
            self.frame.set()


class EnttecOpenUniverse(Universe):
    # Thanks to https://github.com/c0z3n/pySimpleDMX
    # I didn't actually use the code, but it was a very useful resouurce
    # For protocol documentation.
    def __init__(self, name, channels=128, portname="", framerate=44.0, number=0):
        self.ok = False
        self.number = number
        self.status = "Disconnect"
        self.statusChanged = {}
        # Sender needs the values to be there for setup
        self.values = numpy.array([0.0] * channels, dtype="f4")
        self.sender = makeDMXSender(weakref.ref(self), portname, framerate)

        Universe.__init__(self, name, channels)
        
        self.sender.connect()
        self.hidden = False

    def onFrame(self):
        data = rawmessage(self.values)
        self.sender.onFrame(data)

    def __del__(self):
        # Stop the thread when this gets deleted
        self.sender.onFrame(None)

    def close(self):
        try:
            self.sender.onFrame(None)
        except Exception:
            pass
        return super().close()


def makeDMXSender(uref, port, fr):
    return RawDMXSender(uref, port, fr)


class RawDMXSender():
    """This object is used by the universe object to send data to the enttec adapter.
        It runs in it's own thread because the frame rate might have nothing to do with
        the rate at which the data actually gets rendered.
    """

    def __init__(self, universe, port, framerate):
        self.frame = threading.Event()
        self.data = rawmessage(universe().values)
        self.universe = universe

        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.name = "DMXSenderThread_" + self.thread.name
        self.portname = port
        self.framerate = float(framerate)
        self.lock = threading.Lock()
        self.port = None
        self.started = None

    def setStatus(self, s, ok):
        try:
            x = self.universe()
            if x:
                x.setStatus(s, ok)
        except Exception:
            logging.exception("???")

    def connect(self):
        if not self.started:
            self.started = True
            self.thread.start()
            
        # Different status message first time
        try:
            self.reconnect()
        except Exception as e:
            self.setStatus('Could not connect, ' + str(e)[:100] + '...', False)

    def reconnect(self):
        "Try to reconnect to the adapter"
        try:
            import serial
            if not self.portname:
                import serial.tools.list_ports

                p = serial.tools.list_ports.comports()
                if p:
                    if len(p) > 1:
                        self.setStatus(
                            'More than one device found, refusing to guess. Please specify a device.', False)
                        return
                    else:
                        p = p[0].device
                else:
                    self.setStatus('No device found', False)
                    return
            else:
                p = self.portname
            time.sleep(0.1)
            try:
                self.port.close()
            except Exception:
                pass
            self.port = serial.Serial(
                p, baudrate=250000, timeout=1.0, write_timeout=1.0, stopbits=2)

            self.port.read(self.port.inWaiting())
            time.sleep(0.05)
            self.port.break_condition = True
            time.sleep(0.0001)
            self.port.break_condition = False
            time.sleep(0.0003)
            self.port.write(self.data)
            self.port.flush()
            self.setStatus('connected to ' + p, True)

        except Exception as e:
            try:
                self.setStatus('dis_connected, ' + str(e)[:100] + '...', False)
            except Exception:
                pass

    def run(self):
        while self.universe():
            try:
                s = time.time()
                self.port.read(self.port.inWaiting())
                x = self.frame.wait(0.1)
                with self.lock:
                    if self.data is None:
                        try:
                            self.port.close()
                        except Exception:
                            pass
                        return

                    self.port.break_condition = True
                    time.sleep(0.0001)
                    self.port.break_condition = False
                    time.sleep(0.0003)

                    self.port.write(self.data)
                    if x:
                        self.frame.clear()
                time.sleep(
                    max(((1.0 / self.framerate) - (time.time() - s)), 0))
            except Exception as e:
                try:
                    self.port.close()
                except Exception:
                    pass
                try:
                    if self.data is None:
                        return
                    if self.port:
                        self.setStatus('dis_connected, ' + str(e)
                                       [:100] + '...', False)
                    self.port = None
                    # reconnect is designed not to raise Exceptions, so if there's0
                    # an error here it's probably because the whole scope is being cleaned
                    time.sleep(8)
                    self.reconnect()
                except Exception:
                    return

    def onFrame(self, data):
        with self.lock:
            self.data = data
            self.frame.set()


colorTagDeviceUniverses = {}
addedTags = {}

discoverlock = threading.RLock()


def onDelTag(t, m):
    if m in addedTags:
        with discoverlock:
            if m in addedTags:
                del addedTags[m]
                discoverColorTagDevices()


kaithem.message.subscribe("/system/tags/deleted", onDelTag)


def onAddTag(t, m):
    if 'color' not in m and 'fade' not in m and 'light' not in m and 'bulb' not in m and 'colour' not in m:
        return
    discoverColorTagDevices()


kaithem.message.subscribe("/system/tags/created", onAddTag)
kaithem.message.subscribe("/system/tags/configured", onAddTag)


def discoverColorTagDevices():
    global colorTagDeviceUniverses

    u = {}

    # Devices may have "subdevices" represented by tag heirarchy, like:
    # /devices/devname/subdevice.color

    def handleSubdevice(dev, sd, c, ft):
        if dev == sd:
            name = dev
        else:
            name = dev + "." + sd

        addedTags[c.name] = True
        if ft:
            addedTags[ft.name] = True

        with universesLock:
            if name not in _universes:
                u[name] = ColorTagUniverse(name, c, ft)
            else:
                u[name] = _universes[name]()

    for i in kaithem.devices:
        d = kaithem.devices[i]
        c = None
        ft = None

        last_sd = None
        for j in sorted(d.tagPoints.keys()):
            jn = d.tagPoints[j].name
            # everything between the last slash and the dot, because the dot marks "property of"
            subdevice = jn.split('/')[-1].split('.')[0]

            if last_sd and c and not subdevice == last_sd:
                handleSubdevice(i, subdevice, c, ft)
                c = None
                ft = None

            last_sd = subdevice

            t = d.tagPoints[j]

            if t.subtype == 'color':
                c = t

            elif t.subtype == "light_fade_duration":
                ft = t

        # Found something with a color!
        if c:
            handleSubdevice(i, subdevice, c, ft)

    colorTagDeviceUniverses = u


class ColorTagUniverse(Universe):
    """
        Detects devices with a "color" property having the subtype color.
    """

    def __init__(self, name, tag, fadeTag=None):
        self.ok = True
        self.status = "Disconnect"
        self.statusChanged = {}
        Universe.__init__(self, name, 4)
        self.hidden = False
        self.tag = tag
        self.f = Fixture(self.name + ".rgb",
                         [['R', 'red'], ['G', 'green'], ['B', 'blue']])
        self.f.assign(self.name, 1)
        self.lock = threading.RLock()

        self.lastColor = None

        if fadeTag:
            self.fadeTag = fadeTag
            self.localFading = False
        else:
            self.fadeTag = None
            self.localFading = True

    def onFrame(self):
        def f():
            if self.lock.acquire(timeout=1):
                try:
                    self._onFrame()
                finally:
                    self.lock.release()
        kaithem.misc.do(f)

    def _onFrame(self):
        c = colorzero.Color.from_rgb(
            self.values[1] / 255, self.values[2] / 255, self.values[3] / 255).html

        tm = time.monotonic()

        # Only set the fade tag right before we are about to do something with the bulb, otherwise we would be adding a ton
        # of useless writes
        if not c == self.lastColor or not c == self.tag.value:
            self.lastColor = c
            if self.fadeTag:
                t = max(self.fadeEndTime - time.time(),
                        self.interpolationTime, 0)
                # Round to the nearest 20th of a second so we don't accidentally set the values more often than needed if it doesn't change
                t = int(t * 20) / 20
                self.fadeTag(t, tm, annotation="Chandler")

            self.tag(c, tm, annotation="Chandler")


core.discoverColorTagDevices = discoverColorTagDevices


def getUniverse(u: Optional[str]) -> Optional[Universe]:
    "Get strong ref to universe if it exists, else get none."
    if not u:
        return None
    try:
        oldUniverseObj = universes[u]()
    except KeyError:
        oldUniverseObj = None
    return oldUniverseObj


def getUniverses() -> Dict[str, Universe]:
    "Returns dict of strong refs to universes, filtered to exclude weak refs"
    m = universes
    u = {}
    for i in m:
        x = m[i]()
        if x:
            u[i] = x

    return u


def rerenderUniverse(i: str):
    universe = getUniverse(i)
    if universe:
        universe.full_rerender = True


def mapUniverse(u:str):
    if not u.startswith("@"):
        return u

    u = u.split("[")[0]

    try:
        x = fixtures[u[1:]]()
        if not x:
            return None
    except KeyError:
        return None
    return x.universe


def mapChannel(u: str, c: str | int):
    index = 1

    if isinstance(c, str):
        if c.startswith("__"):
            return None
        # Handle the notation for repeating fixtures
        if "[" in c:
            c, index = c.split("[")
            index = int(index.split("]")[0].strip())

    if not u.startswith("@"):
        if isinstance(c, str):
            universe = getUniverse(u)
            if universe:
                c = universe.channelNames.get(c, None)
                if not c:
                    return None
                else:
                    return u, int(c)
        else:
            return u, int(c)

    try:
        f = fixtures[u[1:]]()
        if not f:
            return None

    except KeyError:
        return None
    x = f.assignment
    if not x:
        return

    # Index advance @fixture[5] means assume @fixture is the first of 5 identical fixtures and you want #5
    return x[0], int(x[1] + f.nameToOffset[c] + ((index - 1) * len(f.channels)))
