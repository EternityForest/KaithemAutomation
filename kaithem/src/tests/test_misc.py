import gc
import sys
import time

if "--collect-only" not in sys.argv:  # pragma: no cover
    from kaithem.api import util


def test_private_ip_check():
    assert util.is_private_ip("127.0.0.1")
    assert util.is_private_ip("10.0.0.67")
    assert util.is_private_ip("::1")

    # Todo: shoyld we actually consider mesh
    # networks to be private?
    assert util.is_private_ip("fe80::1")

    assert not util.is_private_ip("100.27.132.170")
    assert not util.is_private_ip("89.207.132.170")


def test_midi_scanner():
    import rtmidi

    from kaithem.api.midi import list_midi_inputs

    midiout = rtmidi.MidiOut(name="test457")
    midiout.open_virtual_port("test123")
    found = 0
    try:
        x = list_midi_inputs(force_update=True)
        for i in x:
            if "test123" in i and "test457" in i:
                found += 1
    finally:
        midiout.close_port()

    assert found == 1


def test_midi_scanner_does_not_leave_behind_ports():
    """There was a bug where the midi scanner would leave behind ports.
    This test makes sure that doesn't happen."""
    from kaithem.api.midi import list_midi_inputs

    num = len(list_midi_inputs(force_update=True))
    time.sleep(0.1)
    for i in range(5):
        list_midi_inputs(force_update=True)
        time.sleep(0.1)

    gc.collect()
    gc.collect()

    for i in range(5):
        if len(list_midi_inputs(force_update=True)) == num:
            break
        time.sleep(0.1)

    # TODO could be brittle if other stuff is running
    assert len(list_midi_inputs(force_update=True)) == num
