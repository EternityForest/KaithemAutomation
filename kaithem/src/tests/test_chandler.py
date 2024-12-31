# pyright: strict, reportOptionalMemberAccess=false,  reportUnknownMemberType=false, reportAttributeAccessIssue=false


import datetime
import gc
import subprocess
import sys
import time

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


def test_mqtt():
    """Spins up mosquitto and tests that the MQTT feature works"""

    cfg = """
persistence false
allow_anonymous true
listener 7801
"""
    with open("/dev/shm/kaithem_tests/mosquitto.conf", "w") as f:
        f.write(cfg)

    pr = subprocess.Popen(
        ["mosquitto", "-c", "/dev/shm/kaithem_tests/mosquitto.conf"]
    )
    time.sleep(0.5)
    assert pr.poll() is None

    try:
        s = groups.Group(board, "TestingSceneMQTT")
        # Must add scenes to the board so we can save them and test the saving
        board.addGroup(s)
        s.go()

        s.setMqttServer("localhost:7801")
        s.setMQTTFeature("syncGroup", True)
        s.add_cue("c2")

        s2 = groups.Group(board, "TestingSceneMQTT2")
        s2.go()
        board.addGroup(s2)
        s2.setMqttServer("localhost:7801")
        s2.setMQTTFeature("syncGroup", True)
        s2.add_cue("c2")
        time.sleep(0.2)
        s.goto_cue("c2")
        time.sleep(0.2)

        for attempt in stamina.retry_context(on=AssertionError, attempts=50):
            with attempt:
                assert s2.cue.name == "c2"
    finally:
        pr.kill()


def test_fixtures():
    """Create a universe, a fixture type, and a fixture,
    add the fixture to a group, check the universe vals
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

    s = groups.Group(board, "TestingGroup1", id="TEST")
    # Must add groups to the board so we can save them and test the saving
    board.addGroup(s)
    s.go()
    cid = s.cue.id
    ## 0s are the pattern spacing
    core.wait_frame()

    board._onmsg("__admin__", ["add_cuef", cid, "testFixture", 0, 0, 0], "test")
    core.wait_frame()

    board._onmsg("__admin__", ["scv", cid, "@testFixture", "red", 39], "test")
    board._onmsg("__admin__", ["scv", cid, "@testFixture", "dim", 64.5], "test")

    core.wait_frame()

    assert universes.universes["dmx"]().values[0] == 0
    assert universes.universes["dmx"]().values[1] == 39

    assert int(universes.universes["dmx"]().values[4]) == 64
    assert int(universes.universes["dmx"]().values[5]) == 127
    assert int(universes.universes["dmx"]().values[6]) == 4

    assert board.cl_get_project_data()["setup"]["fixture_assignments"][
        "testFixture"
    ]

    s.close()
    board.rmGroup(s)
    core.wait_frame()

    assert "TestingGroup1" not in board.groups_by_name


def test_duplicate_group_name():
    grp1 = groups.Group(board, "TestGroup1", id="TEST")
    board.addGroup(grp1)
    grp1.go()
    core.wait_frame()
    assert grp1 in board.active_groups

    with pytest.raises(RuntimeError):
        groups.Group(board, "TestGroup1", id="TEST")

    assert grp1 in board.active_groups

    grp1.close()
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

    grp = groups.Group(board, "TestNonTracking", id="TEST")

    grp.go()
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

    grp.close()
    board.rmGroup(grp)
    core.wait_frame()
    assert "TestNonTracking" not in board.groups_by_name
    core.wait_frame()

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

    s = groups.Group(board, "TestingGroup1", id="TEST")
    board.addGroup(s)

    assert "TEST" in groups.groups

    s.go()

    assert s.active

    # Make code coverage happy about __repr__
    assert repr(s)
    assert repr(s.cue)

    core.wait_frame()
    assert s in board.active_groups
    assert s.cue.name == "default"

    s.add_cue("__setup__")

    s.stop()
    s.go()

    assert s.cueHistory[-2][0] == "__setup__"
    assert s.cue.name == "default"

    # Need to get coverage on go on cue that's already active
    # TODO maybe more detailed tests
    s.go()

    s.close()
    board.rmGroup(s)
    core.wait_frame()

    assert "TestingGroup1" not in board.groups_by_name


def test_checkpoint():
    # Ensure that if a a checkpoint cue exists, we go there

    s = groups.Group(board, "TestingGroup1", id="TEST")
    board.addGroup(s)

    assert "TEST" in groups.groups

    s.go()

    assert s.active
    core.wait_frame()

    assert s in board.active_groups
    assert s.cue.name == "default"

    s.add_cue("checkpoint", checkpoint=True)

    s.stop()
    s.go()

    assert s.cue.name == "default"

    s.goto_cue("checkpoint")

    s.stop()
    s.go()

    assert s.cue.name == "checkpoint"

    s.close()
    board.rmGroup(s)
    core.wait_frame()

    assert "TestingGroup1" not in board.groups_by_name


def test_shuffle():
    s = groups.Group(board, "TestingGroup1", id="TEST")
    # Must add groups to the board so we can save them and test the saving
    board.addGroup(s)

    s.go()

    assert s.active
    assert s.cue.name == "default"

    s.add_cue("cue2", next_cue="shuffle:x_*")

    for i in range(250):
        s.add_cue(f"x_{i}")

    s.goto_cue("cue2")

    s.next_cue()
    assert s.cue.name != "cue2"

    x = s.cue.name
    s.goto_cue("cue2")

    s.next_cue()
    assert s.cue.name != x

    s.close()
    board.rmGroup(s)
    core.wait_frame()

    assert "TestingGroup1" not in board.groups_by_name


def test_sched():
    s = groups.Group(board, "TestingGroup1", id="TEST")
    # Must add groups to the board so we can save them and test the saving
    board.addGroup(s)

    s.go()

    assert s.active
    assert s.cue.name == "default"
    s.cue.next_cue = "__schedule__"

    t = datetime.datetime.now() - datetime.timedelta(hours=2)

    # Make a looping schedule.  Before_b ends before the current time, we want to be in
    # after_a

    s.add_cue("before_a", length=f"@{t.strftime('%l%P')}")

    t += datetime.timedelta(hours=1)
    s.add_cue("before_b", length=f"@{t.strftime('%l%P')}")

    t += datetime.timedelta(hours=2)
    s.add_cue("after_a", length=f"@{t.strftime('%l%P')}")

    t += datetime.timedelta(hours=2)
    s.add_cue("after_b", length=f"@{t.strftime('%l%P')}", next_cue="before_a")

    s.next_cue()

    assert s.cue.name == "after_a"

    t = datetime.timedelta(minutes=-1) + datetime.datetime.now()
    s.add_cue("sched_at_test", schedule_at=f"@{t.strftime('%l%P')}")

    s.goto_cue("default")
    s.next_cue()
    assert s.cue.name == "sched_at_test"

    s.close()
    board.rmGroup(s)
    core.wait_frame()

    assert "TestingGroup1" not in board.groups_by_name


def test_timer_group():
    s = groups.Group(board, "TestingGroup1", id="TEST")
    # Must add groups to the board so we can save them and test the saving
    board.addGroup(s)

    assert "TEST" in groups.groups

    s.go()

    assert s.active
    core.wait_frame()

    assert s in board.active_groups
    assert s.cue.name == "default"

    s.add_cue("cue2", length="@8pm")
    s.goto_cue("cue2")
    assert s.cue.name == "cue2"
    assert isinstance(s.cuelen, float)
    assert s.cuelen

    s.close()
    board.rmGroup(s)
    core.wait_frame()

    assert "TestingGroup1" not in board.groups_by_name


def test_play_sound():
    s = groups.Group(board, "TestingGroup2", id="TEST")
    board.addGroup(s)

    assert "TEST" in groups.groups

    s.go()

    assert s.active
    core.wait_frame()

    assert s in board.active_groups
    assert s.cue.name == "default"

    s.add_cue("cue2", sound="alert.ogg")
    s.goto_cue("cue2")

    # Asyc from the frames can't just frame wait
    time.sleep(1)
    time.sleep(1)

    # Dummy test sounds end right away
    assert play_logs[-1][0] == "play"
    assert play_logs[-1][1] == "TEST"
    # Resolver should have found an opus file
    assert play_logs[-1][2].endswith(".opus")

    s.close()
    board.rmGroup(s)
    core.wait_frame()

    assert "TestingGroup2" not in board.groups_by_name


def test_trigger_shortcuts():
    s = groups.Group(board, name="TestingGroup3", id="TEST")
    s2 = groups.Group(board, name="TestingGroup4", id="TEST2")
    board.addGroup(s)
    board.addGroup(s2)

    s.go()
    s2.go()

    assert s.active
    core.wait_frame()

    assert s in board.active_groups
    assert s.cue.name == "default"

    s.add_cue("cue2", trigger_shortcut="foo")

    s2.add_cue("cue2", shortcut="foo")

    s.goto_cue("cue2")

    core.wait_frame()
    core.wait_frame()

    # Cue2 in s should trigger the shortcut code foo, which triggers Cue2 in s2
    assert s2.cue.name == "cue2"

    s.close()
    s2.close()
    board.rmGroup(s)
    board.rmGroup(s2)
    core.wait_frame()

    assert "TestingGroup3" not in board.groups_by_name
    assert "TestingGroup4" not in board.groups_by_name


def test_shortcuts():
    grp = groups.Group(board, name="TestingGroup3", id="TEST")
    board.addGroup(grp)

    grp.go()

    assert grp.active
    core.wait_frame()

    assert grp in board.active_groups
    assert grp.cue.name == "default"

    grp.add_cue("cue2", shortcut="__generate__from__number__")

    cue2 = grp.cues["cue2"]

    # Test setting to same value
    cue2.shortcut = cue2.shortcut
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

    grp.close()
    board.rmGroup(grp)
    core.wait_frame()

    assert "TestingGroup3" not in board.groups_by_name

    # Make sure the shortcut was removed
    assert ("shortcut2" not in global_actions.shortcut_codes) or (
        len(global_actions.shortcut_codes["shortcut2"]) == 0
    )


def test_cue_logic():
    s = groups.Group(board, name="TestingGroup5", id="TEST")
    s2 = groups.Group(board, name="TestingGroup6", id="TEST2")
    board.addGroup(s)
    board.addGroup(s2)

    s.go()
    s2.go()

    assert s.active
    core.wait_frame()

    assert s in board.active_groups
    assert s.cue.name == "default"

    s.add_cue(
        "cue2",
        rules=[
            ["cue.enter", [["goto", "TestingGroup6", "cue2"]]],
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
        ["=test_var", [["goto", "TestingGroup6", "default"]]],
    ]
    assert s2.cue.name == "cue2"

    core.wait_frame()
    core.wait_frame()
    assert s2.cue.name == "default"

    # Test var change rules
    s2.cues["cue2"].rules = [
        ["=~test_var", [["goto", "TestingGroup6", "default"]]],
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
        ["=/test_var", [["goto", "TestingGroup6", "default"]]],
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
        ["=+test_var", [["goto", "TestingGroup6", "default"]]],
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

    s.close()
    s2.close()
    board.rmGroup(s)
    board.rmGroup(s2)
    core.wait_frame()

    assert "TestingGroup5" not in board.groups_by_name
    assert "TestingGroup6" not in board.groups_by_name


def test_cue_logic_tags():
    sending_group = groups.Group(board, name="sending_group", id="TEST")
    recv_group = groups.Group(board, name="recv_group", id="TEST2")
    board.addGroup(sending_group)
    board.addGroup(recv_group)

    sending_group.go()
    recv_group.go()

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
            ["=tv('/logic_test_tag')", [["goto", "recv_group", "cue2"]]],
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

    sending_group.close()
    recv_group.close()

    board.rmGroup(sending_group)
    board.rmGroup(recv_group)
    core.wait_frame()

    assert "TestingGroup5" not in board.groups_by_name
    assert "TestingGroup6" not in board.groups_by_name

    gc.collect()

    # Ensure that any subscribers cleaned up.
    assert len(test_set_tag.subscribers) == test_set_tag_initial_subscribers
    assert len(logic_test_tag.subscribers) == logic_test_tag_initial_subscribers


def test_commands():
    s = groups.Group(board, name="TestingGroup5", id="TEST")
    s2 = groups.Group(board, name="TestingGroup6", id="TEST2")
    board.addGroup(s)
    board.addGroup(s2)

    s.go()
    s2.go()

    assert s.active
    core.wait_frame()
    assert s in board.active_groups
    assert s.cue.name == "default"

    s.add_cue(
        "cue2",
        rules=[
            ["cue.enter", [["goto", "TestingGroup6", "cue2"]]],
            ["cue.enter", [["set_alpha", "=GROUP", "0.76"]]],
        ],
    )

    s2.add_cue("cue2")

    s.goto_cue("cue2")

    core.wait_frame()
    core.wait_frame()

    assert s2.cue.name == "cue2"
    assert s.alpha == 0.76

    s.close()
    s2.close()
    board.rmGroup(s)
    board.rmGroup(s2)
    core.wait_frame()

    assert "TestingGroup5" not in board.groups_by_name
    assert "TestingGroup6" not in board.groups_by_name


def test_tag_backtrack_feature():
    s = groups.Group(board, name="TestingGroup7", id="TEST")
    board.addGroup(s)

    s.go()
    core.wait_frame()
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
    s.close()
    core.wait_frame()


def test_priorities():
    s = groups.Group(board, name="TestingGroup7", id="TEST")
    s2 = groups.Group(board, name="TestingGroup8", id="TEST2")

    board.addGroup(s)
    board.addGroup(s)

    s.go()
    s2.go()

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
    s = groups.Group(board, name="TestingGroup5", id="TEST")
    s2 = groups.Group(board, name="TestingGroup6", id="TEST2")
    board.addGroup(s)
    board.addGroup(s2)

    s.go()
    s2.go()

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

    s.close()
    s2.close()
    board.rmGroup(s)
    board.rmGroup(s2)
    core.wait_frame()


def test_tag_io():
    "Tests the tag point UI inputs and meters that you can do in the groups overview"
    # Not as thorough of a test as it maybe should be...
    display_tags = [
        ["Label", "=177", {"type": "meter"}],
        ["Label", "/blah", {"type": "string_input"}],
        ["Label", "/goo", {"type": "switch_input"}],
        ["Label", "/ghjgy", {"type": "numeric_input"}],
    ]

    s = groups.Group(board, name="TestingGroup5", id="TEST")
    board.addGroup(s)

    s.display_tags = display_tags

    s.go()

    # Simulate user input
    board._onmsg(
        "__admin__", ["inputtagvalue", s.id, "/ghjgy", 97], "nonexistantsession"
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

    s.close()
    board.rmGroup(s)
    core.wait_frame()


def test_cue_logic_plugin():
    # foo_command is from conftest.py written into dev shm plugins
    # folder

    s = groups.Group(board, name="TestingGroup5", id="TEST")
    s2 = groups.Group(board, name="TestingGroup6", id="TEST2")
    board.addGroup(s)
    board.addGroup(s2)

    s.go()
    s2.go()

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
    for attempt in stamina.retry_context(on=AssertionError, attempts=10):
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

    s.close()
    s2.close()
    board.rmGroup(s)
    board.rmGroup(s2)
    core.wait_frame()

    assert "TestingGroup5" not in board.groups_by_name
    assert "TestingGroup6" not in board.groups_by_name


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
