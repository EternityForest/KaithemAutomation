# pyright: strict, reportOptionalMemberAccess=false,  reportUnknownMemberType=false, reportAttributeAccessIssue=false


import datetime
import sys
import time

if "--collect-only" not in sys.argv:
    from kaithem.src import tagpoints
    from kaithem.src.chandler import WebChandlerConsole, core, scenes, universes
    from kaithem.src.sound import play_logs

    core.boards["test_board"] = WebChandlerConsole.WebConsole()

    board = core.boards["test_board"]


async def test_fixtures():
    """Create a universe, a fixture type, and a fixture,
    add the fixture to a scene, check the universe vals
    """
    u = {"dmx": {"channels": 512, "framerate": 44, "number": 1, "type": "enttecopen"}}
    fixtypes = {"3ch RGB": [["red", "red"], ["green", "green"], ["blue", "blue"]]}
    # fixps = {"tst": {"blue": 42, "dim": 0, "green": 0, "red": 0}}
    fixas = {"testFixture": {"addr": 1, "name": "testFixture", "type": "3ch RGB", "universe": "dmx"}}

    board._onmsg("__admin__", ["setconfuniverses", u], "test")
    board.check_autosave()

    assert board.get_project_data()["setup"]["configured_universes"]["dmx"]

    board._onmsg("__admin__", ["setfixtureclass", "3ch RGB", fixtypes["3ch RGB"]], "test")
    assert board.get_project_data()["setup"]["fixture_types"]["3ch RGB"][0][0] == "red"
    board._onmsg("__admin__", ["setFixtureAssignment", "testFixture", fixas["testFixture"]], "test")

    s = scenes.Scene(board, "TestingScene1", id="TEST")
    # Must add scenes to the board so we can save them and test the saving
    board.addScene(s)
    s.go()
    cid = s.cue.id
    ## 0s are the pattern spacing

    board._onmsg("__admin__", ["add_cuef", cid, "testFixture", 0, 0, 0], "test")

    board._onmsg("__admin__", ["scv", cid, "@testFixture", "red", 39], "test")

    time.sleep(0.1)
    time.sleep(0.1)

    assert universes.universes["dmx"]().values[0] == 0
    assert universes.universes["dmx"]().values[1] == 39

    assert board.get_project_data()["setup"]["fixture_assignments"]["testFixture"]

    s.close()
    board.rmScene(s)
    assert "TestingScene1" not in board.scenes_by_name


def test_make_scene():
    s = scenes.Scene(board, "TestingScene1", id="TEST")
    # Must add scenes to the board so we can save them and test the saving
    board.addScene(s)

    assert "TEST" in scenes.scenes

    s.go()

    assert s.active
    assert s in board.active_scenes
    assert s.cue.name == "default"

    # Ensure the web render functions at least work
    # assert web.Web().editor("test_board")
    # assert web.Web().config("test_board")

    # # Make sure we can access it's web media display
    # assert web.Web().default("webmediadisplay", scene=s.id)

    s.add_cue("cue2")
    s.goto_cue("cue2")
    assert s.cue.name == "cue2"

    # Make sure a save file was created
    # board.check_autosave()
    # assert os.path.exists(os.path.join(directories.vardir, "chandler", "scenes", "TestingScene1.yaml"))

    s.close()
    board.rmScene(s)
    assert "TestingScene1" not in board.scenes_by_name

    # board.check_autosave()
    # assert not os.path.exists(os.path.join(directories.vardir, "chandler", "scenes", "TestingScene1.yaml"))


def test_setup_cue():
    # Ensure that if a setup cue exists, we go there first
    # then go to default

    s = scenes.Scene(board, "TestingScene1", id="TEST")
    board.addScene(s)

    assert "TEST" in scenes.scenes

    s.go()

    assert s.active
    assert s in board.active_scenes
    assert s.cue.name == "default"

    s.add_cue("__setup__")

    s.stop()
    s.go()

    assert s.cueHistory[-2][0] == "__setup__"
    assert s.cue.name == "default"

    s.close()
    board.rmScene(s)
    assert "TestingScene1" not in board.scenes_by_name


def test_checkpoint():
    # Ensure that if a a checkpoint cue exists, we go there

    s = scenes.Scene(board, "TestingScene1", id="TEST")
    board.addScene(s)

    assert "TEST" in scenes.scenes

    s.go()

    assert s.active
    assert s in board.active_scenes
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
    board.rmScene(s)
    assert "TestingScene1" not in board.scenes_by_name


def test_shuffle():
    s = scenes.Scene(board, "TestingScene1", id="TEST")
    # Must add scenes to the board so we can save them and test the saving
    board.addScene(s)

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
    board.rmScene(s)
    assert "TestingScene1" not in board.scenes_by_name


def test_sched():
    s = scenes.Scene(board, "TestingScene1", id="TEST")
    # Must add scenes to the board so we can save them and test the saving
    board.addScene(s)

    s.go()

    assert s.active
    assert s.cue.name == "default"

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

    s.cue.next_cue = "__schedule__"

    s.next_cue()

    assert s.cue.name == "after_a"

    s.close()
    board.rmScene(s)
    assert "TestingScene1" not in board.scenes_by_name


def test_timer_scene():
    s = scenes.Scene(board, "TestingScene1", id="TEST")
    # Must add scenes to the board so we can save them and test the saving
    board.addScene(s)

    assert "TEST" in scenes.scenes

    s.go()

    assert s.active
    assert s in board.active_scenes
    assert s.cue.name == "default"

    s.add_cue("cue2", length="@8pm")
    s.goto_cue("cue2")
    assert s.cue.name == "cue2"
    assert isinstance(s.cuelen, float)
    assert s.cuelen

    s.close()
    board.rmScene(s)
    assert "TestingScene1" not in board.scenes_by_name


def test_play_sound():
    s = scenes.Scene(board, "TestingScene2", id="TEST")
    board.addScene(s)

    assert "TEST" in scenes.scenes

    s.go()

    assert s.active
    assert s in board.active_scenes
    assert s.cue.name == "default"

    s.add_cue("cue2", sound="alert.ogg")
    s.goto_cue("cue2")
    time.sleep(1)

    # Dummy test sounds end right away
    assert play_logs[-1][0] == "play"
    assert play_logs[-1][1] == "TEST"
    assert play_logs[-1][2].endswith("alert.ogg")

    s.close()
    board.rmScene(s)

    assert "TestingScene2" not in board.scenes_by_name


def test_trigger_shortcuts():
    s = scenes.Scene(board, name="TestingScene3", id="TEST")
    s2 = scenes.Scene(board, name="TestingScene4", id="TEST2")
    board.addScene(s)
    board.addScene(s2)

    s.go()
    s2.go()

    assert s.active
    assert s in board.active_scenes
    assert s.cue.name == "default"

    s.add_cue("cue2", trigger_shortcut="foo")

    s2.add_cue("cue2", shortcut="foo")

    s.goto_cue("cue2")

    # Cue2 in s should trigger the shortcut code foo, which triggers Cue2 in s2
    assert s2.cue.name == "cue2"

    s.close()
    s2.close()
    board.rmScene(s)
    board.rmScene(s2)

    assert "TestingScene3" not in board.scenes_by_name
    assert "TestingScene4" not in board.scenes_by_name


def test_cue_logic():
    s = scenes.Scene(board, name="TestingScene5", id="TEST")
    s2 = scenes.Scene(board, name="TestingScene6", id="TEST2")
    board.addScene(s)
    board.addScene(s2)

    s.go()
    s2.go()

    assert s.active
    assert s in board.active_scenes
    assert s.cue.name == "default"

    s.add_cue(
        "cue2",
        rules=[
            ["cue.enter", [["goto", "TestingScene6", "cue2"]]],
            ["cue.enter", [["set_alpha", "=SCENE", "0.76"]]],
        ],
    )

    s2.add_cue("cue2")

    s.goto_cue("cue2")
    time.sleep(0.5)
    time.sleep(0.5)
    assert s2.cue.name == "cue2"
    assert s.alpha == 0.76

    s.close()
    s2.close()
    board.rmScene(s)
    board.rmScene(s2)

    assert "TestingScene5" not in board.scenes_by_name
    assert "TestingScene6" not in board.scenes_by_name


def test_commands():
    s = scenes.Scene(board, name="TestingScene5", id="TEST")
    s2 = scenes.Scene(board, name="TestingScene6", id="TEST2")
    board.addScene(s)
    board.addScene(s2)

    s.go()
    s2.go()

    assert s.active
    assert s in board.active_scenes
    assert s.cue.name == "default"

    s.add_cue(
        "cue2",
        rules=[
            ["cue.enter", [["goto", "TestingScene6", "cue2"]]],
            ["cue.enter", [["set_alpha", "=SCENE", "0.76"]]],
        ],
    )

    s2.add_cue("cue2")

    s.goto_cue("cue2")
    time.sleep(0.5)
    assert s2.cue.name == "cue2"
    assert s.alpha == 0.76

    s.close()
    s2.close()
    board.rmScene(s)
    board.rmScene(s2)

    assert "TestingScene5" not in board.scenes_by_name
    assert "TestingScene6" not in board.scenes_by_name


def test_lighting_value_set_tag():
    s = scenes.Scene(board, name="TestingScene5", id="TEST")
    s2 = scenes.Scene(board, name="TestingScene6", id="TEST2")
    board.addScene(s)
    board.addScene(s2)

    s.go()
    s2.go()

    # Set values and check that tags change
    s.cues["default"].set_value("/test1", "value", 50)
    s.cues["default"].set_value("/test2", "value", 60)
    time.sleep(0.3)
    time.sleep(0.3)

    assert tagpoints.Tag("/test1").value == 50
    assert tagpoints.Tag("/test2").value == 60

    # Half the alpha should have half the resulting values
    s.setAlpha(0.50)
    # Give backround rerender time
    time.sleep(0.25)
    time.sleep(0.1)

    assert tagpoints.Tag("/test1").value == 25
    assert tagpoints.Tag("/test2").value == 30

    s.stop()
    time.sleep(0.2)
    time.sleep(0.1)

    assert tagpoints.Tag("/test1").value == 0
    assert tagpoints.Tag("/test2").value == 0

    s.default_alpha = 0.5
    s.go()
    time.sleep(0.2)
    time.sleep(0.1)
    assert tagpoints.Tag("/test1").value == 25
    assert tagpoints.Tag("/test2").value == 30

    # Move it up and set it as a flicker layer
    s2.blend = "flicker"
    s2.priority = 65

    # Set values and check that tags change
    s2.cues["default"].set_value("/test1", "value", 255)
    s2.cues["default"].set_value("/test2", "value", 255)

    # Ensure the values are changing
    t1 = tagpoints.Tag("/test1").value
    t2 = tagpoints.Tag("/test2").value
    time.sleep(0.5)
    time.sleep(0.2)

    assert t1 != tagpoints.Tag("/test1").value
    assert t2 != tagpoints.Tag("/test2").value

    # Stop flickering, should be back to normal
    s2.stop()
    time.sleep(0.2)
    time.sleep(0.2)

    assert t1 == tagpoints.Tag("/test1").value
    assert t2 == tagpoints.Tag("/test2").value

    s2.go()
    time.sleep(0.2)
    time.sleep(0.2)
    time.sleep(0.2)

    # Flicker starts again
    assert t1 != tagpoints.Tag("/test1").value
    assert t2 != tagpoints.Tag("/test2").value
    t1 = tagpoints.Tag("/test1").value
    t2 = tagpoints.Tag("/test2").value
    time.sleep(0.5)
    time.sleep(0.2)

    assert t1 != tagpoints.Tag("/test1").value
    assert t2 != tagpoints.Tag("/test2").value

    # # Make sure cue vals saved
    # p = os.path.join(directories.vardir, "chandler", "scenes", "TestingScene5.yaml")
    # with open(p) as f:
    #     f2 = yaml.load(f, Loader=yaml.SafeLoader)

    # assert f2["cues"]["default"]["values"]["/test1"]["value"] == 50
    # assert f2["cues"]["default"]["values"]["/test2"]["value"] == 60

    # # Make sure scene settings saved
    # p = os.path.join(directories.vardir, "chandler", "scenes", "TestingScene6.yaml")
    # with open(p) as f:
    #     f2 = yaml.load(f, Loader=yaml.SafeLoader)

    # assert f2["blend"] == "flicker"
    # assert f2["priority"] == 65

    s.close()
    s2.close()
    board.rmScene(s)
    board.rmScene(s2)


def test_tag_io():
    "Tests the tag point UI inputs and meters that you can do in the scenes overview"
    # Not as thorough of a test as it maybe should be...
    display_tags = [
        ["Label", "=177", {"type": "meter"}],
        ["Label", "/blah", {"type": "string_input"}],
        ["Label", "/goo", {"type": "switch_input"}],
        ["Label", "/ghjgy", {"type": "numeric_input"}],
    ]

    s = scenes.Scene(board, name="TestingScene5", id="TEST")
    board.addScene(s)

    s.set_display_tags(display_tags)

    s.go()

    # Simulate user input
    board._onmsg("__admin__", ["inputtagvalue", s.id, "/ghjgy", 97], "nonexistantsession")
    time.sleep(0.1)
    # Make sure the input tag thing actually sets the value
    assert tagpoints.Tag("ghjgy").value == 97

    # Validate that the output display tag actually exists
    assert "=177" in tagpoints.allTagsAtomic

    # # Make sure cue vals saved
    # p = os.path.join(directories.vardir, "chandler", "scenes", "TestingScene5.yaml")
    # with open(p) as f:
    #     f2 = yaml.load(f, Loader=yaml.SafeLoader)

    # assert f2["display_tags"] == display_tags

    s.close()
    board.rmScene(s)


def test_cue_logic_plugin():
    # foo_command is from conftest.py written into dev shm plugins
    # folder

    s = scenes.Scene(board, name="TestingScene5", id="TEST")
    s2 = scenes.Scene(board, name="TestingScene6", id="TEST2")
    board.addScene(s)
    board.addScene(s2)

    s.go()
    s2.go()

    assert s.active
    assert s in board.active_scenes
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
    s.goto_cue("cue2")

    time.sleep(0.5)
    assert s2.cue.name == "cue2"

    s2.stop()
    s.stop()
    assert s2.cue.name == "default"
    assert s2.entered_cue == 0

    s.cues["default"].setRules(
        [
            ["cue.enter", [["foo_command", "test_val"]]],
        ],
    )

    time.sleep(0.2)
    assert s2.cue.name == "default"
    assert s2.entered_cue == 0

    s.go()
    time.sleep(0.2)
    time.sleep(0.2)

    assert s2.cue.name == "cue2"

    s.close()
    s2.close()
    board.rmScene(s)
    board.rmScene(s2)

    assert "TestingScene5" not in board.scenes_by_name
    assert "TestingScene6" not in board.scenes_by_name


# def test_scene_loaded_from_yaml():
#     # Conftest.py writes this scene as YAML
#     # to the dev/shm

#     # It has 2 cues.  It should go to the second
#     # then stop there because there's no next

#     s = board.scenes_by_name["unit_testing"]

#     assert s.active
#     assert s in board.active_scenes

#     if not s.cue.name == "c1":
#         time.sleep(1)

#     assert s.cue.name == "c1"

#     # This was set in default. But c1 is not a tracking scene so it should
#     # not carry over
#     assert tagpoints.Tag("/unit_testing/t1").value == 0

#     # But c1 does set this tag so that should be working.
#     assert tagpoints.Tag("/unit_testing/t2").value == 183.0
