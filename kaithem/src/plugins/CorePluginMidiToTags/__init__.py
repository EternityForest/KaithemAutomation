# SPDX-License-Identifier: GPL-3.0-or-later

"""
JACK-based MIDI input fan-out.

A dedicated JACK client (registered under the name ``OUR_CLIENT_NAME``)
listens on every external MIDI output port in the JACK graph (which
under pipewire-jack corresponds to every MIDI device the system can
see) and dispatches events to the messagebus at ``/midi/<normalized>``
and to tag points at ``/midi/<normalized>/<channel>.<kind>``.

We deliberately do *not* use python-rtmidi / rtmidi2 any more: the
JACK-Client library's built-in MIDI support is sufficient and means we
have one audio/MIDI subsystem instead of two.
"""

import queue
import re
import threading
import time
import traceback
from typing import Any

import jack
from scullery import jacktools, messagebus

from kaithem.src import tagpoints

# Public name of our JACK client.  Used both for the actual jack.Client
# call and to filter our own ports out of the listing.
OUR_CLIENT_NAME = "KaithemMidi"


midi_tags = {}


def setTag(n: str, v: int, a: Any = None):
    if n not in midi_tags:
        midi_tags[n] = tagpoints.Tag(n)
        midi_tags[n].min = 0
        midi_tags[n].max = 127
    midi_tags[n].set_claim_val("default", v, timestamp=None, annotation=None)


def setTag14(n: str, v: int, a: Any = None):
    if n not in midi_tags:
        midi_tags[n] = tagpoints.Tag(n)
        midi_tags[n].min = 0
        midi_tags[n].max = 16383
    midi_tags[n].set_claim_val("default", v, timestamp=None, annotation=None)


def normalize_midi_name(t: str):
    # Replace the "128:0" part that rtmidi used to add to virtual port names.
    t = re.sub(r"\d+:\d+", "", t)

    t = (
        t.lower()
        .replace(":", "_")
        .replace("[", "")
        .replace("]", "")
        .replace(" ", "_")
    )

    t = t.replace("-", "_")
    for i in tagpoints.ILLEGAL_NAME_CHARS:
        t = t.replace(i, "")

    t = t.strip("_")
    t = t.strip()
    return t


def onMidiMessageTuple(m: tuple[list[int]], d: str):
    sb = m[0][0]
    code = sb & 240
    ch = sb & 15

    # Convert to one-based
    ch += 1

    a = m[0][1]
    b = m[0][2]

    if code == 144:
        messagebus.post_message(f"/midi/{d}", ("noteon", ch, a, b))
        setTag(f"/midi/{d}/{str(ch)}.note", a, a=b)

    elif code == 128:
        messagebus.post_message(f"/midi/{d}", ("noteoff", ch, a, b))
        setTag(f"/midi/{d}/{str(ch)}.note", 0, a=0)

    elif code == 224:
        messagebus.post_message(f"/midi/{d}", ("pitch", ch, a, b))
        setTag14(f"/midi/{d}/{str(ch)}.pitch", a + b * 128, a=0)

    elif code == 176:
        messagebus.post_message(f"/midi/{d}", ("cc", ch, a, b))
        setTag(f"/midi/{d}/{str(ch)}.cc.{str(a)}", b, a=0)


# ---------------------------------------------------------------------------
# JACK client management
# ---------------------------------------------------------------------------

# source_port_name -> (jack.OwnMidiPort, normalized_name)
_our_ports: dict[str, tuple[jack.OwnMidiPort, str]] = {}
_ports_lock = threading.Lock()

# FIFO between the JACK RT process callback and our worker thread.
_event_queue: "queue.Queue[tuple[str, bytes]]" = queue.Queue()

# Singleton manager (populated by init()).
_manager: "JackMidiManager | None" = None


def get_jack_client_name() -> str:
    """Name of the JACK client we own.  Used by other modules that
    need to filter our ports out of the listing."""
    return OUR_CLIENT_NAME


def list_midi_sources() -> list[str]:
    """Return raw (unnormalized) full port names of all external MIDI
    output ports visible to JACK right now."""
    try:
        ports = jacktools.get_ports(is_midi=True, is_output=True)
        return [p.name for p in ports if p.clientName != OUR_CLIENT_NAME]
    except Exception:
        return []


class JackMidiManager:
    """Owns a single JACK client, auto-connects to external MIDI output
    ports, and dispatches incoming MIDI events to the messagebus / tag
    points.

    A small FIFO is used to move bytes out of the real-time process
    callback so the worker thread can do all the user-facing work.
    """

    def __init__(self):
        self._stopped = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._client: jack.Client | None = None
        # Counter used to give each of our input ports a unique shortname.
        self._slot_counter = 0

        try:
            self._client = jack.Client(OUR_CLIENT_NAME)
        except Exception:
            messagebus.post_message(
                "/system/notifications/errors",
                "Failed to create JACK MIDI client. MIDI features disabled.\n"
                + traceback.format_exc(),
            )
            return

        try:
            self._client.set_process_callback(self._process)
            self._client.activate()
        except Exception:
            messagebus.post_message(
                "/system/notifications/errors",
                "Failed to activate JACK MIDI client. MIDI features disabled.\n"
                + traceback.format_exc(),
            )
            self._client = None
            return

        messagebus.subscribe("/system/jack/newport", self._on_new_port)
        messagebus.subscribe("/system/jack/delport", self._on_del_port)
        # When JACK (re)starts we need to re-scan because ports come and go.
        messagebus.subscribe("/system/sound/jackstart", self._on_jack_start)

        # Initial scan picks up anything that was already registered
        # before we subscribed to the messagebus.
        self._initial_scan()

        self._worker_thread = threading.Thread(
            target=self._worker, daemon=True, name="KaithemMidiWorker"
        )
        self._worker_thread.start()

    # -- JACK port lifecycle -------------------------------------------------

    def _initial_scan(self):
        try:
            ports = jacktools.get_ports(is_midi=True, is_output=True)
            for p in ports:
                if p.clientName != OUR_CLIENT_NAME:
                    self._register_source(p)
        except Exception:
            traceback.print_exc()

    def _on_new_port(self, _topic, port_info: jacktools.PortInfo):
        try:
            if port_info.is_audio or port_info.is_input:
                return
            if port_info.clientName == OUR_CLIENT_NAME:
                return
            self._register_source(port_info)
        except Exception:
            traceback.print_exc()

    def _on_del_port(self, _topic, port_info: jacktools.PortInfo):
        with _ports_lock:
            _our_ports.pop(port_info.name, None)

    def _on_jack_start(self, _topic, _msg):
        # JACK came back up.  Re-scan so we re-attach to anything that
        # is still there.
        self._initial_scan()

    def _register_source(self, port_info: jacktools.PortInfo):
        if self._client is None:
            return

        with _ports_lock:
            if port_info.name in _our_ports:
                return

            slot = self._slot_counter
            self._slot_counter += 1
            shortname = f"midi_in_{slot}"
            try:
                our_port = self._client.midi_inports.register(shortname)
            except Exception:
                traceback.print_exc()
                return

            assert isinstance(our_port, jack.OwnMidiPort)

            normalized = normalize_midi_name(port_info.name)
            _our_ports[port_info.name] = (our_port, normalized)

            our_full_name = our_port.name
            source_name = port_info.name

        # Connecting straight away often fails because the port isn't
        # visible to the rest of the graph yet.  Try a few times with a
        # small delay.
        def connect_later():
            for _ in range(10):
                time.sleep(0.2)
                try:
                    jacktools.connect(source_name, our_full_name)
                except Exception:
                    continue
                else:
                    return
            traceback.print_exc()

        threading.Thread(
            target=connect_later, daemon=True, name="KaithemMidiConnect"
        ).start()

    # -- Process callback / worker ------------------------------------------

    def _process(self, _frames):
        # Keep the work here minimal: snapshot the port list under the
        # lock, then drain events from each one and push the bytes onto
        # the queue.  Doing the messagebus work here would be unsafe.
        with _ports_lock:
            ports_snapshot = list(_our_ports.items())

        for _source_name, (port, normalized) in ports_snapshot:
            try:
                for _time, event in port.incoming_midi_events():
                    # The event buffer is reused on the next iteration;
                    # copy it before queueing.
                    _event_queue.put((normalized, bytes(event)))
            except Exception:
                traceback.print_exc()

    def _worker(self):
        while not self._stopped.is_set():
            try:
                normalized, data = _event_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                onMidiMessageTuple((list(data),), normalized)
            except Exception:
                traceback.print_exc()


def init():
    global _manager
    if _manager is not None:
        return
    _manager = JackMidiManager()


init()
