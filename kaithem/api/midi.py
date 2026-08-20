"""
Public MIDI API.

All MIDI in/out is handled via a JACK client (works under pipewire-jack).
The plugin :mod:`kaithem.src.plugins.CorePluginMidiToTags` owns the actual
JACK client that listens on MIDI inputs and fans events out to the
internal message bus and tag points.

This module is intentionally just a thin abstraction layer so callers
(the about page, WebChandlerConsole, etc.) don't have to know how MIDI
is wired under the hood.
"""

import time

import structlog

from kaithem.src.plugins.CorePluginMidiToTags import normalize_midi_name

logger = structlog.get_logger(__name__)


def normalize_midi_port_name(name: str) -> str:
    """Given a raw JACK MIDI port name (e.g. ``"My Keyboard:midi_out"``),
    return a normalized name as used in the internal message bus.
    """
    return normalize_midi_name(name)


inputs_cache: tuple[float, list[str]] = (0.0, [])


def __list_midi_inputs() -> list[str]:
    """Return a list of normalized MIDI input port names currently
    visible to JACK (which under pipewire corresponds to all MIDI
    sources the system can see).
    """
    try:
        from kaithem.src.plugins.CorePluginMidiToTags import (
            get_jack_client_name,  # noqa: F401
            list_midi_sources,
        )

        return [normalize_midi_port_name(n) for n in list_midi_sources()]
    except Exception:  # pragma: no cover
        logger.exception("Error listing MIDI inputs via JACK")
        return []


def list_midi_inputs(force_update: bool = False) -> list[str]:
    """
    These correspond to topics at /midi/portname you could
    subscribe to.
    """
    global inputs_cache
    if force_update or (time.monotonic() - inputs_cache[0] > 1):
        inputs_cache = (time.monotonic(), __list_midi_inputs())

    return inputs_cache[1]
