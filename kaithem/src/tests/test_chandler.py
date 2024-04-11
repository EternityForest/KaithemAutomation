import logging
import os
import time

import yaml

from kaithem.src import directories, tagpoints
from kaithem.src.chandler import core, scenes
from kaithem.src.sound import play_logs

board = core.boards[0]()


def test_make_scene():
    s = scenes.Scene("TestingScene1", id="TEST")
    # Must add scenes to the board so we can save them and test the saving
    board.addScene(s)

    assert "TEST" in scenes.scenes

    s.go()

    assert s.active
    assert s in scenes.active_scenes
    assert s.cue.name == "default"

    s.add_cue("cue2")
    s.goto_cue("cue2")
    assert s.cue.name == "cue2"

    # Make sure a save file was created
    board.check_autosave()
    assert os.path.exists(os.path.join(directories.vardir, "chandler", "scenes", "TestingScene1.yaml"))

    s.close()
    board.rmScene(s)
    assert "TestingScene1" not in scenes.scenes_by_name

    board.check_autosave()
    assert not os.path.exists(os.path.join(directories.vardir, "chandler", "scenes", "TestingScene1.yaml"))


def test_timer_scene():
    s = scenes.Scene("TestingScene1", id="TEST")
    # Must add scenes to the board so we can save them and test the saving
    board.addScene(s)

    assert "TEST" in scenes.scenes

    s.go()

    assert s.active
    assert s in scenes.active_scenes
    assert s.cue.name == "default"

    s.add_cue("cue2", length="@8pm")
    s.goto_cue("cue2")
    assert s.cue.name == "cue2"
    assert isinstance(s.cuelen, float)
    assert s.cuelen

    # Make sure a save file was created
    board.check_autosave()
    assert os.path.exists(os.path.join(directories.vardir, "chandler", "scenes", "TestingScene1.yaml"))

    s.close()
    board.rmScene(s)
    assert "TestingScene1" not in scenes.scenes_by_name

    board.check_autosave()
    assert not os.path.exists(os.path.join(directories.vardir, "chandler", "scenes", "TestingScene1.yaml"))


def test_play_sound():
    s = scenes.Scene("TestingScene2", id="TEST")
    board.addScene(s)

    assert "TEST" in scenes.scenes

    s.go()

    assert s.active
    assert s in scenes.active_scenes
    assert s.cue.name == "default"

    s.add_cue("cue2", sound="alert.ogg")
    s.goto_cue("cue2")
    time.sleep(1)

    # Dummy test sounds end right away
    assert play_logs[-1][0] == "play"
    assert play_logs[-1][1] == "TEST"
    assert play_logs[-1][2].endswith("alert.ogg")

    board.check_autosave()

    # Test that saved data is what it should be
    p = os.path.join(directories.vardir, "chandler", "scenes", "TestingScene2.yaml")
    with open(p) as f:
        f2 = yaml.load(f, Loader=yaml.SafeLoader)

    assert "cue2" in f2["cues"]

    assert f2["cues"]["cue2"]["sound"].endswith("alert.ogg")

    s.close()
    board.rmScene(s)
    board.check_autosave()

    assert "TestingScene2" not in scenes.scenes_by_name


def test_trigger_shortcuts():
    s = scenes.Scene(name="TestingScene3", id="TEST")
    s2 = scenes.Scene(name="TestingScene4", id="TEST2")
    board.addScene(s)
    board.addScene(s2)

    s.go()
    s2.go()

    assert s.active
    assert s in scenes.active_scenes
    assert s.cue.name == "default"

    s.add_cue("cue2", trigger_shortcut="foo")

    s2.add_cue("cue2", shortcut="foo")

    s.goto_cue("cue2")

    # Cue2 in s should trigger the shortcut code foo, which triggers Cue2 in s2
    assert s2.cue.name == "cue2"
    board.check_autosave()

    # Test that saved data is what it should be
    p = os.path.join(directories.vardir, "chandler", "scenes", "TestingScene3.yaml")
    with open(p) as f:
        f2 = yaml.load(f, Loader=yaml.SafeLoader)

    assert f2["cues"]["cue2"]["trigger_shortcut"] == "foo"

    p = os.path.join(directories.vardir, "chandler", "scenes", "TestingScene4.yaml")
    with open(p) as f:
        f2 = yaml.load(f, Loader=yaml.SafeLoader)

    assert f2["cues"]["cue2"]["shortcut"] == "foo"

    s.close()
    s2.close()
    board.rmScene(s)
    board.rmScene(s2)

    assert "TestingScene3" not in scenes.scenes_by_name
    assert "TestingScene4" not in scenes.scenes_by_name


def test_cue_logic():
    logging.warning(scenes.rootContext.commands.scriptcommands)
    s = scenes.Scene(name="TestingScene5", id="TEST")
    s2 = scenes.Scene(name="TestingScene6", id="TEST2")
    board.addScene(s)
    board.addScene(s2)

    s.go()
    s2.go()

    assert s.active
    assert s in scenes.active_scenes
    assert s.cue.name == "default"

    s.add_cue(
        "cue2",
        rules=[
            ["cue.enter", [["goto", "TestingScene6", "cue2"]]],
            ["cue.enter", [["setAlpha", "=SCENE", "0.76"]]],
        ],
    )

    s2.add_cue("cue2")

    s.goto_cue("cue2")
    time.sleep(0.5)
    assert s2.cue.name == "cue2"
    assert s.alpha == 0.76
    board.check_autosave()

    p = os.path.join(directories.vardir, "chandler", "scenes", "TestingScene5.yaml")
    with open(p) as f:
        f2 = yaml.load(f, Loader=yaml.SafeLoader)

    assert len(f2["cues"]["cue2"]["rules"]) == 2

    s.close()
    s2.close()
    board.rmScene(s)
    board.rmScene(s2)

    assert "TestingScene5" not in scenes.scenes_by_name
    assert "TestingScene6" not in scenes.scenes_by_name


def test_commands():
    s = scenes.Scene(name="TestingScene5", id="TEST")
    s2 = scenes.Scene(name="TestingScene6", id="TEST2")
    board.addScene(s)
    board.addScene(s2)

    s.go()
    s2.go()

    assert s.active
    assert s in scenes.active_scenes
    assert s.cue.name == "default"

    s.add_cue(
        "cue2",
        rules=[
            ["cue.enter", [["goto", "TestingScene6", "cue2"]]],
            ["cue.enter", [["setAlpha", "=SCENE", "0.76"]]],
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

    assert "TestingScene5" not in scenes.scenes_by_name
    assert "TestingScene6" not in scenes.scenes_by_name


def test_lighting_value_set_tag():
    # Use the same API that the web would, to create a tagpoint universe
    # Which maps the first two channels to tag points
    universes = {
        "tags": {
            "channelConfig": {"2": "test2", "1:test1": "test1"},
            "channels": 512,
            "framerate": 44,
            "number": 1,
            "type": "tagpoints",
        }
    }

    board._onmsg("__admin__", ["setconfuniverses", universes], "nonexistantsession")
    board.check_autosave()

    # Make sure universe settings saved
    p = os.path.join(directories.vardir, "chandler", "universes", "tags.yaml")
    with open(p) as f:
        f2 = yaml.load(f, Loader=yaml.SafeLoader)

    assert f2 == universes["tags"]

    s = scenes.Scene(name="TestingScene5", id="TEST")
    s2 = scenes.Scene(name="TestingScene6", id="TEST2")
    board.addScene(s)
    board.addScene(s2)

    s.go()
    s2.go()

    # Set values and check that tags change
    s.cues["default"].set_value("tags", 1, 50)
    s.cues["default"].set_value("tags", 2, 60)
    time.sleep(0.25)
    assert tagpoints.Tag("/test1").value == 50
    assert tagpoints.Tag("/test2").value == 60

    # Half the alpha should have half the resulting values
    s.setAlpha(0.50)
    # Give backround rerender time
    time.sleep(0.25)
    assert tagpoints.Tag("/test1").value == 25
    assert tagpoints.Tag("/test2").value == 30

    # Move it up and set it as a flicker layer
    s2.blend = "flicker"
    s2.priority = 65

    # Set values and check that tags change
    s2.cues["default"].set_value("tags", 1, 255)
    s2.cues["default"].set_value("tags", 2, 255)

    # Ensure the values are changing
    t1 = tagpoints.Tag("/test1").value
    t2 = tagpoints.Tag("/test2").value
    time.sleep(0.5)

    assert t1 != tagpoints.Tag("/test1").value
    assert t2 != tagpoints.Tag("/test2").value

    board.check_autosave()

    # Make sure cue vals saved
    p = os.path.join(directories.vardir, "chandler", "scenes", "TestingScene5.yaml")
    with open(p) as f:
        f2 = yaml.load(f, Loader=yaml.SafeLoader)

    assert f2["cues"]["default"]["values"]["tags"][1] == 50
    assert f2["cues"]["default"]["values"]["tags"][2] == 60

    # Make sure scene settings saved
    p = os.path.join(directories.vardir, "chandler", "scenes", "TestingScene6.yaml")
    with open(p) as f:
        f2 = yaml.load(f, Loader=yaml.SafeLoader)

    assert f2["blend"] == "flicker"
    assert f2["priority"] == 65

    s.close()
    s2.close()
    board.rmScene(s)
    board.rmScene(s2)
    board.check_autosave()


def test_tag_io():
    "Tests the tag point UI inputs and meters that you can do in the scenes overview"
    # Not as thorough of a test as it maybe should be...
    display_tags = [
        ["Label", "=177", {"type": "meter"}],
        ["Label", "blah", {"type": "string_input"}],
        ["Label", "goo", {"type": "switch_input"}],
        ["Label", "ghjgy", {"type": "numeric_input"}],
    ]

    s = scenes.Scene(name="TestingScene5", id="TEST")
    board.addScene(s)

    s.set_display_tags(display_tags)

    s.go()

    # Simulate user input
    board._onmsg("__admin__", ["inputtagvalue", s.id, "ghjgy", 97], "nonexistantsession")

    # Make sure the input tag thing actually sets the value
    assert tagpoints.Tag("ghjgy").value == 97

    # Validate that the output display tag actually exists
    assert "=177" in tagpoints.allTagsAtomic

    board.check_autosave()

    # Make sure cue vals saved
    p = os.path.join(directories.vardir, "chandler", "scenes", "TestingScene5.yaml")
    with open(p) as f:
        f2 = yaml.load(f, Loader=yaml.SafeLoader)

    assert f2["display_tags"] == display_tags

    s.close()
    board.rmScene(s)
    board.check_autosave()
