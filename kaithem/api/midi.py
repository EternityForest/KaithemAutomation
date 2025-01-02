"""
You can use normalize_midi_port_name to get name for the midi device
which can be used for things like subscribing to "/midi/portname".


"""

import structlog
from scullery import messagebus

from kaithem.src.plugins.CorePluginMidiToTags import normalize_midi_name

logger = structlog.get_logger(__name__)


def normalize_midi_port_name(name: str) -> str:
    """Given a name as would be returned by
    rtmidi's get_port_name, return a normalized name
    as used in the internal message bus.
    """
    return normalize_midi_name(name)


once: list[int] = [0]


def list_midi_inputs() -> list[str]:
    """
    These correspond to topics at /midi/portname you could
    subscribe to.
    """
    try:
        import rtmidi
    except ImportError:
        if once[0] == 0:
            messagebus.post_message(
                "/system/notifications/errors/",
                "python-rtmidi is missing. Most MIDI related features will not work.",
            )
            once[0] = 1
        return []
    try:
        try:
            m = rtmidi.MidiIn()
        except Exception:
            m = rtmidi.MidiIn()

        x = [
            normalize_midi_port_name(m.get_port_name(i))
            for i in range(m.get_port_count())
        ]
        m.close_port()
        return x
    except Exception:
        logger.exception("Error in MIDI system")
        return []
