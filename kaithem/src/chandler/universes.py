"""Important things about this module:"""

from __future__ import annotations

import gc
import json
import logging
import socket
import struct
import threading
import time
import traceback
import weakref
from typing import Any

import colorzero
import numpy
import serial
import serial.tools.list_ports
import structlog

from kaithem.api import lifespan
from kaithem.src import alerts

from ..kaithemobj import kaithem
from . import core
from .core import disallow_special

logger = structlog.get_logger(__name__)

# Locals for performance... Is this still a thing??
float = float
abs = abs
int = int
max = max
min = min


# universes and universes state are protected under the render loop lock
universes: dict[str, weakref.ReferenceType[Universe]] = {}

# MUTABLE
_universes: dict[str, weakref.ReferenceType[Universe]] = {}


fixtures: dict[str, weakref.ref[Fixture]] = {}

last_state_update = time.time()


def refresh_groups():
    """Tell groups the set of universes has changed"""
    global last_state_update
    last_state_update = time.time()

    def f():
        for b in core.iter_boards():
            for i in b.active_groups:
                with i.lock:
                    i.refresh_lighting()

    core.serialized_async_with_core_lock(f)


def get_on_demand_universe(name: str) -> Universe:
    global universes
    if not name.strip().startswith("/"):
        raise ValueError("Only tag point universes")

    if name in universes:
        try:
            x = universes[name]()
            if x:
                return x
        except KeyError:
            pass

    t = OneTagpoint(name)
    core.add_data_pusher_to_all_boards(
        lambda s: s.pushchannelInfoByUniverseAndNumber(name)
    )  # type: ignore
    return t


class Fixture:
    def __init__(self, name: str, data: dict[str, Any] | None = None):
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
        # Not threadsafe or something to rely on,
        # just an extra defensive check
        if name in fixtures:
            raise ValueError("Name in Use")

        if data:
            channel_data = data.get("channels", None)
        else:
            channel_data = None

        self.channels: list[dict[str, Any]]

        if channel_data:
            # Normalize and raise errors on nonsense
            channels: list[dict[str, Any]] = json.loads(
                json.dumps(channel_data)
            )

            assert isinstance(channels, list)
            self.channels = channels

        else:
            channels = []
            self.channels = channels

        self.universe: str | None = None
        self.startAddress: int | None = 0
        self.assignment: tuple[str, int] | None = None
        disallow_special(name, ".")

        self.nameToOffset: dict[str, int] = {}

        # Used for looking up channel by name
        for i in range(len(channels)):
            self.nameToOffset[channels[i]["name"]] = i

        fixtures[name] = weakref.ref(self)
        self.name = name

        global last_state_update
        last_state_update = time.time()

    def getChannelByName(self, name: str):
        if self.startAddress:
            return self

    def __del__(self):
        def f():
            # Todo think more about if theres a race condition
            if self.name not in fixtures:
                return

            if fixtures[self.name]() is not self:
                return

            logger.warn(f"Auto-deleting fixture {self.name}")
            with core.cl_context:
                try:
                    del fixtures[self.name]
                except KeyError:
                    pass

                ID = id(self)

                try:
                    x = fixtures[self.name]()
                    if id(x) == id(ID):
                        self.cl_assign(None, None)
                        self.rm()
                except KeyError:
                    pass
                except Exception:
                    print(traceback.format_exc())
            global last_state_update
            last_state_update = time.time()

        kaithem.misc.do(f)

    def rm(self):
        try:
            del fixtures[self.name]
        except Exception:
            print(traceback.format_exc())
        global last_state_update
        last_state_update = time.time()

    @core.cl_context.required
    def cl_assign(self, universe: str | None, channel: int | None):
        if universe is None:
            if channel is not None:
                raise ValueError("Cannot specify channel without universe")

        if channel is None:
            if universe is not None:
                raise ValueError("Cannot specify universe without channel")

        # First just clear the old assignment, if any
        if self.universe and self.startAddress:
            oldUniverseObj = getUniverse(self.universe)

            # All fixture channels together. This is safe because there are no nontrivial
            # function calls under this, and we are in the proper lock order
            with core.render_loop_lock:
                if oldUniverseObj:
                    # Delete current assignments
                    for i in range(
                        self.startAddress,
                        self.startAddress + len(self.channels),
                    ):
                        if i in oldUniverseObj.channels:
                            # Ensure we are not assigning something else with same name
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

        # Again, no non-safe calls under this lock.
        with core.render_loop_lock:
            if universe:
                assert channel is not None
                self.assignment = universe, channel
            else:
                self.assignment = None

            self.universe = universe
            self.startAddress = channel

            universeObj = getUniverse(universe)

            if not universeObj:
                return

            core.fixtureschanged = {}

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
                if self.channels[cPointer]["type"] in ("hue", "sat", "custom"):
                    # Mark it as a hue channel that blends slightly differently
                    universeObj.hueBlendMask[i] = 1
                    cPointer += 1

        universeObj.fixtures[self.name] = weakref.ref(self)
        universeObj.cl_channels_changed()
        global last_state_update
        last_state_update = time.time()


class Universe:
    "Represents a lighting universe, similar to a DMX universe, but is not limited to DMX."

    refresh_on_create = True

    def __init__(self, name: str, count: int = 512, number: int = 0):
        global universes
        for i in ":[]()*\\`~!@#$%^&*=+|{}'\";<>,":
            if i in name:
                raise ValueError(
                    "Name cannot contain special characters except _"
                )
        self.name = name
        self.closed = False

        self.hidden = True

        # If local fading is disabled, the rendering tries to compress everything down to a set of fade commands.
        # This is the time at which the current fade is supposed to end.
        self.fadeEndTime = 0.0

        # If False, lighting values don't fade in, they just jump straight to the target,
        # For things like smart bulbs where we want to use the remote fade instead.
        self.localFading = True

        # Used by blend modes to request that the
        # remote device do onboard interpolation
        # The longest time requested by any layer is used
        # The final interpolation time is the greater of
        # This and the time determined by fadeEndTime
        self.interpolationTime = 0.0

        # Let subclasses set these
        if not hasattr(self, "status"):
            self.status = "normal"
        if not hasattr(self, "ok"):
            self.ok = True

        # name:weakref(fixture) for every fixture that is mapped to this universe
        self.fixtures = {}

        # Represents the telemetry data back from the physical device of this universe.
        self.telemetry = {}

        # Dict of all board ids that have already pushed a status update
        self.statusChanged = {}
        self.channels: dict[int, weakref.ref[Fixture]] = {}

        # Maps names to numbers, mostly for tagpoint universes.
        if not hasattr(self, "channelInfoByUniverseAndNumber"):
            self.channelInfoByUniverseAndNumber = {}

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
        self.fine_channels: dict[int, int] = {}

        # Map fixed channel numbers to values.
        # We implemnet that here so they are fixed no matter what the groups and blend modes say
        self.fixed_channels: dict[int, float] = {}

        # Used for the caching. It's the layer we want to save as the background state before we apply.
        # Calculated as either the last group rendered in the stack or the first group that requests a rerender that affects the universe
        self.save_before_layer = (0.0, 0.0)
        # Reset in pre_render, indicates if we've not rendered a layer that we think is going to change soon
        # so far in this frame
        self.all_static = True

        self.error_alert = alerts.Alert(
            f"{self.name}.errorState", priority="error", auto_ack=True
        )

        # flag to apply all groups, even ones not marked as neding rerender
        self.full_rerender = False

        # The priority, started of the top layer layer that's been applied to this group.
        self.top_layer = (0, 0)

        # This is the priority, started of the "saved" layer that's been cached so we don't
        # Have to rerender it or anything below it.
        self.prerendered_layer = (0, 0)

        # A copy of the state of the universe just after prerendered_layer was rendered, so we can go back
        # and start from there without rerendering lower layers.

        # The format is values,alphas
        self.prerendered_data = (
            numpy.array([0.0] * count, dtype="f4"),
            numpy.array([0.0] * count, dtype="f4"),
        )

        # Maybe there might be an iteration error. But it's just a GUI convenience that
        # A simple refresh solves, so ignore it.
        try:
            for i in core.iter_boards():
                i.push_setup()
        except Exception:
            logger.exception("Exception in push_setup")

        global _universes, universes
        if name in _universes and _universes[name]():
            gc.collect()
            time.sleep(0.1)
            gc.collect()
            # We retry, because the universes are often temporarily cached as strong refs
            if name in _universes and _universes[name]():
                try:
                    u = None
                    try:
                        u = _universes[name]()
                    except KeyError:
                        pass
                    if u:
                        u.close()
                except Exception:
                    raise ValueError("Name " + name + " is taken")

        with core.render_loop_lock:
            _universes[name] = weakref.ref(self)
            universes = {
                i: _universes[i] for i in _universes if _universes[i]()
            }

        global last_state_update
        last_state_update = time.time()

        if self.refresh_on_create:
            kaithem.message.post("/chandler/command/refreshFixtures", self.name)
            self.refresh_groups()

    def close(self):
        global universes

        with core.render_loop_lock:
            # Don't delete the object that replaced this
            if self.name in _universes and (_universes[self.name]() is self):
                del _universes[self.name]

            universes = {
                i: _universes[i] for i in _universes if _universes[i]()
            }

            def alreadyClosed(*a, **k):
                pass

            self.onFrame = alreadyClosed
            self.setStatus = alreadyClosed
            self.refresh_groups = alreadyClosed
            self.reset_to_cache = alreadyClosed
            self.reset = alreadyClosed
            self.preFrame = alreadyClosed
            self.save_prerendered = alreadyClosed

        refresh_groups()
        self.closed = True
        global last_state_update
        last_state_update = time.time()

    def setStatus(self, s: str, ok: bool):
        "Set the status shown in the gui. ok is a bool value that indicates if the object is able to transmit data to the fixtures"
        if ok:
            self.error_alert.release()
        else:
            self.error_alert.trip(message=str(s))

        # avoid pushing unnecessary statuses
        if (self.status == s) and (self.ok == ok):
            return
        self.status = s
        self.ok = ok
        self.statusChanged = {}

    def refresh_groups(self):
        """Stop and restart all active groups, because some caches might need to be updated
        when a new universes is added
        """
        refresh_groups()

    def __del__(self):
        if not self.closed:
            if self.refresh_on_create:
                if lifespan and not lifespan.shutdown:
                    # Do as little as possible in the undefined __del__ thread
                    refresh_groups()
            global last_state_update
            last_state_update = time.time()

    @core.cl_context.required
    def cl_channels_changed(self):
        "Call this when fixtures are added, moved, or modified."
        self.fine_channels = {}
        self.fixed_channels = {}

        for i in self.channels:
            fixture = self.channels[i]()
            if not fixture:
                continue
            if not fixture.startAddress:
                continue
            data = fixture.channels[i - fixture.startAddress]
            if data["type"] == "fine":
                if isinstance(data["coarse"], int):
                    self.fine_channels[i] = (
                        fixture.startAddress + data["coarse"]
                    )
                else:
                    for num, ch in enumerate(fixture.channels):
                        if ch.get("name", "") == data["coarse"]:
                            self.fine_channels[i] = fixture.startAddress + num

            if data["type"] == "fixed":
                self.fixed_channels[i] = data["value"]

    def reset_to_cache(self):
        "Remove all changes since the prerendered layer."
        values, alphas = self.prerendered_data
        self.values = numpy.copy(values)
        self.alphas = numpy.copy(alphas)

        self.top_layer = self.prerendered_layer

    def save_prerendered(self, p, s):
        "Save this layer as the cached layer. Called in the render functions"
        self.prerendered_layer = (p, s)
        self.prerendered_data = (
            numpy.copy(self.values),
            numpy.copy(self.alphas),
        )

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
    return b"\x7e\x06" + struct.pack("<H", len(data)) + data + b"\xe7"


def rawmessage(data):
    "An enttec open DMX message from a set of values"
    data = numpy.maximum(numpy.minimum(data, 255), 0)
    data = data.astype(numpy.uint8)
    data = data.tobytes()
    # Remove the 0 position as DMX starts at 1
    return b"\0" + (data[1:513])


class EnttecUniverse(Universe):
    # Thanks to https://github.com/c0z3n/pySimpleDMX
    # I didn't actually use the code, but it was a very useful resource
    # For protocol documentation.
    def __init__(
        self,
        name: str,
        channels: int = 512,
        portname: str = "",
        framerate: float = 44.0,
        number: int = 0,
    ):
        self.ok = False
        self.number = number
        self.status = "Disconnect"
        self.statusChanged = {}
        # Sender needs the values to be there for setup
        self.values = numpy.array([0.0] * channels, dtype="f4")
        self.sender = makeSender(
            DMXSender, weakref.ref(self), portname, framerate
        )

        Universe.__init__(self, name, channels)
        self.sender.connect()

        self.hidden = False

    def onFrame(self):
        data = message(self.values)
        self.sender.onFrame(data)

    def __del__(self):
        # Stop the thread when this gets deleted
        self.sender.onFrame(None)

    @core.cl_context.required
    def close(self):
        try:
            self.sender.onFrame(None)
        except Exception:
            pass
        return super().close()


class DMXSender:
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
            self.setStatus("Could not connect, " + str(e)[:100] + "...", False)

    def reconnect(self, portlist=None):
        "Try to reconnect to the adapter"
        try:
            if not self.portname:
                p = portlist or serial.tools.list_ports.comports()
                if p:
                    if len(p) > 1:
                        self.setStatus(
                            "More than one device found, refusing to guess. Please specify a device.",
                            False,
                        )
                        return
                    else:
                        p = p[0].device
                else:
                    self.port = None
                    self.setStatus("No device found", False)
                    return
            else:
                p = self.portname
            time.sleep(0.1)
            try:
                if self.port:
                    self.port.close()
            except Exception:
                pass
            self.port = serial.Serial(p, 57600, timeout=1.0, write_timeout=1.0)

            # This is a flush to try to re-sync receivers that don't have any kind of time out detection
            # We do this by sending a frame where each value is the packet end code,
            # Hoping that it lines up with the end of whatever unfinished data we don't know about.
            self.setStatus("Found port, writing sync data", True)

            for i in range(8):
                self.port.write(message(numpy.array([231] * 120)))
                time.sleep(0.05)
            self.port.write(
                message(numpy.zeros(max(128, len(self.universe().values))))
            )
            time.sleep(0.1)
            self.port.read(self.port.in_waiting)
            time.sleep(0.05)
            self.port.write(self.data)
            self.setStatus("connected to " + p, True)
        except Exception as e:
            try:
                self.port = None
                self.setStatus("disconnected, " + str(e)[:100] + "...", False)
            except Exception:
                pass

    def run(self):
        while 1:
            try:
                assert self.port
                s = time.time()
                self.port.read(self.port.in_waiting)
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
                time.sleep(max(((1.0 / self.framerate) - (time.time() - s)), 0))
            except Exception as e:
                try:
                    if self.port:
                        self.port.close()
                except Exception:
                    pass
                try:
                    if self.data is None:
                        return
                    if self.port:
                        self.setStatus(
                            "disconnected, " + str(e)[:100] + "...", False
                        )
                    self.port = None
                    # I don't remember why we retry twice here. But reusing the port list should reduce CPU a lot.
                    time.sleep(3)

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
    def __init__(
        self,
        name,
        channels=128,
        address="255.255.255.255:6454",
        framerate=44.0,
        number=0,
    ):
        self.ok = True
        self.status = "OK"
        self.number = number
        self.statusChanged = {}

        x = address.split("://")
        if len(x) > 1:
            scheme = x[0]
        else:
            scheme = ""

        addr, port = x[-1].split(":")
        port = int(port)

        # Sender needs the values to be there for setup

        # Channel 0 is a dummy to make math easier.
        self.values = numpy.array([0.0] * (channels + 1), dtype="f4")
        self.sender = makeSender(
            ArtNetSender, weakref.ref(self), addr, port, framerate, scheme
        )

        Universe.__init__(self, name, channels)

        self.hidden = False

    def onFrame(self):
        data = self.values
        self.sender.onFrame(data, None, self.number)

    def __del__(self):
        # Stop the thread when this gets deleted
        self.sender.onFrame(None)

    @core.cl_context.required
    def close(self):
        try:
            self.sender.onFrame(None)
        except Exception:
            pass
        return super().close()


def makeSender(c, uref, *a):
    return c(uref, *a)


class ArtNetSender:
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

                        addr = self.addr
                        self.frame.clear()
                    try:
                        self.sock.sendto(self.data, (addr, self.port))
                    except Exception:
                        time.sleep(5)
                        raise

                    time.sleep(
                        max(((1.0 / self.framerate) - (time.time() - s)), 0)
                    )
                except Exception:
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
        self.sock.bind(("", 0))
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
            if data is not None:
                # DMX starts at 1, don't send element 0 even though it exists.
                p = (
                    b"Art-Net\x00\x00\x50\x00\x0e\0"
                    + struct.pack(
                        "<BH",
                        physical if physical is not None else universe,
                        universe,
                    )
                    + struct.pack(">H", len(data))
                    + (data.astype(numpy.uint8).tobytes()[1:])
                )
                self.data = p
            else:
                self.data = data
            self.frame.set()


class EnttecOpenUniverse(Universe):
    # Thanks to https://github.com/c0z3n/pySimpleDMX
    # I didn't actually use the code, but it was a very useful resource
    # For protocol documentation.
    def __init__(
        self, name, channels=512, portname="", framerate=44.0, number=0
    ):
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

    @core.cl_context.required
    def close(self):
        try:
            self.sender.onFrame(None)
        except Exception:
            pass
        return super().close()


def makeDMXSender(uref, port, fr):
    return RawDMXSender(uref, port, fr)


class RawDMXSender:
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

        self.should_stop = False

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
            self.setStatus("Could not connect, " + str(e)[:100] + "...", False)

    def reconnect(self):
        "Try to reconnect to the adapter"
        try:
            if not self.portname:
                p = serial.tools.list_ports.comports()
                if p:
                    if len(p) > 1:
                        self.setStatus(
                            "More than one device found, refusing to guess. Please specify a device.",
                            False,
                        )
                        return
                    else:
                        p = p[0].device
                else:
                    self.setStatus("No device found", False)
                    return
            else:
                p = self.portname
            time.sleep(0.1)
            try:
                if self.port:
                    self.port.close()
            except Exception:
                pass
            self.port = serial.Serial(
                p, baudrate=250000, timeout=1.0, write_timeout=1.0, stopbits=2
            )

            self.port.read(self.port.in_waiting)
            time.sleep(0.05)
            self.port.break_condition = True
            time.sleep(0.0001)
            self.port.break_condition = False
            time.sleep(0.0003)
            self.port.write(self.data)
            self.port.flush()
            self.setStatus("connected to " + p, True)

        except Exception as e:
            try:
                self.setStatus("disconnected, " + str(e)[:100] + "...", False)
            except Exception:
                pass

    def run(self):
        while self.universe():
            try:
                assert self.port
                s = time.time()
                self.port.read(self.port.in_waiting)
                x = self.frame.wait(0.1)
                if self.should_stop:
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
                time.sleep(max(((1.0 / self.framerate) - (time.time() - s)), 0))
            except Exception as e:
                try:
                    if self.port:
                        self.port.close()
                except Exception:
                    pass
                try:
                    if self.data is None:
                        return
                    if self.port:
                        self.setStatus(
                            "disconnected, " + str(e)[:100] + "...", False
                        )
                    self.port = None
                    # reconnect is designed not to raise Exceptions, so if there's0
                    # an error here it's probably because the whole scope is being cleaned
                    time.sleep(8)
                    self.reconnect()
                except Exception:
                    return

    def onFrame(self, data):
        if data is None:
            self.should_stop = True
        else:
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
                cl_discover_color_tag_devices()


kaithem.message.subscribe("/system/tags/deleted", onDelTag)


def onAddTag(t, m):
    if (
        "color" not in m
        and "fade" not in m
        and "light" not in m
        and "bulb" not in m
        and "colour" not in m
    ):
        return
    cl_discover_color_tag_devices()


kaithem.message.subscribe("/system/tags/created", onAddTag)
kaithem.message.subscribe("/system/tags/configured", onAddTag)


def cl_discover_color_tag_devices():
    global colorTagDeviceUniverses

    u = {}

    # Devices may have "subdevices" represented by tag hierarchy, like:
    # /devices/devname/subdevice.color

    def handleSubdevice(dev, sd, c, ft):
        global _universes
        if dev == sd:
            name = dev
        else:
            name = dev + "." + sd

        addedTags[c.name] = True
        if ft:
            addedTags[ft.name] = True

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
            subdevice = jn.split("/")[-1].split(".")[0]

            if last_sd and c and not subdevice == last_sd:
                handleSubdevice(i, subdevice, c, ft)
                c = None
                ft = None

            last_sd = subdevice

            t = d.tagPoints[j]

            if t.subtype == "color":
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
        self.f = Fixture(
            self.name + ".rgb",
            {
                "channels": [
                    {"name": "red", "type": "red"},
                    {"name": "green", "type": "green"},
                    {"name": "blue", "type": "blue"},
                ]
            },
        )
        with core.cl_context:
            self.f.cl_assign(self.name, 1)
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
            self.values[1] / 255, self.values[2] / 255, self.values[3] / 255
        ).html

        tm = time.time()

        # Only set the fade tag right before we are about to do something with the bulb, otherwise we would be adding a ton
        # of useless writes
        if not c == self.lastColor or not c == self.tag.value:
            self.lastColor = c
            if self.fadeTag:
                t = max(
                    self.fadeEndTime - time.time(), self.interpolationTime, 0
                )
                # Round to the nearest 20th of a second so we don't accidentally set the values more often than needed if it doesn't change
                t = int(t * 20) / 20
                self.fadeTag(t, tm, annotation="Chandler")

            self.tag(c, tm, annotation="Chandler")


class OneTagpoint(Universe):
    "Used for outputting lighting to Kaithem's internal Tagpoint system"

    refresh_on_create = False

    def __init__(
        self, name, channels=3, tagpoints={}, framerate=44.0, number=0
    ):
        self.ok = True
        self.status = "OK"
        self.number = number
        self.statusChanged = {}
        self.tagpoint = kaithem.tags[name]
        self.claim = None

        self.count = 3
        self.hidden = True

        self.prev = (-1, -1)

        self.channelInfoByUniverseAndNumber = {"value": 1}

        # Sender needs the values to be there for setup
        self.values = numpy.array([0.0] * (self.count), dtype="f4")

        Universe.__init__(self, name, self.count)

    def onFrame(self):
        try:
            x = float(self.values[1])
            a = float(self.alphas[1])

            t = (x, a)

            if (x > -1) and (a > 0):
                self.claim = self.tagpoint.claim(x, "ChandlerUniverse", 50)
            else:
                self.tagpoint.release("ChandlerUniverse")

            self.prev = t

        except Exception:
            core.rl_log_exc("Error in tagpoint universe")
            print(traceback.format_exc())


def getUniverse(u: str | None) -> Universe | None:
    """Get strong ref to universe if it exists, else get none. must be
    safe to call under render loop lock.
    """
    global universes
    if not u:
        return None
    try:
        oldUniverseObj = universes[u]()
    except KeyError:
        oldUniverseObj = None
    return oldUniverseObj


def getUniverses() -> dict[str, Universe]:
    "Returns dict of strong refs to universes, filtered to exclude weak refs"
    global universes
    m = universes
    u = {}
    for i in m:
        x = m[i]()
        if x:
            u[i] = x

    return u


def rerenderUniverse(i: str):
    """Set full_rerender to true on a given universe, if it exists. must be
    safe to call under render loop lock."""
    universe = getUniverse(i)
    if universe:
        universe.full_rerender = True


def mapUniverse(u: str):
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


def mapChannel(u: str, c: str | int) -> tuple[str, int] | None:
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
            # Special case the tag points, we need to map before they
            # actually exist
            if c == "value" and u[0] == "/":
                return u, 1

            universe = getUniverse(u)
            if universe:
                c = universe.channelInfoByUniverseAndNumber.get(c, None)
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

    if c not in f.nameToOffset:
        return

    # Index advance @fixture[5] means assume @fixture is the first of 5 identical fixtures and you want #5
    return x[0], int(x[1] + f.nameToOffset[c] + ((index - 1) * len(f.channels)))
