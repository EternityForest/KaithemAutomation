# SPDX-License-Identifier: GPL-3.0-or-later

"""
JACK-based MIDI input fan-out.

For every external MIDI output port visible to JACK (which under
pipewire-jack corresponds to every MIDI source the system can see) we
spawn a dedicated ``jack_midi_dump`` subprocess and connect that
subprocess's input port to the external source with an airwire via
``jacktools.connect``.

A small daemon thread per source reads the subprocess's stdout, parses
the leading hex bytes from each line, and forwards the resulting bytes
to :func:`onMidiMessageTuple` which dispatches them to the messagebus
and tag points.

We deliberately do *not* use python-rtmidi / rtmidi2 any more, and we
also avoid running an in-process JACK realtime callback: ``jack_midi_dump``
does the realtime work in C, one OS process per source, which keeps the
Python side essentially idle.
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from typing import Any

from scullery import jacktools, messagebus, workers

from kaithem.src import tagpoints

_logger = logging.getLogger(__name__)
# Public name of the JACK clients we own.  Each source gets a unique
# suffix appended, e.g. "KaithemMidi_0".  Used both as the client name
# passed to ``jack_midi_dump`` and to filter our own clients out of
# ``list_midi_sources``.
OUR_CLIENT_NAME = "KaithemMidi"

# Path to the wrapper script that ensures the ``jack_midi_dump``
# subprocess is killed if our Python process dies (it sets
# ``PR_SET_PDEATHSIG`` via ctypes before exec'ing the wrapped command).
JACK_MIDI_DUMP_WRAPPER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "jack_midi_dump_pdeathsig.py",
)

USE_MIDI = True
if not shutil.which("jack_midi_dump"):
    USE_MIDI = False
    _logger.warning("jack_midi_dump not found on PATH; MIDI features disabled.")

midi_tags = {}


def setTag(n: str, v: float, a: Any = None):
    if n not in midi_tags:
        midi_tags[n] = tagpoints.Tag(n)
        midi_tags[n].min = 0
        midi_tags[n].max = 127
    midi_tags[n].set_claim_val("default", v, timestamp=None, annotation=None)


def setTag14(n: str, v: float, a: Any = None):
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


def onMidiMessageTuple(m: tuple[tuple[int, int, int]], d: str):
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
# Subprocess worker (one per MIDI source)
# ---------------------------------------------------------------------------


# Match the optional "<digits>:" timestamp prefix that jack_midi_dump
# prints at the start of each line.  Examples:
#   "  3: e0 11 46"
#   "266: b0 08 45 control change ..."
_TIME_PREFIX_RE = re.compile(r"^\s*\d+:")


def _parse_line(line: str) -> bytes | None:
    """Extract the raw MIDI bytes from a single jack_midi_dump line.

    Returns ``None`` for blank lines or lines that don't contain any
    hex bytes.  ``jack_midi_dump`` prints one event per line::

         3: e0 11 46
        266: b0 08 45 control change (channel  0): controller   8, value  69

    We only care about the leading hex tokens; the human-readable text
    after them isn't reliable for every message type.
    """
    if not line:
        return None

    line = _TIME_PREFIX_RE.sub("", line)

    out = bytearray()
    for tok in line.split():
        # A valid MIDI byte token is exactly two hex digits.
        if len(tok) != 2:
            break
        try:
            out.append(int(tok, 16))
        except ValueError:
            break

    return bytes(out) if out else None


class MidiSourceWorker:
    """One ``jack_midi_dump`` subprocess + a reader thread.

    The subprocess registers an input port whose name matches its
    client name.  The owning :class:`JackMidiManager` connects the
    external MIDI source port to that input port.
    """

    # Backoff (seconds) between restart attempts when the subprocess
    # exits unexpectedly.  Capped at MAX_RESTART_BACKOFF.
    INITIAL_RESTART_BACKOFF = 1.0
    MAX_RESTART_BACKOFF = 30.0

    def __init__(
        self, source_port_name: str, normalized: str, client_name: str
    ):
        self.source_port_name = source_port_name
        self.normalized = normalized
        self.client_name = client_name

        self.target_port_name = f"{client_name}:input"

        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        # Used by the manager to wait for the subprocess to be ready
        # before attempting the airwire connect.
        self._ready = threading.Event()
        self._last_exit_returncode: int | None = None

    # -- Lifecycle -----------------------------------------------------------

    def start(self):
        self._stopped.clear()
        self._thread = threading.Thread(
            target=self._run_forever,
            daemon=True,
            name=f"MidiDump[{self.normalized}]",
        )
        self._thread.start()

    def stop(self):
        self._stopped.set()
        with self._lock:
            proc = self._proc
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass

    def wait_until_ready(self, timeout: float = 5.0) -> bool:
        """Block until the subprocess has registered its port.

        ``jack_midi_dump`` blocks until JACK accepts the new client,
        so by the time ``Popen`` returns the port is (almost) always
        already visible.  We also poll the port list to be safe.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                ports = jacktools.get_ports(is_midi=True, is_output=False)
                for p in ports:
                    if p.name == self.target_port_name:
                        self._ready.set()
                        return True
            except Exception:
                pass
            time.sleep(0.05)
        return False

    # -- Internal ------------------------------------------------------------

    def _run_forever(self):
        backoff = self.INITIAL_RESTART_BACKOFF
        while not self._stopped.is_set():
            try:
                self._spawn_and_read()
            except Exception:
                traceback.print_exc()
            if self._stopped.is_set():
                return
            # Subprocess died unexpectedly; back off and try again.
            time.sleep(backoff)
            backoff = min(self.MAX_RESTART_BACKOFF, backoff * 2)

    def _spawn_and_read(self):
        # Use line-buffered text mode so readline() returns complete
        # lines.  jack_midi_dump emits one event per line.
        #
        # We run the wrapped command via our ``JACK_MIDI_DUMP_WRAPPER``
        # script, which sets PR_SET_PDEATHSIG before exec'ing the real
        # command.  That guarantees the subprocess (and any descendants
        # it might fork off) are killed if our Python process dies for
        # any reason — not just an orderly shutdown, but SIGKILL, a
        # segfault, OOM-kill, etc.  Without this we'd leave orphaned
        # jack clients holding MIDI ports in the JACK graph.
        argv = [
            sys.executable,
            JACK_MIDI_DUMP_WRAPPER,
            "jack_midi_dump",
            self.client_name,
        ]
        try:
            proc = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                bufsize=1,
                text=True,
            )
        except FileNotFoundError:
            messagebus.post_message(
                "/system/notifications/errors",
                "jack_midi_dump not found on PATH; MIDI features disabled.",
            )
            return
        except Exception:
            traceback.print_exc()
            return

        with self._lock:
            self._proc = proc
        self._ready.set()

        try:
            assert proc.stdout is not None
            for raw_line in proc.stdout:
                if self._stopped.is_set():
                    break
                data = _parse_line(raw_line)
                if not data:
                    continue
                try:
                    # pyrefly: ignore [bad-argument-type]
                    onMidiMessageTuple((tuple(data),), self.normalized)
                except Exception:
                    traceback.print_exc()
        except Exception:
            traceback.print_exc()
        finally:
            try:
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            self._last_exit_returncode = proc.returncode
            with self._lock:
                self._proc = None


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

# source_port_name -> MidiSourceWorker
_workers: dict[str, MidiSourceWorker] = {}
_workers_lock = threading.Lock()


def get_jack_client_name() -> str:
    """Name of the JACK clients we own.

    Used by other modules that need to filter our ports out of the
    listing.
    """
    return OUR_CLIENT_NAME


def list_midi_sources() -> list[str]:
    """Return raw (unnormalized) full port names of all external MIDI
    output ports visible to JACK right now.
    """
    try:
        ports = jacktools.get_ports(is_midi=True, is_output=True)
        return [
            p.name
            for p in ports
            if not p.name.split(":", 1)[0].startswith(OUR_CLIENT_NAME + "_")
        ]
    except Exception:
        return []


def _slot_index_from_client_name(name: str) -> int | None:
    """Inverse of the slot-index convention used by ``JackMidiManager``."""
    prefix = f"{OUR_CLIENT_NAME}_"
    if not name.startswith(prefix):
        return None
    try:
        return int(name[len(prefix) :])
    except ValueError:
        return None


class JackMidiManager:
    """Keeps one :class:`MidiSourceWorker` per external MIDI output port.

    Subscribes to JACK port-lifecycle messages on the messagebus so the
    set of workers tracks the actual JACK graph.
    """

    _MAX_CLIENT_NAME_SLOT = 10**6

    def __init__(self):
        self._slot_counter = 0
        self._slot_lock = threading.Lock()

        messagebus.subscribe("/system/jack/newport", self._on_new_port)
        messagebus.subscribe("/system/jack/delport", self._on_del_port)
        # When JACK (re)starts we need to re-scan because ports come and go.
        messagebus.subscribe("/system/sound/jackstart", self._on_jack_start)

        # Initial scan picks up anything that was already registered
        # before we subscribed to the messagebus.
        self._initial_scan()

    # -- JACK port lifecycle -------------------------------------------------

    def _initial_scan(self):
        try:
            ports = jacktools.get_ports(is_midi=True, is_output=True)
            for p in ports:
                self._register_source(p)
        except Exception:
            traceback.print_exc()

    def _on_new_port(self, _topic, port_info: jacktools.PortInfo):
        try:
            if port_info.is_audio or port_info.is_input:
                return
            self._register_source(port_info)
        except Exception:
            traceback.print_exc()

    def _on_del_port(self, _topic, port_info: jacktools.PortInfo):
        with _workers_lock:
            worker = _workers.pop(port_info.name, None)
        if worker is not None:
            worker.stop()

    def _on_jack_start(self, _topic, _msg):
        # JACK came back up.  Stop everything we know about (their
        # jack_midi_dump children will have lost their connections
        # anyway) and re-scan.
        with _workers_lock:
            old = list(_workers.items())
            _workers.clear()
        for w in old:
            try:
                w[1].stop()
            except Exception:
                _logger.exception("Error stopping MIDI worker for %s", w[0])
        self._initial_scan()

    def _next_slot(self) -> int:
        with self._slot_lock:
            slot = self._slot_counter
            self._slot_counter = (
                self._slot_counter + 1
            ) % self._MAX_CLIENT_NAME_SLOT
        return slot

    def _register_source(self, port_info: jacktools.PortInfo):
        with _workers_lock:
            if port_info.name in _workers:
                return
            slot = self._next_slot()
            normalized = normalize_midi_name(port_info.name)
            client_name = f"{OUR_CLIENT_NAME}_{slot}"
            worker = MidiSourceWorker(
                source_port_name=port_info.name,
                normalized=normalized,
                client_name=client_name,
            )
            _workers[port_info.name] = worker

        worker.start()

        def f():
            self._connect_later(worker)

        workers.do(f)

    def _connect_later(self, worker: MidiSourceWorker):
        if not worker.wait_until_ready(timeout=15.0):
            raise RuntimeError("Timed out waiting for worker to be ready")

        for _ in range(10):
            try:
                jacktools.connect(
                    worker.source_port_name, worker.target_port_name
                )
            except Exception:
                time.sleep(0.2)
            else:
                return
        traceback.print_exc()


def init():
    JackMidiManager()


if USE_MIDI:
    init()
