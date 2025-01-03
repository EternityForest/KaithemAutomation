# pyright: strict, reportOptionalMemberAccess=false,  reportUnknownMemberType=false, reportAttributeAccessIssue=false


import datetime
import gc
import os
import subprocess
import sys
import time
import uuid

import pytest
import stamina

if "--collect-only" not in sys.argv:  # pragma: no cover
    from kaithem.src import tagpoints
    from kaithem.src.chandler import (
        WebChandlerConsole,
        core,
        global_actions,
        groups,
        universes,
    )
    from kaithem.src.sound import play_logs

    core.boards["test_board"] = WebChandlerConsole.WebConsole()

    board = core.boards["test_board"]


class TempGroup:
    """Gives a running group and then cleans it up.
    Asserts a whole bunch of stuff every time.
    """

    def __init__(self, name: str | None = None):
        self.name = name or ("test_group_" + str(uuid.uuid4()).replace("-", ""))

    def __enter__(self):
        self.group = groups.Group(board, self.name)
        assert self.group.name == self.name
        board.addGroup(self.group)
        self.group.go()
        core.wait_frame()
        core.wait_frame()
        assert self.group.active
        assert self.group.alpha == 1
        assert self.group.cue.name == "default"
        assert self.name in board.groups_by_name
        assert self.group in board.active_groups
        assert self.group.id in board.groups
        assert self.group.id in groups.groups
        return self.group

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.group.close()
        core.wait_frame()
        core.wait_frame()
        board.rmGroup(self.group)
        core.wait_frame()
        core.wait_frame()
        assert self.name not in board.groups_by_name
        assert self.group not in board.active_groups
        assert self.group.id not in board.groups
        assert self.group.id not in groups.groups

        del self.group
        gc.collect()
        core.wait_frame()


staticdir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
staticdir = os.path.join(staticdir, "data", "static")


def test_slide_rel_len():
    with TempGroup() as grp:
        grp.cue.slide = os.path.join(
            staticdir, "sounds", "320181__dland__hint.opus"
        )
        grp.cue.rel_length = True
        grp.cue.length = 0.1
        grp.add_cue("cue2")
        grp.goto_cue("default")

        # Don't depend too much on the exact value
        assert grp.cuelen > 0.3
        assert grp.cuelen < 1
        time.sleep(2)
        assert grp.cue.name


def test_sound_rel_len():
    with TempGroup() as grp:
        grp.cue.sound = os.path.join(
            staticdir, "sounds", "320181__dland__hint.opus"
        )
        grp.cue.rel_length = True
        grp.cue.length = 0.1
        grp.goto_cue("default")

        # Don't depend too much on the exact value
        assert grp.cuelen > 0.3
        assert grp.cuelen < 1


def test_mqtt():
    """Spins up mosquitto and tests that the MQTT feature works"""

    cfg = """
persistence false
allow_anonymous true
listener 38527
"""
    with open("/dev/shm/kaithem_tests/mosquitto.conf", "w") as f:
        f.write(cfg)

    pr = subprocess.Popen(
        ["mosquitto", "-c", "/dev/shm/kaithem_tests/mosquitto.conf"]
    )
    time.sleep(0.5)
    assert pr.poll() is None

    try:
        with TempGroup() as s:
            s.setMqttServer("localhost:38527")
            s.setMQTTFeature("syncGroup", True)
            s.add_cue("c2")

            with TempGroup() as s2:
                s2.setMqttServer("localhost:38527")
                s2.setMQTTFeature("syncGroup", True)
                s2.add_cue("c2")
                time.sleep(0.5)
                s.goto_cue("c2")
                time.sleep(0.2)

                for attempt in stamina.retry_context(
                    on=AssertionError, attempts=50
                ):
                    with attempt:
                        assert s2.cue.name == "c2"
    finally:
        pr.terminate()
        time.sleep(2)
        pr.kill()


def test_tap_tempo():
    with TempGroup() as grp:
        grp.tap()
        time.sleep(0.5)
        grp.tap()
        time.sleep(0.5)
        grp.tap()

        core.wait_frame()
        assert abs(grp.bpm - 120) < 10


def test_midi():
    import rtmidi

    from kaithem.api import midi
    from kaithem.src.chandler import WebChandlerConsole
    from kaithem.src.plugins import CorePluginMidiToTags

    # TODO thi belongs in it's on test
    non_normalized = "Midi Through:Midi Through Port-0 14:0"
    normalized = midi.normalize_midi_port_name(non_normalized)

    assert normalized == "midi_through_midi_through_port_0"
    # Make sure redoing it doesn't change it
    assert midi.normalize_midi_port_name(normalized) == normalized

    # Create virtual midi input
    midiout = rtmidi.MidiOut(name="Kaithem Test")
    midiout.open_virtual_port("virtualoutput")

    # Hack so we don't have to wait ten seconds
    CorePluginMidiToTags.doScan()

    note_on = [0x90, 60, 112]  # channel 1, middle C, velocity 112
    note_off = [0x80, 60, 0]

    with TempGroup() as grp:
        grp.add_cue("cue2")

        grp.midi_source = "kaithem_test_virtualoutput"

        # Ensure that this name is something a user could find
        # Via UI
        assert grp.midi_source in WebChandlerConsole.list_midi_inputs()

        # Note we have converted to the note name here
        grp.cue.rules = [
            ["midi.note:1.C5", [["goto", "=GROUP", "cue2"]]],
        ]

        grp.cues["cue2"].rules = [
            ["midi.noteoff:1.C5", [["goto", "=GROUP", "default"]]],
        ]

        core.wait_frame()
        core.wait_frame()

        assert grp.cue.name == "default"
        midiout.send_message(note_on)
        core.wait_frame()
        core.wait_frame()

        assert grp.cue.name == "cue2"
        midiout.send_message(note_off)
        core.wait_frame()
        core.wait_frame()
        assert grp.cue.name == "default"

        midiout.close_port()


def test_fixtures():
    """Create a universe, a fixture type, and a fixture,
    add the fixture to a group, che/ck the universe vals
    """
    u = {
        "dmx": {
            "channels": 512,
            "framerate": 44,
            "number": 1,
            "type": "enttecopen",
        }
    }
    fixtypes = {
        "TestFixtureType": {
            "channels": [
                {"name": "red", "type": "red"},
                {"name": "green", "type": "green"},
                {"name": "blue", "type": "blue"},
                {"name": "dim", "type": "intensity"},
                {"name": "dim_fine", "type": "fine", "coarse": "dim"},
                {"name": "mode", "type": "fixed", "value": 4},
            ]
        }
    }

    # fixps = {"tst": {"blue": 42, "dim": 0, "green": 0, "red": 0}}
    fixas = {
        "testFixture": {
            "addr": 1,
            "name": "testFixture",
            "type": "TestFixtureType",
            "universe": "dmx",
        }
    }

    board._onmsg("__admin__", ["setconfuniverses", u], "test")
    board.cl_check_autosave()

    assert board.cl_get_project_data()["setup"]["configured_universes"]["dmx"]

    board._onmsg(
        "__admin__",
        ["setfixtureclass", "TestFixtureType", fixtypes["TestFixtureType"]],
        "test",
    )
    assert (
        board.cl_get_project_data()["setup"]["fixture_types"][
            "TestFixtureType"
        ]["channels"][0]["name"]
        == "red"
    )
    board._onmsg(
        "__admin__",
        ["setFixtureAssignment", "testFixture", fixas["testFixture"]],
        "test",
    )

    with TempGroup() as grp:
        cid = grp.cue.id
        ## 0s are the pattern spacing
        core.wait_frame()

        board._onmsg(
            "__admin__", ["add_cuef", cid, "testFixture", 0, 0, 0], "test"
        )
        core.wait_frame()

        board._onmsg(
            "__admin__", ["scv", cid, "@testFixture", "red", 39], "test"
        )
        board._onmsg(
            "__admin__", ["scv", cid, "@testFixture", "dim", 64.5], "test"
        )

        core.wait_frame()

        assert universes.universes["dmx"]().values[0] == 0
        assert universes.universes["dmx"]().values[1] == 39

        assert int(universes.universes["dmx"]().values[4]) == 64
        assert int(universes.universes["dmx"]().values[5]) == 127
        assert int(universes.universes["dmx"]().values[6]) == 4

        assert board.cl_get_project_data()["setup"]["fixture_assignments"][
            "testFixture"
        ]


def test_duplicate_group_name():
    grp1 = groups.Group(board, "TestGroup1", id="TEST")
    board.addGroup(grp1)
    grp1.go()
    core.wait_frame()
    core.wait_frame()

    assert grp1 in board.active_groups

    with pytest.raises(RuntimeError):
        groups.Group(board, "TestGroup1", id="TEST")

    assert grp1 in board.active_groups

    grp1.close()
    core.wait_frame()
    core.wait_frame()

    assert grp1 not in board.active_groups
    board.rmGroup(grp1)


def test_cue_track_setting():
    u = {
        "dmx2": {
            "channels": 512,
            "framerate": 44,
            "number": 1,
            "type": "enttecopen",
        }
    }

    # Todo replace with a setter method
    board.configured_universes = u
    board.cl_create_universes(u)

    with TempGroup() as grp:
        grp.cue.set_value_immediate("dmx2", 1, 255)

        # Non existant universes need test coverage to be sure
        # it doesn't crash anything
        grp.cue.set_value_immediate("nonexistent", 1, 255)

        core.wait_frame()
        core.wait_frame()
        core.wait_frame()

        assert int(universes.universes["dmx2"]().values[1]) == 255

        # This is a tracking cue so it keeps the value
        grp.add_cue("test1")
        grp.goto_cue("test1")
        core.wait_frame()
        core.wait_frame()
        time.sleep(0.1)
        assert grp.cue.name == "test1"
        assert int(universes.universes["dmx2"]().values[1]) == 255

        # This is not a tracking cue so it doesn't keep the value
        grp.add_cue("test2", track=False)
        grp.goto_cue("test2")
        core.wait_frame()
        core.wait_frame()
        time.sleep(0.1)
        assert grp.cue.name == "test2"
        assert int(universes.universes["dmx2"]().values[1]) == 0

    board.configured_universes = {}
    board.cl_create_universes(board.configured_universes)

    core.wait_frame()
    core.wait_frame()

    assert "dmx2" not in universes.universes


def test_make_group():
    s = groups.Group(board, "TestingGroup1", id="TEST")
    # Must add groups to the board so we can save them and test the saving
    board.addGroup(s)

    assert "TEST" in groups.groups

    s.go()

    assert s.active
    core.wait_frame()
    assert s in board.active_groups
    assert s.cue.name == "default"

    # Ensure the web render functions at least work
    # assert web.Web().editor("test_board")
    # assert web.Web().config("test_board")

    # # Make sure we can access it's web media display
    # assert web.Web().default("webmediadisplay", group=s.id)

    s.add_cue("cue2")
    s.goto_cue("cue2")
    assert s.cue.name == "cue2"

    # Make sure a save file was created
    # board.check_autosave()
    # assert os.path.exists(os.path.join(directories.vardir, "chandler", "groups", "TestingGroup1.yaml"))

    s.close()
    board.rmGroup(s)
    core.wait_frame()

    assert "TestingGroup1" not in board.groups_by_name

    # board.check_autosave()
    # assert not os.path.exists(os.path.join(directories.vardir, "chandler", "groups", "TestingGroup1.yaml"))


def test_setup_cue():
    # Ensure that if a setup cue exists, we go there first
    # then go to default

    with TempGroup() as grp:
        # Make code coverage happy about __repr__
        assert repr(grp)
        assert repr(grp.cue)

        core.wait_frame()
        assert grp in board.active_groups
        assert grp.cue.name == "default"

        grp.add_cue("__setup__")

        grp.stop()
        grp.go()

        assert grp.cueHistory[-2][0] == "__setup__"
        assert grp.cue.name == "default"


def test_checkpoint():
    # Ensure that if a a checkpoint cue exists, we go there

    with TempGroup() as grp:
        assert grp in board.active_groups
        assert grp.cue.name == "default"

        grp.add_cue("checkpoint", checkpoint=True)

        grp.stop()
        grp.go()

        assert grp.cue.name == "default"

        grp.goto_cue("checkpoint")

        grp.stop()
        grp.go()

        assert grp.cue.name == "checkpoint"


def test_shuffle():
    with TempGroup() as grp:
        grp.add_cue("cue2", next_cue="shuffle:x_*")

        for i in range(250):
            grp.add_cue(f"x_{i}")

        grp.goto_cue("cue2")

        grp.next_cue()
        assert grp.cue.name != "cue2"

        x = grp.cue.name
        grp.goto_cue("cue2")

        grp.next_cue()
        assert grp.cue.name != x


def test_sched():
    with TempGroup() as grp:
        grp.cue.next_cue = "__schedule__"

        t = datetime.datetime.now() - datetime.timedelta(hours=2)

        # Make a looping schedule.  Before_b ends before the current time, we want to be in
        # after_a

        grp.add_cue("before_a", length=f"@{t.strftime('%l%P')}")

        t += datetime.timedelta(hours=1)
        grp.add_cue("before_b", length=f"@{t.strftime('%l%P')}")

        t += datetime.timedelta(hours=2)
        grp.add_cue("after_a", length=f"@{t.strftime('%l%P')}")

        t += datetime.timedelta(hours=2)
        grp.add_cue(
            "after_b", length=f"@{t.strftime('%l%P')}", next_cue="before_a"
        )

        grp.next_cue()

        assert grp.cue.name == "after_a"

        t = datetime.timedelta(minutes=-1) + datetime.datetime.now()
        grp.add_cue("sched_at_test", schedule_at=f"@{t.strftime('%l%P')}")

        grp.goto_cue("default")
        grp.next_cue()
        assert grp.cue.name == "sched_at_test"


def test_timer_group():
    with TempGroup() as grp:
        grp.add_cue("cue2", length="@8pm")
        grp.goto_cue("cue2")
        assert grp.cue.name == "cue2"
        assert isinstance(grp.cuelen, float)
        assert grp.cuelen


def test_play_sound():
    with TempGroup() as grp:
        grp.add_cue("cue2", sound="alert.ogg")
        grp.goto_cue("cue2")

        # Asyc from the frames can't just frame wait
        time.sleep(1)
        time.sleep(1)

        # Dummy test sounds end right away
        assert play_logs[-1][0] == "play"
        assert play_logs[-1][1] == grp.id
        # Resolver should have found an opus file
        assert play_logs[-1][2].endswith(".opus")


def test_renaming():
    with TempGroup() as grp:
        cue2 = grp.add_cue("cue2")
        old_name = grp.name

        grp.setName("TestRenameCues2")
        core.wait_frame()
        core.wait_frame()

        assert grp.name == "TestRenameCues2"
        assert old_name not in board.groups_by_name
        assert "TestRenameCues2" in board.groups_by_name

        # No rename default
        with pytest.raises(RuntimeError):
            grp.rename_cue("default", "default2")

        # No rename to already existing
        with pytest.raises(RuntimeError):
            grp.rename_cue("cue2", "default")

        with pytest.raises(ValueError):
            grp.rename_cue("cue2", "?<>,")

        with pytest.raises(ValueError):
            grp.rename_cue("cue2", " ")

        grp.go()
        grp.goto_cue("cue2")

        core.wait_frame()
        core.wait_frame()
        core.wait_frame()

        assert grp.cue.name == "cue2"
        # No rename active cue
        with pytest.raises(RuntimeError):
            grp.rename_cue("cue2", "foo")

        grp.goto_cue("default")

        # wait to let gui push actions pointing at old cue finish
        core.wait_frame()
        core.wait_frame()
        grp.rename_cue("cue2", "cue3")
        core.wait_frame()
        core.wait_frame()

        assert "cue3" in grp.cues
        assert "cue2" not in grp.cues
        assert cue2.name == "cue3"


def add_cue_fail():
    with TempGroup() as grp:
        grp.add_cue("cue2")
        # No duplicate
        with pytest.raises(RuntimeError):
            grp.add_cue("cue2")
        with pytest.raises(RuntimeError):
            grp.add_cue("default")

        with pytest.raises(ValueError):
            grp.add_cue(
                "#!$&()&^",
            )

        with pytest.raises(ValueError):
            grp.add_cue("")

        with pytest.raises(ValueError):
            grp.add_cue(" ")

        # Trailing space
        with pytest.raises(ValueError):
            grp.add_cue("steamedhams ")


def test_trigger_shortcuts():
    with TempGroup() as s:
        with TempGroup() as s2:
            s.add_cue("cue2", trigger_shortcut="foo")

            s2.add_cue("cue2", shortcut="foo")

            s.goto_cue("cue2")

            core.wait_frame()
            core.wait_frame()

            # Cue2 in s should trigger the shortcut code foo, which triggers Cue2 in s2
            assert s2.cue.name == "cue2"


def test_shortcuts():
    with TempGroup() as grp:
        assert grp.active
        core.wait_frame()

        assert grp in board.active_groups
        assert grp.cue.name == "default"

        grp.add_cue("cue2_blah", shortcut="__generate__from__number__")

        cue2 = grp.cues["cue2_blah"]

        # Test setting to same value
        cue2.shortcut = cue2.shortcut

        # Try to stop a nuisance KeyError,
        # if the rename takes effect before
        # the sending of the data to the UI
        # it wuld try to send data that was renamed away.
        core.wait_frame()
        core.wait_frame()
        time.sleep(1)

        # Make sure renaming cues doesn't break shortcuts
        grp.rename_cue("cue2_blah", "cue2")
        assert cue2.name == "cue2"

        core.wait_frame()
        core.wait_frame()

        assert len(global_actions.shortcut_codes[cue2.shortcut]) == 1

        # Todo maybe we shouldn't store numbers as ints with a multiplier
        global_actions.cl_trigger_shortcut_code(str(int(cue2.number / 1000)))

        # Setting the shortcut is not expected to be instant
        core.wait_frame()
        core.wait_frame()

        assert grp.cue.name == "cue2"

        grp.goto_cue("default")
        core.wait_frame()
        core.wait_frame()
        assert grp.cue.name == "default"

        old_shortcut = cue2.shortcut
        cue2.shortcut = "shortcut2"

        core.wait_frame()
        core.wait_frame()

        # Ensure the old shortcut does not still work
        global_actions.cl_trigger_shortcut_code(old_shortcut)
        core.wait_frame()
        core.wait_frame()
        assert grp.cue.name == "default"

        # Ensure the new shortcut works
        global_actions.cl_trigger_shortcut_code("shortcut2")
        core.wait_frame()
        core.wait_frame()
        assert grp.cue.name == "cue2"

    # Make sure the shortcut was removed
    assert ("shortcut2" not in global_actions.shortcut_codes) or (
        len(global_actions.shortcut_codes["shortcut2"]) == 0
    )


def test_cue_logic():
    with TempGroup() as s:
        with TempGroup() as s2:
            s.add_cue(
                "cue2",
                rules=[
                    ["cue.enter", [["goto", s2.name, "cue2"]]],
                    ["cue.enter", [["set_alpha", "=GROUP", "0.76"]]],
                ],
            )

            s2.add_cue("cue2")
            s.goto_cue("cue2")

            # Events are sometimes delayed a frame
            core.wait_frame()
            core.wait_frame()

            assert s2.cue.name == "cue2"
            assert s.alpha == 0.76

            # Test variable based rules
            s2.script_context.setVar("test_var", 1)
            s2.cue.rules = [
                ["=test_var", [["goto", s2.name, "default"]]],
            ]
            assert s2.cue.name == "cue2"

            core.wait_frame()
            core.wait_frame()
            assert s2.cue.name == "default"

            # Test var change rules
            s2.cues["cue2"].rules = [
                ["=~test_var", [["goto", s2.name, "default"]]],
            ]
            s2.goto_cue("cue2")
            core.wait_frame()
            core.wait_frame()
            assert s2.cue.name == "cue2"

            s2.script_context.setVar("test_var", 0)
            core.wait_frame()
            core.wait_frame()
            assert s2.cue.name == "default"

            # Test rising edge rules
            s2.script_context.setVar("test_var", 1)
            s2.cues["cue2"].rules = [
                ["=/test_var", [["goto", s2.name, "default"]]],
            ]
            s2.goto_cue("cue2")
            s2.script_context.setVar("test_var", 1)
            core.wait_frame()
            core.wait_frame()
            assert s2.cue.name == "cue2"

            s2.script_context.setVar("test_var", 0)
            s2.script_context.setVar("test_var", 1)
            core.wait_frame()
            core.wait_frame()
            assert s2.cue.name == "default"

            # Test change-to-nonzero rules
            s2.script_context.setVar("test_var", 1)
            s2.cues["cue2"].rules = [
                ["=+test_var", [["goto", s2.name, "default"]]],
            ]
            s2.goto_cue("cue2")

            # Going to zero should do nothing
            s2.script_context.setVar("test_var", 0)
            core.wait_frame()
            core.wait_frame()
            assert s2.cue.name == "cue2"

            s2.script_context.setVar("test_var", 1)
            core.wait_frame()
            core.wait_frame()
            assert s2.cue.name == "default"


def test_cue_logic_tags():
    with TempGroup("sending_group") as sending_group:
        with TempGroup("recv_group") as recv_group:
            assert sending_group.active
            core.wait_frame()

            assert sending_group in board.active_groups
            assert sending_group.cue.name == "default"

            test_set_tag = tagpoints.Tag("/test_set_tag")
            logic_test_tag = tagpoints.Tag("/logic_test_tag")

            test_set_tag_initial_subscribers = len(test_set_tag.subscribers)
            logic_test_tag_initial_subscribers = len(logic_test_tag.subscribers)

            assert test_set_tag_initial_subscribers == 0
            assert logic_test_tag_initial_subscribers == 0

            # This should set a tag, and also, when a different tag gets set,
            # trigger a transition in the receiving group
            sending_group.add_cue(
                "cue2",
                rules=[
                    [
                        "=tv('/logic_test_tag')",
                        [["goto", "recv_group", "cue2"]],
                    ],
                    ["cue.enter", [["set_tag", "/test_set_tag", "5"]]],
                ],
            )

            recv_group.add_cue("cue2")

            sending_group.goto_cue("cue2")

            # Events are sometimes delayed a frame
            core.wait_frame()
            core.wait_frame()
            assert test_set_tag.value == 5

            # Now set the tag and test the transition
            logic_test_tag.value = 1

            core.wait_frame()
            core.wait_frame()
            assert recv_group.cue.name == "cue2"

    assert "TestingGroup5" not in board.groups_by_name
    assert "TestingGroup6" not in board.groups_by_name

    gc.collect()

    # Ensure that any subscribers cleaned up.
    assert len(test_set_tag.subscribers) == test_set_tag_initial_subscribers
    assert len(logic_test_tag.subscribers) == logic_test_tag_initial_subscribers


def test_commands():
    with TempGroup() as s:
        with TempGroup() as s2:
            s.add_cue(
                "cue2",
                rules=[
                    ["cue.enter", [["goto", s2.name, "cue2"]]],
                    ["cue.enter", [["set_alpha", "=GROUP", "0.76"]]],
                ],
            )

            s2.add_cue("cue2")

            s.goto_cue("cue2")

            core.wait_frame()
            core.wait_frame()

            assert s2.cue.name == "cue2"
            assert s.alpha == 0.76


# def test_exit_cue_action():
# TODO: As events are async,  exit happens before enter sometimes
#     with TempGroup() as s:
#         s.add_cue(
#             "cue2",
#             rules=[
#                 ["cue.exist", [["goto", s.name, "default"]]],
#             ],
#         )

#         s.add_cue("cue2")

#         s.goto_cue("cue2")

#         core.wait_frame()
#         core.wait_frame()

#         # Nothing happens, it's an exit action
#         assert s2.cue.name == "cue2"

#         s.goto_cue("cue2")

#         core.wait_frame()
#         core.wait_frame()

#         # Exiting and reentering the cue causes a redirect that interrupts the goto
#         assert s2.cue.name == "default"


def test_tag_backtrack_feature():
    with TempGroup() as s:
        s.cues["default"].set_value_immediate("/test_bt", "value", 1)

        # Set values and check that tags change
        # First time allow two frames because it creates a new universe for the tag

        core.wait_frame()
        core.wait_frame()
        assert tagpoints.Tag("/test_bt").value == 1

        s.cues["default"].set_value_immediate("/test_bt", "value", 2)
        core.wait_frame()
        assert tagpoints.Tag("/test_bt").value == 2

        c2 = s.add_cue("c2")
        c2.set_value_immediate("/test_bt", "value", 5)

        s.add_cue("c3")

        # c3 has no lighting values, however as c2 is between default and c3 in sequence,
        # Skipping should backtrack.
        s.goto_cue("c3")
        core.wait_frame()

        assert tagpoints.Tag("/test_bt").value == 5


def test_priorities():
    with TempGroup() as s:
        with TempGroup() as s2:
            # Set values and check that tags change
            s.cues["default"].set_value_immediate("/test_p", "value", 1)
            s2.cues["default"].set_value_immediate("/test_p", "value", 2)

            core.wait_frame()

            assert tagpoints.Tag("/test_p").value == 2

            # Change priority and confirm stacking order changes
            s.priority = 51

            core.wait_frame()
            core.wait_frame()

            assert tagpoints.Tag("/test_p").value == 1


def test_lighting_value_set_tag_flicker():
    with TempGroup() as s:
        with TempGroup() as s2:
            # Set values and check that tags change
            s.cues["default"].set_value_immediate("/test1", "value", 50)
            s.cues["default"].set_value_immediate("/test2", "value", 60)

            core.wait_frame()

            assert tagpoints.Tag("/test1").value == 50
            assert tagpoints.Tag("/test2").value == 60

            # Half the alpha should have half the resulting values
            s.setAlpha(0.50)
            core.wait_frame()

            assert tagpoints.Tag("/test1").value == 25
            assert tagpoints.Tag("/test2").value == 30

            s.stop()
            core.wait_frame()

            assert tagpoints.Tag("/test1").value == 0
            assert tagpoints.Tag("/test2").value == 0

            s.default_alpha = 0.5
            s.go()
            core.wait_frame()

            assert tagpoints.Tag("/test1").value == 25
            assert tagpoints.Tag("/test2").value == 30

            # Move it up and set it as a flicker layer
            s2.blend = "flicker"
            s2.priority = 65

            # Set values and check that tags change
            s2.cues["default"].set_value_immediate("/test1", "value", 255)
            s2.cues["default"].set_value_immediate("/test2", "value", 255)

            # Ensure the values are changing
            t1 = tagpoints.Tag("/test1").value
            t2 = tagpoints.Tag("/test2").value
            core.wait_frame()

            for attempt in stamina.retry_context(on=AssertionError):
                with attempt:
                    assert t1 != tagpoints.Tag("/test1").value
                    assert t2 != tagpoints.Tag("/test2").value

            # Stop flickering, should be back to normal
            s2.stop()
            core.wait_frame()

            for attempt in stamina.retry_context(on=AssertionError):
                with attempt:
                    assert t1 == tagpoints.Tag("/test1").value
                    assert t2 == tagpoints.Tag("/test2").value

            s2.go()
            core.wait_frame()

            for attempt in stamina.retry_context(on=AssertionError):
                with attempt:
                    # Flicker starts again
                    assert t1 != tagpoints.Tag("/test1").value
                    assert t2 != tagpoints.Tag("/test2").value

            t1 = tagpoints.Tag("/test1").value
            t2 = tagpoints.Tag("/test2").value
            core.wait_frame()

            for attempt in stamina.retry_context(on=AssertionError):
                with attempt:
                    assert t1 != tagpoints.Tag("/test1").value
                    assert t2 != tagpoints.Tag("/test2").value

            # # Make sure cue vals saved
            # p = os.path.join(directories.vardir, "chandler", "groups", "TestingGroup5.yaml")
            # with open(p) as f:
            #     f2 = yaml.load(f, Loader=yaml.SafeLoader)

            # assert f2["cues"]["default"]["values"]["/test1"]["value"] == 50
            # assert f2["cues"]["default"]["values"]["/test2"]["value"] == 60

            # # Make sure group settings saved
            # p = os.path.join(directories.vardir, "chandler", "groups", "TestingGroup6.yaml")
            # with open(p) as f:
            #     f2 = yaml.load(f, Loader=yaml.SafeLoader)

            # assert f2["blend"] == "flicker"
            # assert f2["priority"] == 65


def test_tag_io():
    "Tests the tag point UI inputs and meters that you can do in the groups overview"
    # Not as thorough of a test as it maybe should be...
    display_tags = [
        ["Label", "=177", {"type": "meter"}],
        ["Label", "/blah", {"type": "string_input"}],
        ["Label", "/goo", {"type": "switch_input"}],
        ["Label", "/ghjgy", {"type": "numeric_input"}],
    ]

    with TempGroup() as s:
        s.display_tags = display_tags

        # Simulate user input
        board._onmsg(
            "__admin__",
            ["inputtagvalue", s.id, "/ghjgy", 97],
            "nonexistantsession",
        )
        core.wait_frame()
        # Make sure the input tag thing actually sets the value
        assert tagpoints.Tag("ghjgy").value == 97

        # Validate that the output display tag actually exists
        assert "=177" in tagpoints.allTagsAtomic

        # # Make sure cue vals saved
        # p = os.path.join(directories.vardir, "chandler", "groups", "TestingGroup5.yaml")
        # with open(p) as f:
        #     f2 = yaml.load(f, Loader=yaml.SafeLoader)

        # assert f2["display_tags"] == display_tags


def test_cue_logic_plugin():
    # foo_command is from conftest.py written into dev shm plugins
    # folder

    with TempGroup() as s:
        with TempGroup() as s2:
            assert s.active
            core.wait_frame()

            assert s in board.active_groups
            assert s.cue.name == "default"

            # Foo command just triggers it's arg
            # as both an event and shortcut code
            s.add_cue(
                "cue2",
                rules=[
                    ["cue.enter", [["foo_command", "test_val"]]],
                ],
            )

            s2.add_cue("cue2", shortcut="test_val")
            # Registering a new cue with a shortcut listener is not instant
            core.wait_frame()
            core.wait_frame()

            s.goto_cue("cue2")

            core.wait_frame()

            # not frame synced yet?
            for attempt in stamina.retry_context(
                on=AssertionError, attempts=10
            ):
                with attempt:
                    assert s2.cue.name == "cue2"

            s2.stop()
            s.stop()
            core.wait_frame()

            assert s2.cue.name == "default"
            assert s2.entered_cue == 0

            s.cues["default"].rules = [
                ["cue.enter", [["foo_command", "test_val"]]],
            ]

            core.wait_frame()
            core.wait_frame()

            assert s2.cue.name == "default"
            assert s2.entered_cue == 0

            s2.go()
            core.wait_frame()
            core.wait_frame()
            assert s2.cue.name == "default"

            s.go()

            core.wait_frame()
            core.wait_frame()

            # Script events are not currently frame synced
            for i in range(10):
                if not s2.cue.name == "cue2":
                    time.sleep(0.25)

            assert s2.cue.name == "cue2"


def test_cue_logic_inherit_rules_cue():
    with TempGroup() as grp:
        grp.add_cue(
            "__rules__",
            rules=[
                ["cue.enter", [["set_alpha", "=GROUP", "0.7"]]],
            ],
        )

        grp.goto_cue("default")

        core.wait_frame()
        core.wait_frame()

        assert grp.alpha == 0.7


def test_cue_logic_inherit():
    with TempGroup() as s:
        s.add_cue(
            "cue2",
            rules=[
                ["cue.enter", [["set_alpha", "=GROUP", "0.7"]]],
            ],
        )

        s.cues["default"].inherit_rules = "cue2"

        s.goto_cue("default")

        core.wait_frame()
        core.wait_frame()

        assert s.alpha == 0.7


def test_cue_logic_inherit_loop():
    with TempGroup() as s:
        s.add_cue(
            "cue2",
            rules=[
                ["cue.enter", [["set_alpha", "=GROUP", "0.7"]]],
            ],
            inherit_rules="default",
        )

        s.cues["default"].inherit_rules = "cue2"

        s.goto_cue("default")

        core.wait_frame()
        core.wait_frame()

        assert s.alpha == 0.7


# def test_group_loaded_from_yaml():
#     # Conftest.py writes this group as YAML
#     # to the dev/shm

#     # It has 2 cues.  It should go to the second
#     # then stop there because there's no next

#     s = board.groups_by_name["unit_testing"]

#     assert s.active
#     core.wait_frame()

#     assert s in board.active_groups

#     if not s.cue.name == "c1":
#         time.sleep(1)

#     assert s.cue.name == "c1"

#     # This was set in default. But c1 is not a tracking group so it should
#     # not carry over
#     assert tagpoints.Tag("/unit_testing/t1").value == 0

#     # But c1 does set this tag so that should be working.
#     assert tagpoints.Tag("/unit_testing/t2").value == 183.0
