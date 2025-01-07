import gc
import os
import shutil
import sys
import time

if "--collect-only" not in sys.argv:  # pragma: no cover
    from kaithem.src import util


def test_message_bus():
    from kaithem.src import logviewer, messagebus

    got = []

    def good_subscriber(topic, val):
        got.append((topic, val))

    messagebus.subscribe("test", good_subscriber)
    messagebus.post("test", "hello")
    time.sleep(0.2)
    assert len(got) == 1
    assert got[0] == ("/test", "hello")

    def bad_subscriber(topic, val):
        raise RuntimeError("bad")

    messagebus.subscribe("test2", bad_subscriber)
    messagebus.post("test2", "hello")
    time.sleep(0.2)
    logviewer.expect_log("bad_subscriber")


def test_map_tiles_cleanup():
    from kaithem.src import settings_overrides
    from kaithem.src.plugins import CorePluginMapTileServer

    settings_overrides.add_val(
        "core_plugin_map_tile_server/max_age_days", "10", priority=100
    )
    settings_overrides.add_val(
        "core_plugin_map_tile_server/cache_size_mb", "0", priority=100
    )
    try:
        os.makedirs(
            "/dev/shm/kaithem_tests/maptiles/openstreetmap/0/0/",
            exist_ok=True,
        )

        shutil.copy(
            "kaithem/data/static/img/1x1.png",
            "/dev/shm/kaithem_tests/maptiles/openstreetmap/0/0/0.png",
        )
        shutil.copy(
            "kaithem/data/static/img/1x1.png",
            "/dev/shm/kaithem_tests/maptiles/openstreetmap/0/0/1.png",
        )

        four_months_ago = time.time() - 60 * 60 * 24 * 30 * 4

        os.utime(
            "/dev/shm/kaithem_tests/maptiles/openstreetmap/0/0/0.png",
            (four_months_ago, four_months_ago),
        )

        CorePluginMapTileServer.clean()

        assert not os.path.exists(
            "/dev/shm/kaithem_tests/maptiles/openstreetmap/0/0/0.png"
        )

        assert os.path.exists(
            "/dev/shm/kaithem_tests/maptiles/openstreetmap/0/0/1.png"
        )

    finally:
        settings_overrides.add_val(
            "core_plugin_map_tile_server/max_age_days", ""
        )
        settings_overrides.add_val(
            "core_plugin_map_tile_server/cache_size_mb", ""
        )


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
